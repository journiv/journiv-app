
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.integrations import immich
from app.models.integration import Integration, IntegrationProvider
from app.models.user import User

class TestImmichProvider:

    @pytest.mark.asyncio
    async def test_list_assets_requests_sorted_live_response(self):
        """Test that list_assets requests descending order from API."""
        # Setup Mocks
        mock_user = User(id="00000000-0000-0000-0000-000000000000")
        mock_integration = Integration(
            id="00000000-0000-0000-0000-000000000000",
            user_id="00000000-0000-0000-0000-000000000000",
            provider=IntegrationProvider.IMMICH,
            is_active=True,
            base_url="http://immich",
            access_token_encrypted="enc",
            external_user_id="immich-user-1",
        )

        response_json = {
            "assets": {"items": [], "total": 0}
        }

        # Mock dependencies
        with patch("app.integrations.immich._get_cache") as mock_cache_get:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None # Force live fetch
            mock_cache_get.return_value = mock_cache


            with patch("app.integrations.immich._get_client") as mock_client_get:
                mock_client = AsyncMock()
                # Ensure the response object is a regular MagicMock, not Async
                mock_response = MagicMock()
                mock_response.json.return_value = response_json
                mock_response.raise_for_status = MagicMock()

                mock_client.post.return_value = mock_response
                mock_client_get.return_value = mock_client

                with patch("app.integrations.immich.decrypt_token", return_value="key"):
                    # Execute
                    await immich.list_assets(
                        session=MagicMock(),
                        user=mock_user,
                        integration=mock_integration,
                        page=1
                    )

                    # Verify API call included order: desc
                    call_kwargs = mock_client.post.call_args.kwargs
                    assert call_kwargs['json']['order'] == 'desc'

    @pytest.mark.asyncio
    async def test_ensure_album_exists_found_existing(self):
        """Test ensure_album_exists returns ID when album already exists."""
        base_url = "http://immich.test"
        api_key = "test-key"
        album_name = "Journiv"
        existing_id = "existing-uuid"

        with patch("app.integrations.immich.get_album_id_by_name", new_callable=AsyncMock) as mock_get_id:
            mock_get_id.return_value = existing_id

            # Execute
            result = await immich.ensure_album_exists(base_url, api_key, album_name)

            # Verify
            assert result == existing_id
            mock_get_id.assert_called_once_with(base_url, api_key, album_name)

    @pytest.mark.asyncio
    async def test_ensure_album_exists_create_new(self):
        """Test ensure_album_exists creates new album when not found."""
        base_url = "http://immich.test"
        api_key = "test-key"
        album_name = "Journiv"
        new_id = "new-uuid"

        with patch("app.integrations.immich.get_album_id_by_name", new_callable=AsyncMock) as mock_get_id:
            mock_get_id.return_value = None  # Not found initially

            with patch("app.integrations.immich.create_album", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = new_id

                # Execute
                result = await immich.ensure_album_exists(base_url, api_key, album_name)

                # Verify
                assert result == new_id
                mock_get_id.assert_called_once_with(base_url, api_key, album_name)
                mock_create.assert_called_once_with(base_url, api_key, album_name)

    @pytest.mark.asyncio
    async def test_ensure_album_exists_race_condition(self):
        """Test ensure_album_exists handles race condition (creation fails but exists)."""
        base_url = "http://immich.test"
        api_key = "test-key"
        album_name = "Journiv"
        race_id = "race-uuid"

        with patch("app.integrations.immich.get_album_id_by_name", new_callable=AsyncMock) as mock_get_id:
            # First call -> None (not found), Second call -> ID (found)
            mock_get_id.side_effect = [None, race_id]

            with patch("app.integrations.immich.create_album", new_callable=AsyncMock) as mock_create:
                # Creation fails (e.g. someone else created it in between)
                mock_create.side_effect = ValueError("Album already exists")

                # Execute
                result = await immich.ensure_album_exists(base_url, api_key, album_name)

                # Verify
                assert result == race_id
                assert mock_get_id.call_count == 2
                mock_create.assert_called_once()


    @pytest.mark.asyncio
    async def test_get_album_id_by_name_found(self):
        """Test get_album_id_by_name finds the correct album."""
        base_url = "http://immich.test"
        api_key = "test-key"
        album_name = "Target Album"

        albums_response = [
            {"id": "id-1", "albumName": "Other Album"},
            {"id": "target-id", "albumName": "Target Album"},
            {"id": "id-2", "albumName": "Another Album"},
        ]

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client_cls.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = albums_response
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            # Execute
            result = await immich.get_album_id_by_name(base_url, api_key, album_name)

            # Verify
            assert result == "target-id"
            mock_client.get.assert_called_once()
            assert mock_client.get.call_args[0][0] == f"{base_url}/api/albums"

    @pytest.mark.asyncio
    async def test_get_album_id_by_name_not_found(self):
        """Test get_album_id_by_name returns None if not found."""
        base_url = "http://immich.test"
        api_key = "test-key"
        album_name = "Non Existent"

        albums_response = [
            {"id": "id-1", "albumName": "Other Album"},
        ]

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client_cls.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = albums_response
            mock_client.get.return_value = mock_response

            # Execute
            result = await immich.get_album_id_by_name(base_url, api_key, album_name)

            # Verify
            assert result is None

    @pytest.mark.asyncio
    async def test_create_album_success(self):
        """Test create_album calls correct endpoint."""
        base_url = "http://immich.test"
        api_key = "test-key"
        album_name = "New Album"
        new_id = "new-uuid"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client_cls.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": new_id}
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response

            # Execute
            result = await immich.create_album(base_url, api_key, album_name)

            # Verify
            assert result == new_id
            mock_client.post.assert_called_once()
            args, kwargs = mock_client.post.call_args
            assert args[0] == f"{base_url}/api/albums"
            assert kwargs['json']['albumName'] == album_name

    @pytest.mark.asyncio
    async def test_add_assets_to_album(self):
        """Test add_assets_to_album calls correct endpoint."""
        base_url = "http://immich.test"
        api_key = "test-key"
        album_id = "album-uuid"
        asset_ids = ["asset-1", "asset-2"]

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client_cls.return_value = mock_client

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.put.return_value = mock_response

            # Execute
            await immich.add_assets_to_album(base_url, api_key, album_id, asset_ids)

            # Verify
            mock_client.put.assert_called_once()
            args, kwargs = mock_client.put.call_args
            assert args[0] == f"{base_url}/api/albums/{album_id}/assets"
            assert kwargs['json']['ids'] == asset_ids
