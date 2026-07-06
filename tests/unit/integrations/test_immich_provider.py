
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from immichpy.client.generated import AssetMediaSize, AssetOrder
from immichpy.client.generated.exceptions import NotFoundException

from app.integrations import immich
from app.models.integration import AssetType, Integration, IntegrationProvider
from app.models.user import User

ASSET_ID = "11111111-1111-1111-1111-111111111111"
ASSET_ID2 = "22222222-2222-2222-2222-222222222222"
ALBUM_ID = "33333333-3333-3333-3333-333333333333"


def _dto(payload: dict) -> MagicMock:
    """Stand-in for an immichpy DTO: `_dump()` only calls `.to_json()`."""
    model = MagicMock()
    model.to_json.return_value = json.dumps(payload)
    return model


def _patch_client(client: MagicMock):
    """Patch the immichpy client factory to return the given mock client."""
    return patch("app.integrations.immich._client", return_value=client)


class TestImmichProvider:

    @pytest.mark.asyncio
    async def test_list_assets_requests_sorted_live_response(self):
        """list_assets should request descending order via MetadataSearchDto."""
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

        search_response = MagicMock()
        search_response.assets.items = []
        search_response.assets.total = 0
        search_response.assets.count = 0

        client = MagicMock()
        client.search.search_assets = AsyncMock(return_value=search_response)

        with patch("app.integrations.immich._get_cache") as mock_cache_get:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None  # Force live fetch
            mock_cache_get.return_value = mock_cache

            with _patch_client(client):
                with patch("app.integrations.immich.decrypt_token", return_value="key"):
                    await immich.list_assets(
                        session=MagicMock(),
                        user=mock_user,
                        integration=mock_integration,
                        page=1,
                    )

            dto = client.search.search_assets.call_args.args[0]
            assert dto.order == AssetOrder.DESC

    @pytest.mark.asyncio
    async def test_ensure_album_exists_found_existing(self):
        """ensure_album_exists returns ID when album already exists."""
        with patch("app.integrations.immich.get_album_id_by_name", new_callable=AsyncMock) as mock_get_id:
            mock_get_id.return_value = "existing-uuid"

            result = await immich.ensure_album_exists("http://immich.test", "test-key", "Journiv")

            assert result == "existing-uuid"
            mock_get_id.assert_called_once_with("http://immich.test", "test-key", "Journiv")

    @pytest.mark.asyncio
    async def test_ensure_album_exists_create_new(self):
        """ensure_album_exists creates a new album when not found."""
        with patch("app.integrations.immich.get_album_id_by_name", new_callable=AsyncMock) as mock_get_id:
            mock_get_id.return_value = None

            with patch("app.integrations.immich.create_album", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = "new-uuid"

                result = await immich.ensure_album_exists("http://immich.test", "test-key", "Journiv")

                assert result == "new-uuid"
                mock_create.assert_called_once_with("http://immich.test", "test-key", "Journiv")

    @pytest.mark.asyncio
    async def test_ensure_album_exists_race_condition(self):
        """ensure_album_exists handles a create race (fails, then finds it)."""
        with patch("app.integrations.immich.get_album_id_by_name", new_callable=AsyncMock) as mock_get_id:
            mock_get_id.side_effect = [None, "race-uuid"]

            with patch("app.integrations.immich.create_album", new_callable=AsyncMock) as mock_create:
                mock_create.side_effect = ValueError("Album already exists")

                result = await immich.ensure_album_exists("http://immich.test", "test-key", "Journiv")

                assert result == "race-uuid"
                assert mock_get_id.call_count == 2
                mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_album_id_by_name_found(self):
        """get_album_id_by_name matches on album_name and returns the id."""
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
        """get_album_id_by_name returns None when no album matches."""
        client = MagicMock()
        client.albums.get_all_albums = AsyncMock(
            return_value=[MagicMock(id="id-1", album_name="Other Album")]
        )

        with _patch_client(client):
            result = await immich.get_album_id_by_name("http://immich.test", "test-key", "Non Existent")

        assert result is None

    @pytest.mark.asyncio
    async def test_create_album_success(self):
        """create_album returns the new album id and sends the album name."""
        client = MagicMock()
        client.albums.create_album = AsyncMock(return_value=MagicMock(id="new-uuid"))

        with _patch_client(client):
            result = await immich.create_album("http://immich.test", "test-key", "New Album")

        assert result == "new-uuid"
        dto = client.albums.create_album.call_args.args[0]
        assert dto.album_name == "New Album"

    @pytest.mark.asyncio
    async def test_add_assets_to_album(self):
        """add_assets_to_album passes UUIDs to the immichpy client."""
        client = MagicMock()
        client.albums.add_assets_to_album = AsyncMock()

        with _patch_client(client):
            await immich.add_assets_to_album(
                "http://immich.test", "test-key", ALBUM_ID, [ASSET_ID, ASSET_ID2]
            )

        args = client.albums.add_assets_to_album.call_args.args
        assert args[0] == UUID(ALBUM_ID)
        assert args[1].ids == [UUID(ASSET_ID), UUID(ASSET_ID2)]

    def test_get_asset_url_variants(self):
        """URL generation for different asset types (pure, no HTTP)."""
        base_url = "http://immich.test"
        asset_id = "asset-1"

        url = immich.get_asset_url(base_url, asset_id, "original", AssetType.IMAGE)
        assert "/thumbnail?size=preview" in url
        assert asset_id in url

        url = immich.get_asset_url(base_url, asset_id, "original", AssetType.VIDEO)
        assert "/video/playback" in url
        assert asset_id in url

        url = immich.get_asset_url(base_url, asset_id, "thumbnail", AssetType.IMAGE)
        assert "/thumbnail" in url
        assert "size=preview" not in url

    @pytest.mark.asyncio
    async def test_get_asset_info_success(self):
        """get_asset_info returns the dumped asset dict."""
        response_data = {"id": ASSET_ID, "type": "VIDEO"}
        client = MagicMock()
        client.assets.get_asset_info = AsyncMock(return_value=_dto(response_data))

        with _patch_client(client):
            result = await immich.get_asset_info("http://immich.test", "key", ASSET_ID)

        assert result == response_data
        assert client.assets.get_asset_info.call_args.args[0] == UUID(ASSET_ID)

    @pytest.mark.asyncio
    async def test_get_asset_info_fallback(self):
        """get_asset_info falls back to metadata search on 404."""
        response_data = {"id": ASSET_ID, "type": "VIDEO"}
        search_response = MagicMock()
        search_response.assets.items = [_dto(response_data)]

        client = MagicMock()
        client.assets.get_asset_info = AsyncMock(side_effect=NotFoundException(status=404))
        client.search.search_assets = AsyncMock(return_value=search_response)

        with _patch_client(client):
            result = await immich.get_asset_info("http://immich.test", "key", ASSET_ID)

        assert result == response_data
        assert client.search.search_assets.call_args.args[0].id == UUID(ASSET_ID)

    @pytest.mark.asyncio
    async def test_get_asset_info_failure(self):
        """get_asset_info returns an empty dict on unexpected errors."""
        client = MagicMock()
        client.assets.get_asset_info = AsyncMock(side_effect=RuntimeError("boom"))

        with _patch_client(client):
            result = await immich.get_asset_info("http://immich.test", "key", ASSET_ID)

        assert result == {}


class _FakeAioResp:
    """Minimal aiohttp.ClientResponse stand-in for the streaming download helpers."""

    def __init__(self, body: bytes = b""):
        self.status = 200
        self.reason = "OK"
        self.headers: dict = {}
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self) -> bytes:
        return self._body

    @property
    def content(self):
        body = self._body

        class _Stream:
            async def iter_chunked(self, n):
                for i in range(0, len(body), n):
                    yield body[i:i + n]

        return _Stream()


