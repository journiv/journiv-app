
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.integrations import immich

ALBUM_ID = "33333333-3333-3333-3333-333333333333"
ASSET_ID = "11111111-1111-1111-1111-111111111111"
ASSET_ID2 = "22222222-2222-2222-2222-222222222222"


def _patch_client(client: MagicMock):
    return patch("app.integrations.immich._client", return_value=client)


class TestImmichAlbum:

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
        albums = [
            MagicMock(id="id-1", album_name="Other Album"),
            MagicMock(id="target-id", album_name="Target Album"),
            MagicMock(id="id-2", album_name="Another Album"),
        ]
        client = MagicMock()
        client.albums.get_all_albums = AsyncMock(return_value=albums)

        with _patch_client(client):
            result = await immich.get_album_id_by_name("http://immich.test", "test-key", "Target Album")

        assert result == "target-id"
        client.albums.get_all_albums.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_album_id_by_name_not_found(self):
        """Test get_album_id_by_name returns None if not found."""
        client = MagicMock()
        client.albums.get_all_albums = AsyncMock(
            return_value=[MagicMock(id="id-1", album_name="Other Album")]
        )

        with _patch_client(client):
            result = await immich.get_album_id_by_name("http://immich.test", "test-key", "Non Existent")

        assert result is None

    @pytest.mark.asyncio
    async def test_create_album_success(self):
        """Test create_album returns the new id and sends the album name."""
        client = MagicMock()
        client.albums.create_album = AsyncMock(return_value=MagicMock(id="new-uuid"))

        with _patch_client(client):
            result = await immich.create_album("http://immich.test", "test-key", "New Album")

        assert result == "new-uuid"
        assert client.albums.create_album.call_args.args[0].album_name == "New Album"

    @pytest.mark.asyncio
    async def test_add_assets_to_album(self):
        """Test add_assets_to_album passes UUIDs to the immichpy client."""
        client = MagicMock()
        client.albums.add_assets_to_album = AsyncMock()

        with _patch_client(client):
            await immich.add_assets_to_album(
                "http://immich.test", "test-key", ALBUM_ID, [ASSET_ID, ASSET_ID2]
            )

        args = client.albums.add_assets_to_album.call_args.args
        assert args[0] == UUID(ALBUM_ID)
        assert args[1].ids == [UUID(ASSET_ID), UUID(ASSET_ID2)]
