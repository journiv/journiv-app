"""
Regression tests: an Immich asset that no longer exists must proxy as 404.

`get_asset_info` raises `ImmichAssetNotFoundError` once Immich confirms an
asset is gone. `fetch_proxy_asset` looks the asset up on every uncached
"original" request, and neither proxy endpoint caught that error, so a deleted
asset surfaced as a 500 after up to ~3s of retry backoff on the request path.
"""
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.api.v1.endpoints.media as media_module
import app.integrations.router as router_module
from app.integrations import immich
from app.integrations import service as service_module
from app.models.integration import IntegrationProvider


@contextmanager
def _fake_session_context(*_args, **_kwargs):
    yield MagicMock()


@pytest.mark.asyncio
async def test_fetch_proxy_asset_looks_up_type_without_retry_backoff():
    lookup = AsyncMock(side_effect=immich.ImmichAssetNotFoundError("asset-1"))
    with patch.object(
        service_module,
        "get_integration_credentials",
        new=AsyncMock(return_value=("http://immich.test", "encrypted")),
    ), patch.object(service_module, "decrypt_token", return_value="key"), \
         patch.object(immich, "get_cached_asset_type", return_value=None), \
         patch.object(immich, "get_asset_info", new=lookup):
        with pytest.raises(immich.ImmichAssetNotFoundError):
            await service_module.fetch_proxy_asset(
                user_id=uuid4(),
                provider=IntegrationProvider.IMMICH,
                asset_id="asset-1",
                variant="original",
            )

    assert lookup.await_args.kwargs["max_retries"] == 0


@pytest.mark.asyncio
async def test_signed_original_of_deleted_immich_asset_is_404():
    fake_media = MagicMock(external_provider="immich", external_asset_id="asset-1", file_path=None)
    fake_media_service = MagicMock()
    fake_media_service.get_media_by_id.return_value = fake_media

    with patch.object(media_module, "_get_media_service", return_value=fake_media_service), \
         patch.object(media_module, "is_signature_expired", return_value=False), \
         patch.object(media_module, "verify_media_signature", return_value=True), \
         patch.object(
             media_module.database_module, "get_session_context", side_effect=_fake_session_context
         ), \
         patch.object(
             media_module,
             "fetch_proxy_asset",
             new=AsyncMock(side_effect=immich.ImmichAssetNotFoundError("asset-1")),
         ):
        with pytest.raises(HTTPException) as exc_info:
            await media_module.get_media_signed(
                media_id=uuid4(), uid=uuid4(), exp=9999999999, sig="sig"
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_proxy_original_of_deleted_immich_asset_is_404():
    with patch.object(router_module, "is_signature_expired", return_value=False), \
         patch.object(router_module, "verify_media_signature", return_value=True), \
         patch.object(
             router_module,
             "fetch_proxy_asset",
             new=AsyncMock(side_effect=immich.ImmichAssetNotFoundError("asset-1")),
         ):
        with pytest.raises(HTTPException) as exc_info:
            await router_module.proxy_original(
                provider=IntegrationProvider.IMMICH,
                asset_id="asset-1",
                uid=str(uuid4()),
                exp=9999999999,
                sig="sig",
            )

    assert exc_info.value.status_code == 404
