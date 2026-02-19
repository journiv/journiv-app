"""Unit tests for EntryService Immich integration behavior."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.entry import Entry
from app.models.moment import MomentMedia
from app.models.moment import Moment
from app.services.entry_service import EntryService


@pytest.fixture
def mock_services():
    with patch('app.core.celery_app.celery_app') as mock_celery, \
         patch('app.services.media_service.MediaService'), \
         patch('app.services.journal_service.JournalService'), \
         patch('app.services.analytics_service.AnalyticsService'):
        yield mock_celery


class TestEntryServiceImmichAssetRemoval:
    """Test Immich asset removal logic under moment-first architecture."""

    def test_delete_entry_with_shared_immich_assets(self, mock_services):
        """
        Deleting an entry should not enqueue Immich asset removal.

        In moment-first architecture, deleting an entry reverts to a quick log:
        the moment (and its media) remain intact.
        """
        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        entry_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        journal_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        moment_id = uuid.UUID("33333333-3333-3333-3333-333333333333")

        mock_session = MagicMock()

        mock_entry = Entry(
            id=entry_id,
            user_id=user_id,
            journal_id=journal_id,
            moment_id=moment_id,
            title="Test Entry",
            content="Test content",
            content_delta={},
        )
        mock_entry.moment = Moment(id=moment_id, user_id=user_id, logged_at_utc=datetime.now(timezone.utc))

        mock_session.exec.return_value.first.return_value = mock_entry

        service = EntryService(mock_session)
        service.delete_entry(entry_id, user_id)
        mock_services.send_task.assert_not_called()

    def test_delete_entry_with_only_unique_immich_assets(self, mock_services):
        """
        Deleting an entry should not enqueue Immich asset removal, even when
        moment media would be unique to that moment.
        """
        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        entry_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        journal_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        moment_id = uuid.UUID("44444444-4444-4444-4444-444444444444")

        mock_session = MagicMock()

        mock_entry = Entry(
            id=entry_id,
            user_id=user_id,
            journal_id=journal_id,
            moment_id=moment_id,
            title="Test Entry",
            content="Test content",
            content_delta={},
        )
        mock_entry.moment = Moment(id=moment_id, user_id=user_id, logged_at_utc=datetime.now(timezone.utc))

        mock_session.exec.return_value.first.return_value = mock_entry

        service = EntryService(mock_session)
        service.delete_entry(entry_id, user_id)
        mock_services.send_task.assert_not_called()

    def test_delete_entry_media_with_shared_asset(self, mock_services):
        """
        Test that when deleting a single media item that uses a shared asset,
        the asset is NOT removed from the album.
        """
        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        media_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        moment_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
        shared_asset_id = "shared-asset-789"

        mock_session = MagicMock()

        mock_media = MomentMedia(
            id=media_id,
            moment_id=moment_id,
            external_provider="immich",
            external_asset_id=shared_asset_id,
            media_type="image",
            mime_type="image/jpeg",
            file_path=None,
        )

        # Setup mock returns
        # delete_entry_media calls _get_owned_entry which calls session.exec
        mock_session.exec.side_effect = [
            MagicMock(first=MagicMock(return_value=mock_media)),  # Get media
            MagicMock(one=MagicMock(return_value=1)),  # Count query: 1 other occurrence
        ]

        service = EntryService(mock_session)

        # Execute
        service.delete_entry_media(media_id, user_id)

        # Verify: NO task should be sent since asset is shared
        mock_services.send_task.assert_not_called()

    def test_delete_entry_media_with_unique_asset(self, mock_services):
        """
        Test that when deleting a single media item with a unique asset,
        the asset IS removed from the album.
        """
        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        media_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        moment_id = uuid.UUID("66666666-6666-6666-6666-666666666666")
        unique_asset_id = "unique-asset-999"

        mock_session = MagicMock()

        mock_media = MomentMedia(
            id=media_id,
            moment_id=moment_id,
            external_provider="immich",
            external_asset_id=unique_asset_id,
            media_type="image",
            mime_type="image/jpeg",
            file_path=None,
        )

        # Setup mock returns
        mock_session.exec.side_effect = [
            MagicMock(first=MagicMock(return_value=mock_media)),  # Get media
            MagicMock(one=MagicMock(return_value=0)),  # Count query: 0 other occurrences
        ]

        service = EntryService(mock_session)

        # Execute
        service.delete_entry_media(media_id, user_id)

        # Verify: task should be sent to remove asset
        mock_services.send_task.assert_called_once()
        call_args = mock_services.send_task.call_args
        task_args = call_args[1]['args']

        assert task_args[0] == str(user_id)
        assert task_args[1] == "immich"
        assert unique_asset_id in task_args[2]
