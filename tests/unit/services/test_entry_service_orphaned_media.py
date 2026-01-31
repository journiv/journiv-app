"""
Unit tests for orphaned media deletion when updating entries.

Tests verify that media files are immediately deleted when they're removed
from an entry's content delta during an update.
"""
import pytest
import uuid
from datetime import date
from unittest.mock import MagicMock, patch, call
from pathlib import Path

from sqlmodel import Session, create_engine

from app.models.base import BaseModel
from app.models.entry import Entry, EntryMedia
from app.models.journal import Journal
from app.models.user import User
from app.schemas.entry import EntryCreate, EntryUpdate, QuillDelta
from app.core.time_utils import utc_now
from app.services.entry_service import EntryService


def _setup_session():
    """Create an in-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    return Session(engine)


def _create_user(session: Session) -> User:
    """Create a test user."""
    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="Test User",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _create_journal(session: Session, user_id: uuid.UUID) -> Journal:
    """Create a test journal."""
    journal = Journal(
        user_id=user_id,
        title="Test Journal",
    )
    session.add(journal)
    session.commit()
    session.refresh(journal)
    return journal


def _create_entry_with_media(
    session: Session,
    user_id: uuid.UUID,
    journal_id: uuid.UUID,
    title: str = "Test Entry",
    delta: dict = None,
    media_ids: list = None,
) -> Entry:
    """Create a test entry with media.

    Note: This creates an entry with a normalized delta (using media UUIDs as sources).
    This is how the delta is stored in the database after normalization.
    """
    if delta is None and media_ids:
        # Create a normalized delta with media UUIDs as sources
        ops = [{"insert": "Test content\n"}]
        for media_id in media_ids:
            ops.append({"insert": {"image": str(media_id)}})
            ops.append({"insert": "\n"})
        delta = {"ops": ops}

    entry = Entry(
        user_id=user_id,
        journal_id=journal_id,
        title=title,
        content_delta=delta,
        content_plain_text="Test content",
        entry_date=date.today(),
        entry_timezone="UTC",
        entry_datetime_utc=utc_now(),
        is_draft=False,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)

    # Create media records if specified
    if media_ids:
        for i, media_id in enumerate(media_ids):
            media = EntryMedia(
                id=media_id,
                entry_id=entry.id,
                media_type="image",
                file_path=f"user/{user_id}/images/file-path-{i+1}.jpg",
                original_filename=f"image-{i+1}.jpg",
                file_size=1024,
                mime_type="image/jpeg",
                checksum=f"checksum-{i+1}",
                upload_status="COMPLETED",
            )
            session.add(media)
        session.commit()

    return entry


class TestOrphanedMediaDeletion:
    """Test orphaned media deletion functionality."""

    def test_delete_orphaned_media_removes_file_when_media_removed_from_delta(self):
        """Test that media is deleted when removed from entry delta."""
        session = _setup_session()
        user = _create_user(session)
        journal = _create_journal(session, user.id)

        media_id_1 = uuid.uuid4()
        media_id_2 = uuid.uuid4()

        entry = _create_entry_with_media(
            session,
            user.id,
            journal.id,
            media_ids=[media_id_1, media_id_2],
        )

        # Verify initial state
        assert len(session.query(EntryMedia).all()) == 2

        service = EntryService(session)

        # Update delta to remove one media (keep only the second one)
        # The delta should contain the media UUID as the source (like normalized_delta would)
        new_delta = {
            "ops": [
                {"insert": "Test content\n"},
                {"insert": {"image": str(media_id_2)}},
                {"insert": "\n"},
            ]
        }

        with patch(
            "app.services.media_storage_service.MediaStorageService"
        ) as mock_storage_service:
            mock_instance = MagicMock()
            mock_storage_service.return_value = mock_instance

            # Update entry with new delta
            service.update_entry(
                entry.id,
                user.id,
                EntryUpdate(content_delta=QuillDelta.model_validate(new_delta)),
            )

            # Verify: storage service delete_media was called for the orphaned media
            mock_instance.delete_media.assert_called_once()
            call_args = mock_instance.delete_media.call_args

            # Verify the deleted media is the first one
            assert call_args[1]["user_id"] == str(user.id)
            assert call_args[1]["force"] is False

        # Verify: media record was deleted from database
        remaining_media = session.query(EntryMedia).filter(
            EntryMedia.entry_id == entry.id
        ).all()
        assert len(remaining_media) == 1
        assert remaining_media[0].id == media_id_2

    def test_delete_orphaned_media_with_thumbnail(self):
        """Test that orphaned media with thumbnails is properly handled."""
        session = _setup_session()
        user = _create_user(session)
        journal = _create_journal(session, user.id)

        media_id_1 = uuid.uuid4()
        media_id_2 = uuid.uuid4()

        entry = _create_entry_with_media(
            session,
            user.id,
            journal.id,
            media_ids=[media_id_1, media_id_2],
        )

        # Add thumbnail path to the first media (the one we'll delete)
        media = session.query(EntryMedia).filter(EntryMedia.id == media_id_1).first()
        media.thumbnail_path = f"user/{user.id}/images/thumbnails/thumb-image.jpg"
        session.add(media)
        session.commit()

        service = EntryService(session)

        # Update delta to remove the first media (keep the second one)
        new_delta = {
            "ops": [
                {"insert": "Test content\n"},
                {"insert": {"image": str(media_id_2)}},
                {"insert": "\n"},
            ]
        }

        with patch(
            "app.services.media_storage_service.MediaStorageService"
        ) as mock_storage_service:
            mock_instance = MagicMock()
            mock_storage_service.return_value = mock_instance

            service.update_entry(
                entry.id,
                user.id,
                EntryUpdate(content_delta=QuillDelta.model_validate(new_delta)),
            )

            # Verify: delete_media was called for the orphaned media
            mock_instance.delete_media.assert_called_once()

        # Verify: the first media (with thumbnail) was deleted from database
        remaining_media = session.query(EntryMedia).filter(
            EntryMedia.entry_id == entry.id
        ).all()
        assert len(remaining_media) == 1
        assert remaining_media[0].id == media_id_2

        # Verify: the deleted media had a thumbnail path
        deleted_media = session.query(EntryMedia).filter(EntryMedia.id == media_id_1).first()
        assert deleted_media is None  # It was deleted

    def test_no_deletion_when_media_not_removed(self):
        """Test that media is not deleted if it's still in the delta."""
        session = _setup_session()
        user = _create_user(session)
        journal = _create_journal(session, user.id)

        media_id = uuid.uuid4()

        entry = _create_entry_with_media(
            session,
            user.id,
            journal.id,
            media_ids=[media_id],
        )

        service = EntryService(session)

        # Update delta but keep the same media
        new_delta = {
            "ops": [
                {"insert": "Updated content\n"},
                {"insert": {"image": str(media_id)}},
                {"insert": "\n"},
            ]
        }

        with patch(
            "app.services.media_storage_service.MediaStorageService"
        ) as mock_storage_service:
            mock_instance = MagicMock()
            mock_storage_service.return_value = mock_instance

            service.update_entry(
                entry.id,
                user.id,
                EntryUpdate(content_delta=QuillDelta.model_validate(new_delta)),
            )

            # Verify: delete_media was NOT called
            mock_instance.delete_media.assert_not_called()

        # Verify: media record still exists
        remaining_media = session.query(EntryMedia).filter(
            EntryMedia.entry_id == entry.id
        ).all()
        assert len(remaining_media) == 1
        assert remaining_media[0].id == media_id

    def test_multiple_orphaned_media_deleted(self):
        """Test that multiple media files are deleted when all removed from delta."""
        session = _setup_session()
        user = _create_user(session)
        journal = _create_journal(session, user.id)

        media_ids = [uuid.uuid4() for _ in range(3)]

        entry = _create_entry_with_media(
            session,
            user.id,
            journal.id,
            media_ids=media_ids,
        )

        service = EntryService(session)

        # Update delta to remove all media
        new_delta = {"ops": [{"insert": "Text only, no media\n"}]}

        with patch(
            "app.services.media_storage_service.MediaStorageService"
        ) as mock_storage_service:
            mock_instance = MagicMock()
            mock_storage_service.return_value = mock_instance

            service.update_entry(
                entry.id,
                user.id,
                EntryUpdate(content_delta=QuillDelta.model_validate(new_delta)),
            )

            # Verify: delete_media was called 3 times (once for each media)
            assert mock_instance.delete_media.call_count == 3

        # Verify: all media records were deleted
        remaining_media = session.query(EntryMedia).filter(
            EntryMedia.entry_id == entry.id
        ).all()
        assert len(remaining_media) == 0

    def test_orphaned_media_deletion_handles_missing_checksum(self):
        """Test that media without checksum is force deleted (legacy records)."""
        session = _setup_session()
        user = _create_user(session)
        journal = _create_journal(session, user.id)

        media_id = uuid.uuid4()
        entry = _create_entry_with_media(
            session,
            user.id,
            journal.id,
            media_ids=[media_id],
        )

        # Remove checksum from media to simulate old records
        media = session.query(EntryMedia).filter(EntryMedia.id == media_id).first()
        media.checksum = None
        session.add(media)
        session.commit()

        service = EntryService(session)

        # Update delta to remove the media
        new_delta = {"ops": [{"insert": "Text only\n"}]}

        with patch(
            "app.services.media_storage_service.MediaStorageService"
        ) as mock_storage_service:
            mock_instance = MagicMock()
            mock_storage_service.return_value = mock_instance

            service.update_entry(
                entry.id,
                user.id,
                EntryUpdate(content_delta=QuillDelta.model_validate(new_delta)),
            )

            # Verify: delete_media WAS called with force=True (legacy record handling)
            mock_instance.delete_media.assert_called_once()
            call_args = mock_instance.delete_media.call_args
            assert call_args[1]["force"] is True
            assert call_args[1]["checksum"] is None

        # Verify: media record was deleted from database
        remaining_media = session.query(EntryMedia).filter(
            EntryMedia.entry_id == entry.id
        ).all()
        assert len(remaining_media) == 0

    def test_orphaned_media_deletion_is_atomic_with_update(self):
        """Test that media deletion is part of the same transaction as entry update."""
        session = _setup_session()
        user = _create_user(session)
        journal = _create_journal(session, user.id)

        media_id = uuid.uuid4()
        entry = _create_entry_with_media(
            session,
            user.id,
            journal.id,
            media_ids=[media_id],
        )

        new_title = "Updated Title"

        service = EntryService(session)

        # Update both title and delta (removing media)
        new_delta = {"ops": [{"insert": "New content\n"}]}

        with patch(
            "app.services.media_storage_service.MediaStorageService"
        ) as mock_storage_service:
            mock_instance = MagicMock()
            mock_storage_service.return_value = mock_instance

            updated_entry = service.update_entry(
                entry.id,
                user.id,
                EntryUpdate(
                    title=new_title,
                    content_delta=QuillDelta.model_validate(new_delta),
                ),
            )

            # Verify both changes were applied
            assert updated_entry.title == new_title
            # Compare the ops content (Pydantic may add attributes=None)
            assert len(updated_entry.content_delta["ops"]) == 1
            assert updated_entry.content_delta["ops"][0]["insert"] == new_delta["ops"][0]["insert"]

            # Verify media deletion was called
            mock_instance.delete_media.assert_called_once()

        # Verify database state is consistent
        db_entry = session.query(Entry).filter(Entry.id == entry.id).first()
        assert db_entry.title == new_title

        db_media = session.query(EntryMedia).filter(
            EntryMedia.entry_id == entry.id
        ).all()
        assert len(db_media) == 0

    def test_finalize_entry_does_not_trigger_deletion(self):
        """Test that finalizing a draft entry doesn't trigger orphaned media deletion."""
        session = _setup_session()
        user = _create_user(session)
        journal = _create_journal(session, user.id)

        media_id = uuid.uuid4()

        # Create a draft entry with media
        draft_entry = Entry(
            user_id=user.id,
            journal_id=journal.id,
            title="Draft Entry",
            content_delta={"ops": [{"insert": {"image": "file-path-1.jpg"}}, {"insert": "\n"}]},
            content_plain_text="",
            entry_date=date.today(),
            entry_timezone="UTC",
            entry_datetime_utc=utc_now(),
            is_draft=True,
        )
        session.add(draft_entry)
        session.commit()
        session.refresh(draft_entry)

        media = EntryMedia(
            id=media_id,
            entry_id=draft_entry.id,
            media_type="image",
            file_path=f"user/{user.id}/images/file-path-1.jpg",
            original_filename="image-1.jpg",
            file_size=1024,
            mime_type="image/jpeg",
            checksum="checksum-1",
            upload_status="COMPLETED",
        )
        session.add(media)
        session.commit()

        service = EntryService(session)

        with patch(
            "app.services.media_storage_service.MediaStorageService"
        ) as mock_storage_service:
            mock_instance = MagicMock()
            mock_storage_service.return_value = mock_instance

            # Finalize the entry (doesn't change delta, just marks as published)
            finalized = service.finalize_entry(draft_entry.id, user.id)

            # Verify: is_draft was changed to False
            assert finalized.is_draft is False

            # Verify: delete_media was NOT called (no delta update)
            mock_instance.delete_media.assert_not_called()

        # Verify: media still exists
        remaining_media = session.query(EntryMedia).filter(
            EntryMedia.entry_id == draft_entry.id
        ).all()
        assert len(remaining_media) == 1