class TestImmichDownloadHelpers:
    """Cover journiv's own download wiring (UUID conversion, streaming, bytes).

    The status->exception mapping is immichpy's (ApiException.from_response) and
    is not re-tested here.
    """

    @pytest.mark.asyncio
    async def test_download_media_bytes_returns_body(self):
        client = MagicMock()
        client.assets.view_asset_without_preload_content = AsyncMock(
            return_value=_FakeAioResp(b"IMG")
        )

        with _patch_client(client):
            data = await immich.download_media_bytes(
                "http://immich.test", "key", ASSET_ID, AssetMediaSize.THUMBNAIL
            )

        assert data == b"IMG"
        call = client.assets.view_asset_without_preload_content.call_args
        assert call.args[0] == UUID(ASSET_ID)
        assert call.kwargs["size"] == AssetMediaSize.THUMBNAIL

    @pytest.mark.asyncio
    async def test_download_original_to_file_streams_to_disk(self, tmp_path):
        client = MagicMock()
        client.assets.download_asset_without_preload_content = AsyncMock(
            return_value=_FakeAioResp(b"V" * 1_500_000)
        )
        dest = tmp_path / "original"

        with _patch_client(client):
            await immich.download_original_to_file("http://immich.test", "key", ASSET_ID, dest)

        assert dest.read_bytes() == b"V" * 1_500_000
        assert client.assets.download_asset_without_preload_content.call_args.args[0] == UUID(ASSET_ID)
