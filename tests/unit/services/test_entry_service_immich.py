"""
Unit tests for entry service Immich integration functionality.

Tests verify that Immich linked assets are correctly managed when entries are deleted,
ensuring assets shared across multiple entries are not removed from the album prematurely.
"""
import pytest
import uuid
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone

from app.services.entry_service import EntryService
from app.models.entry import Entry, EntryMedia


class TestEntryServiceImmichAssetRemoval:
    """Test Immich asset removal logic when deleting entries."""

    @pytest.mark.asyncio
    async def test_delete_entry_with_shared_immich_assets(self):
        """
        Test that when deleting an entry with Immich assets that are also used
        in other entries, those assets are NOT removed from the album.
        """
        # Setup
        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        entry_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        journal_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

        shared_asset_id = "shared-asset-123"
        unique_asset_id = "unique-asset-456"

        # Mock session
        mock_session = MagicMock()

        # Mock entry
        mock_entry = Entry(
            id=entry_id,
            user_id=user_id,
            journal_id=journal_id,
            title="Test Entry",
            content="Test content",
            entry_date=datetime.now(timezone.utc).date(),
            entry_datetime_utc=datetime.now(timezone.utc),
            entry_timezone="UTC"
        )

        # Mock media records for this entry
        media1 = EntryMedia(
            id=uuid.uuid4(),
            entry_id=entry_id,
            external_provider="immich",
            external_asset_id=shared_asset_id,
            media_type="image",
            mime_type="image/jpeg",
            file_path=None  # Link only
        )
        media2 = EntryMedia(
            id=uuid.uuid4(),
            entry_id=entry_id,
            external_provider="immich",
            external_asset_id=unique_asset_id,
            media_type="image",
            mime_type="image/jpeg",
            file_path=None  # Link only
        )

        # Setup mock returns
        exec_results = [
            mock_entry,  # _get_owned_entry call
            [media1, media2],  # Get media records for the entry
            [(shared_asset_id, 1)],  # Count query: shared_asset_id has 1 other occurrence
            [],  # Get tag links
        ]
        mock_session.exec.side_effect = [MagicMock(first=MagicMock(return_value=r)) if not isinstance(r, list)
                                          else MagicMock(all=MagicMock(return_value=r))
                                          for r in exec_results]

        # Mock celery task
        with patch('app.core.celery_app.celery_app') as mock_celery:
            with patch('app.services.media_service.MediaService'):
                with patch('app.services.journal_service.JournalService'):
                    with patch('app.services.analytics_service.AnalyticsService'):
                        service = EntryService(mock_session)

                        # Execute
                        await service.delete_entry(entry_id, user_id)

                        # Verify: only the unique asset should be queued for removal
                        mock_celery.send_task.assert_called_once()
                        call_args = mock_celery.send_task.call_args

                        assert call_args[0][0] == "app.integrations.tasks.remove_assets_from_album_task"
                        # Args: [user_id, "immich", [asset_ids]]
                        task_args = call_args[1]['args']
                        assert task_args[0] == str(user_id)
                        assert task_args[1] == "immich"
                        # Only unique_asset_id should be in the list
                        assert unique_asset_id in task_args[2]
                        assert shared_asset_id not in task_args[2]

    @pytest.mark.asyncio
    async def test_delete_entry_with_only_unique_immich_assets(self):
        """
        Test that when deleting an entry where all Immich assets are unique
        (not used elsewhere), all assets are removed from the album.
        """
        # Setup
        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        entry_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        journal_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

        asset_id_1 = "unique-asset-1"
        asset_id_2 = "unique-asset-2"

        # Mock session
        mock_session = MagicMock()

        # Mock entry
        mock_entry = Entry(
            id=entry_id,
            user_id=user_id,
            journal_id=journal_id,
            title="Test Entry",
            content="Test content",
            entry_date=datetime.now(timezone.utc).date(),
            entry_datetime_utc=datetime.now(timezone.utc),
            entry_timezone="UTC"
        )

        # Mock media records
        media1 = EntryMedia(
            id=uuid.uuid4(),
            entry_id=entry_id,
            external_provider="immich",
            external_asset_id=asset_id_1,
            media_type="image",
            mime_type="image/jpeg",
            file_path=None
        )
        media2 = EntryMedia(
            id=uuid.uuid4(),
            entry_id=entry_id,
            external_provider="immich",
            external_asset_id=asset_id_2,
            media_type="image",
            mime_type="image/jpeg",
            file_path=None
        )

        # Setup mock returns
        exec_results = [
            mock_entry,  # _get_owned_entry
            [media1, media2],  # Get media records
            [],  # Count query: no assets found in other entries
            [],  # Get tag links
        ]
        mock_session.exec.side_effect = [MagicMock(first=MagicMock(return_value=r)) if not isinstance(r, list)
                                          else MagicMock(all=MagicMock(return_value=r))
                                          for r in exec_results]

        # Mock celery task
        with patch('app.core.celery_app.celery_app') as mock_celery:
            with patch('app.services.media_service.MediaService'):
                with patch('app.services.journal_service.JournalService'):
                    with patch('app.services.analytics_service.AnalyticsService'):
                        service = EntryService(mock_session)

                        # Execute
                        await service.delete_entry(entry_id, user_id)

                        # Verify: both assets should be queued for removal
                        mock_celery.send_task.assert_called_once()
                        call_args = mock_celery.send_task.call_args
                        task_args = call_args[1]['args']

                        # Both assets should be in the removal list
                        assert asset_id_1 in task_args[2]
                        assert asset_id_2 in task_args[2]
                        assert len(task_args[2]) == 2

    @pytest.mark.asyncio
    async def test_delete_entry_media_with_shared_asset(self):
        """
        Test that when deleting a single media item that uses a shared asset,
        the asset is NOT removed from the album.
        """
        # Setup
        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        media_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        shared_asset_id = "shared-asset-789"

        # Mock session
        mock_session = MagicMock()

        # Mock media record
        mock_media = EntryMedia(
            id=media_id,
            entry_id=uuid.uuid4(),
            external_provider="immich",
            external_asset_id=shared_asset_id,
            media_type="image",
            mime_type="image/jpeg",
            file_path=None
        )

        # Setup mock returns
        mock_session.exec.side_effect = [
            MagicMock(first=MagicMock(return_value=mock_media)),  # Get media
            MagicMock(one=MagicMock(return_value=1)),  # Count query: 1 other occurrence
        ]

        # Mock celery task
        with patch('app.core.celery_app.celery_app') as mock_celery:
            service = EntryService(mock_session)

            # Execute
            service.delete_entry_media(media_id, user_id)

            # Verify: NO task should be sent since asset is shared
            mock_celery.send_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_entry_media_with_unique_asset(self):
        """
        Test that when deleting a single media item with a unique asset,
        the asset IS removed from the album.
        """
        # Setup
        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        media_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        unique_asset_id = "unique-asset-999"

        # Mock session
        mock_session = MagicMock()

        # Mock media record
        mock_media = EntryMedia(
            id=media_id,
            entry_id=uuid.uuid4(),
            external_provider="immich",
            external_asset_id=unique_asset_id,
            media_type="image",
            mime_type="image/jpeg",
            file_path=None
        )

        # Setup mock returns
        mock_session.exec.side_effect = [
            MagicMock(first=MagicMock(return_value=mock_media)),  # Get media
            MagicMock(one=MagicMock(return_value=0)),  # Count query: 0 other occurrences
        ]

        # Mock celery task
        with patch('app.core.celery_app.celery_app') as mock_celery:
            service = EntryService(mock_session)

            # Execute
            service.delete_entry_media(media_id, user_id)

            # Verify: task should be sent to remove asset
            mock_celery.send_task.assert_called_once()
            call_args = mock_celery.send_task.call_args
            task_args = call_args[1]['args']

            assert task_args[0] == str(user_id)
            assert task_args[1] == "immich"
            assert unique_asset_id in task_args[2]