class TestOrphanedMediaDeletionEdgeCases:
    """Test edge cases for orphaned media deletion."""

    def test_deletion_with_empty_old_delta(self):
        """Test that deletion gracefully handles entry with no previous content."""
        session = _setup_session()
        user = _create_user(session)
        journal = _create_journal(session, user.id)

        # Create entry with empty delta
        entry = Entry(
            user_id=user.id,
            journal_id=journal.id,
            title="Empty Entry",
            content_delta=None,
            entry_date=date.today(),
            entry_timezone="UTC",
            entry_datetime_utc=utc_now(),
            is_draft=False,
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)

        service = EntryService(session)

        new_delta = {"ops": [{"insert": "Now has content\n"}]}

        with patch(
            "app.services.media_storage_service.MediaStorageService"
        ) as mock_storage_service:
            mock_instance = MagicMock()
            mock_storage_service.return_value = mock_instance

            # This should not raise an error
            service.update_entry(
                entry.id,
                user.id,
                EntryUpdate(content_delta=QuillDelta.model_validate(new_delta)),
            )

            # Verify: delete_media was not called (no old media to delete)
            mock_instance.delete_media.assert_not_called()

    def test_deletion_with_empty_new_delta(self):
        """Test that deletion gracefully handles empty new delta."""
        session = _setup_session()
        user = _create_user(session)
        journal = _create_journal(session, user.id)

        media_id = uuid.uuid4()
        entry = _create_entry_with_media(
            session,
            user.id,
            journal.id,
            media_ids=[media_id],
        )

        service = EntryService(session)

        # Update with empty delta
        new_delta = {"ops": []}

        with patch(
            "app.services.media_storage_service.MediaStorageService"
        ) as mock_storage_service:
            mock_instance = MagicMock()
            mock_storage_service.return_value = mock_instance

            service.update_entry(
                entry.id,
                user.id,
                EntryUpdate(content_delta=QuillDelta.model_validate(new_delta)),
            )

            # Verify: delete_media was called for the orphaned media
            mock_instance.delete_media.assert_called_once()

    def test_deletion_skips_media_without_matching_record(self):
        """Test that deletion gracefully handles orphaned sources with no DB record."""
        session = _setup_session()
        user = _create_user(session)
        journal = _create_journal(session, user.id)

        media_id = uuid.uuid4()
        entry = _create_entry_with_media(
            session,
            user.id,
            journal.id,
            media_ids=[media_id],
        )

        service = EntryService(session)

        # Update delta with a source that has no matching media record
        new_delta = {"ops": [{"insert": "content\n"}]}

        with patch(
            "app.services.media_storage_service.MediaStorageService"
        ) as mock_storage_service:
            mock_instance = MagicMock()
            mock_storage_service.return_value = mock_instance

            # This should handle the case gracefully
            service.update_entry(
                entry.id,
                user.id,
                EntryUpdate(content_delta=QuillDelta.model_validate(new_delta)),
            )

            # Verify: delete_media was called once for the one media we have
            mock_instance.delete_media.assert_called_once()
