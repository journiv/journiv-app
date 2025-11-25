"""
Entry service for managing journal entries.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from zoneinfo import ZoneInfo

from app.core.exceptions import EntryNotFoundError, JournalNotFoundError, ValidationError
from app.core.logging_config import log_info, log_warning, log_error
from app.core.time_utils import utc_now, local_date_for_user, ensure_utc, to_utc
from app.models.entry import Entry, EntryMedia
from app.models.entry_tag_link import EntryTagLink
from app.models.journal import Journal
from app.schemas.entry import EntryCreate, EntryUpdate, EntryMediaCreate

DEFAULT_ENTRY_PAGE_LIMIT = 50
MAX_ENTRY_PAGE_LIMIT = 100


class EntryService:
    """Service class for entry operations."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        """Normalize pagination limit to valid range."""
        if limit <= 0:
            return DEFAULT_ENTRY_PAGE_LIMIT
        return min(limit, MAX_ENTRY_PAGE_LIMIT)

    def _get_owned_entry(self, entry_id: uuid.UUID, user_id: uuid.UUID, *, include_deleted: bool = False) -> Entry:
        statement = select(Entry).where(
            Entry.id == entry_id,
            Entry.user_id == user_id,
        )

        entry = self.session.exec(statement).first()
        if not entry:
            log_warning(f"Entry not found for user {user_id}: {entry_id}")
            raise EntryNotFoundError("Entry not found")
        return entry

    def _commit(self) -> None:
        """Commit database changes with proper error handling."""
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    @staticmethod
    def _derive_entry_date(entry_datetime_utc: datetime, timezone_name: str) -> date:
        """Determine the local date for an entry based on stored timezone."""
        return local_date_for_user(entry_datetime_utc, timezone_name or "UTC")

    def _normalize_entry_timestamp(
        self,
        *,
        entry_date: Optional[date],
        entry_datetime_utc: Optional[datetime],
        entry_timezone: Optional[str],
        fallback_timezone: str
    ) -> tuple[datetime, str, date]:
        timezone_name = (entry_timezone or fallback_timezone or "UTC").strip() or "UTC"

        if entry_datetime_utc is not None:
            normalized_dt = ensure_utc(entry_datetime_utc)
        elif entry_date is not None:
            local_now = datetime.now(ZoneInfo(timezone_name))
            local_dt = datetime.combine(entry_date, local_now.time())
            normalized_dt = to_utc(local_dt, timezone_name)
        else:
            normalized_dt = utc_now()

        derived_date = self._derive_entry_date(normalized_dt, timezone_name)
        return normalized_dt, timezone_name, derived_date

    def _refresh_entry_date(self, entry: Entry) -> None:
        utc_dt = ensure_utc(entry.entry_datetime_utc)
        entry.entry_date = self._derive_entry_date(utc_dt, entry.entry_timezone)

    def create_entry(self, user_id: uuid.UUID, entry_data: EntryCreate) -> Entry:
        """Create a new entry in a journal.

        Args:
            user_id: User ID creating the entry
            entry_data: Entry creation data

        Returns:
            Created entry instance
        """
        # Validate journal exists and belongs to user
        journal_statement = select(Journal).where(
            Journal.id == entry_data.journal_id,
            Journal.user_id == user_id
        )
        journal = self.session.exec(journal_statement).first()
        if not journal:
            log_warning(f"Journal not found for user {user_id}: {entry_data.journal_id}")
            raise JournalNotFoundError("Journal not found")

        # Calculate word count
        word_count = len(entry_data.content.split()) if entry_data.content else 0

        from app.services.user_service import UserService
        user_service = UserService(self.session)
        user_tz = user_service.get_user_timezone(user_id)

        entry_dt_utc, entry_tz, entry_date = self._normalize_entry_timestamp(
            entry_date=entry_data.entry_date,
            entry_datetime_utc=entry_data.entry_datetime_utc,
            entry_timezone=entry_data.entry_timezone,
            fallback_timezone=user_tz
        )

        entry = Entry(
            title=entry_data.title,
            content=entry_data.content,
            entry_date=entry_date,
            entry_datetime_utc=entry_dt_utc,
            entry_timezone=entry_tz,
            location=entry_data.location,
            weather=entry_data.weather,
            journal_id=entry_data.journal_id,
            prompt_id=entry_data.prompt_id,
            word_count=word_count,
            user_id=user_id
        )

        try:
            self.session.add(entry)
            self._commit()
            self.session.refresh(entry)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Entry created for user {user_id} in journal {entry.journal_id}: {entry.id}")

        try:
            from app.services.journal_service import JournalService
            JournalService(self.session).recalculate_journal_entry_count(entry.journal_id, user_id)
        except JournalNotFoundError:
            log_warning(f"Journal missing during entry recount for user {user_id}: {entry.journal_id}")
        except SQLAlchemyError as exc:
            log_error(exc)
        except Exception as exc:
            log_error(exc)

        # Update writing streak analytics
        try:
            from app.services.analytics_service import AnalyticsService
            analytics_service = AnalyticsService(self.session)
            analytics_service.update_writing_streak(user_id, entry.entry_date)
        except Exception as exc:
            log_error(exc)

        return entry

    def get_entry_by_id(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Entry]:
        """Get an entry by ID, ensuring it belongs to the user."""
        statement = select(Entry).where(
            Entry.id == entry_id,
            Entry.user_id == user_id,
        )
        return self.session.exec(statement).first()

    def get_journal_entries(
        self,
        journal_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = DEFAULT_ENTRY_PAGE_LIMIT,
        offset: int = 0,
        include_pinned: bool = True
    ) -> List[Entry]:
        """Get entries for a specific journal."""
        from app.services.journal_service import JournalService
        JournalService(self.session)._get_owned_journal(journal_id, user_id)

        statement = select(Entry).where(
            Entry.journal_id == journal_id,
        )

        if not include_pinned:
            statement = statement.where(Entry.is_pinned.is_(False))

        statement = statement.order_by(
            Entry.is_pinned.desc(),
            Entry.entry_datetime_utc.desc()
        ).offset(offset).limit(limit)

        return list(self.session.exec(statement))

    def get_user_entries(
        self,
        user_id: uuid.UUID,
        limit: int = DEFAULT_ENTRY_PAGE_LIMIT,
        offset: int = 0
    ) -> List[Entry]:
        """Get all entries for a user across all journals."""
        statement = select(Entry).where(
            Entry.user_id == user_id,
        ).order_by(Entry.entry_datetime_utc.desc()).offset(offset).limit(limit)

        return list(self.session.exec(statement))

    def update_entry(self, entry_id: uuid.UUID, user_id: uuid.UUID, entry_data: EntryUpdate) -> Entry:
        """Update an entry."""
        entry = self._get_owned_entry(entry_id, user_id)

        # Handle journal change if requested
        old_journal_id = None
        new_journal_id = None
        if entry_data.journal_id is not None and entry_data.journal_id != entry.journal_id:
            # Validate new journal exists and belongs to user
            new_journal_statement = select(Journal).where(
                Journal.id == entry_data.journal_id,
                Journal.user_id == user_id
            )
            new_journal = self.session.exec(new_journal_statement).first()
            if not new_journal:
                log_warning(f"Target journal not found for user {user_id}: {entry_data.journal_id}")
                raise JournalNotFoundError("Target journal not found")

            # Prevent moving into archived journals
            if new_journal.is_archived:
                log_warning(f"Cannot move entry {entry_id} to archived journal {new_journal.id}")
                raise ValidationError("Cannot move entry to an archived journal")

            # Store old and new journal IDs for stats recalculation
            old_journal_id = entry.journal_id
            new_journal_id = entry_data.journal_id
            entry.journal_id = new_journal_id
            log_info(f"Entry {entry_id} journal changed from {old_journal_id} to {new_journal_id}")

        # Update fields
        if entry_data.title is not None:
            entry.title = entry_data.title
        if entry_data.content is not None:
            entry.content = entry_data.content
            # Recalculate word count
            entry.word_count = len(entry_data.content.split())
        if entry_data.entry_timezone is not None:
            tz_value = (entry_data.entry_timezone or "UTC").strip() or "UTC"
            entry.entry_timezone = tz_value
        timestamp_changed = False

        if entry_data.entry_datetime_utc is not None:
            entry.entry_datetime_utc = ensure_utc(entry_data.entry_datetime_utc)
            timestamp_changed = True

        if entry_data.entry_date is not None:
            timezone_name = entry.entry_timezone or "UTC"
            base_dt = ensure_utc(entry.entry_datetime_utc)
            local_current = base_dt.astimezone(ZoneInfo(timezone_name))
            target_local = datetime.combine(entry_data.entry_date, local_current.time())
            entry.entry_datetime_utc = to_utc(target_local, timezone_name)
            timestamp_changed = True

        if timestamp_changed or entry_data.entry_timezone is not None:
            self._refresh_entry_date(entry)
        if entry_data.location is not None:
            entry.location = entry_data.location
        if entry_data.weather is not None:
            entry.weather = entry_data.weather
        if entry_data.is_pinned is not None:
            entry.is_pinned = entry_data.is_pinned

        entry.updated_at = utc_now()
        try:
            self.session.add(entry)
            self._commit()
            self.session.refresh(entry)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        # Recalculate stats for both journals if journal was changed
        if old_journal_id is not None and new_journal_id is not None:
            try:
                from app.services.journal_service import JournalService
                journal_service = JournalService(self.session)
                # Recalculate old journal stats
                journal_service.recalculate_journal_entry_count(old_journal_id, user_id)
                # Recalculate new journal stats
                journal_service.recalculate_journal_entry_count(new_journal_id, user_id)
            except JournalNotFoundError:
                log_warning(f"Journal missing during entry update recount for user {user_id}")
            except SQLAlchemyError as exc:
                log_error(exc)
            except Exception as exc:
                log_error(exc)

        log_info(f"Entry updated for user {user_id}: {entry.id}")
        return entry

    def delete_entry(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Hard delete an entry and its related records."""
        entry = self._get_owned_entry(entry_id, user_id)

        # Hard delete related EntryMedia records
        media_statement = select(EntryMedia).where(EntryMedia.entry_id == entry_id)
        media_records = self.session.exec(media_statement).all()
        for media in media_records:
            self.session.delete(media)

        # Hard delete related EntryTagLink records
        tag_link_statement = select(EntryTagLink).where(EntryTagLink.entry_id == entry_id)
        tag_link_records = self.session.exec(tag_link_statement).all()
        for tag_link in tag_link_records:
            self.session.delete(tag_link)

        # Store journal_id for recount before deleting entry
        journal_id = entry.journal_id

        # Hard delete the entry
        self.session.delete(entry)

        try:
            self._commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        try:
            from app.services.journal_service import JournalService
            JournalService(self.session).recalculate_journal_entry_count(journal_id, user_id)
        except JournalNotFoundError:
            log_warning(f"Journal missing during entry delete recount for user {user_id}: {journal_id}")
        except SQLAlchemyError as exc:
            log_error(exc)
        except Exception as exc:
            log_error(exc)

        # Recalculate writing streak statistics after entry is deleted
        # This ensures analytics reflect the correct entry counts
        try:
            from app.services.analytics_service import AnalyticsService
            analytics_service = AnalyticsService(self.session)
            analytics_service.recalculate_writing_streak_stats(user_id)
        except Exception as exc:
            # Log error but don't fail the deletion
            log_warning(f"Failed to update writing streak stats after entry deletion: {exc}")

        log_info(f"Entry hard-deleted for user {user_id}: {entry_id}")
        return True

    def toggle_pin(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> Entry:
        """Toggle pin status of an entry."""
        entry = self._get_owned_entry(entry_id, user_id)

        entry.is_pinned = not entry.is_pinned
        entry.updated_at = utc_now()
        try:
            self.session.add(entry)
            self._commit()
            self.session.refresh(entry)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Entry pin toggled for user {user_id}: {entry.id} -> {entry.is_pinned}")
        return entry

    def search_entries(
        self,
        user_id: uuid.UUID,
        query: str,
        journal_id: Optional[uuid.UUID] = None,
        limit: int = DEFAULT_ENTRY_PAGE_LIMIT,
        offset: int = 0
    ) -> List[Entry]:
        """Search entries by content."""
        statement = select(Entry).where(
            Entry.user_id == user_id,
            Entry.content.ilike(f"%{query}%")
        )

        if journal_id:
            statement = statement.where(Entry.journal_id == journal_id)

        statement = statement.order_by(Entry.entry_datetime_utc.desc()).offset(offset).limit(limit)
        return list(self.session.exec(statement))

    def get_entries_by_date_range(
        self,
        user_id: uuid.UUID,
        start_date: date,
        end_date: date,
        journal_id: Optional[uuid.UUID] = None
    ) -> List[Entry]:
        """Get entries within a date range based on entry_date."""
        statement = select(Entry).where(
            Entry.user_id == user_id,
            Entry.entry_date >= start_date,
            Entry.entry_date <= end_date
        )

        if journal_id:
            statement = statement.where(Entry.journal_id == journal_id)

        statement = statement.order_by(Entry.entry_datetime_utc.desc())
        return list(self.session.exec(statement))

    def add_media_to_entry(self, entry_id: uuid.UUID, user_id: uuid.UUID, media_data: EntryMediaCreate) -> EntryMedia:
        """Add media to an entry."""
        # Verify the entry belongs to the user
        self._get_owned_entry(entry_id, user_id)

        media = EntryMedia(
            entry_id=entry_id,
            media_type=media_data.media_type,
            file_path=media_data.file_path,
            original_filename=media_data.original_filename,
            file_size=media_data.file_size,
            mime_type=media_data.mime_type,
            thumbnail_path=media_data.thumbnail_path,
            duration=media_data.duration,
            width=media_data.width,
            height=media_data.height,
            alt_text=media_data.alt_text,
            upload_status=media_data.upload_status,
            file_metadata=media_data.file_metadata,
            checksum=media_data.checksum
        )

        try:
            self.session.add(media)
            self._commit()
            self.session.refresh(media)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Media added to entry {entry_id} for user {user_id}: {media.id}")
        return media

    def get_entry_media(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> List[EntryMedia]:
        """Get all media for an entry."""
        # Verify the entry belongs to the user
        self._get_owned_entry(entry_id, user_id)

        statement = select(EntryMedia).where(
            EntryMedia.entry_id == entry_id,
        )
        return list(self.session.exec(statement))

    def delete_entry_media(self, media_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Soft delete an entry media file.

        Args:
            media_id: Media ID to delete
            user_id: User ID for authorization

        Returns:
            True if deleted successfully

        Raises:
            EntryNotFoundError: If media doesn't exist or doesn't belong to user's entry
        """
        # Get the media and verify it belongs to user's entry
        statement = select(EntryMedia).join(Entry).where(
            EntryMedia.id == media_id,
            Entry.user_id == user_id,
        )
        media = self.session.exec(statement).first()

        if not media:
            raise EntryNotFoundError("Media not found")

        # Hard delete the media
        self.session.delete(media)
        try:
            self._commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Media hard-deleted for user {user_id}: {media.id}")
        return True
