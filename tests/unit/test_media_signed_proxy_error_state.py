"""
Regression test: a 401/403 from Immich while proxying signed media did not
call `_update_integration_error_state` the way the dedicated proxy endpoints
(`app/integrations/router.py`) do, so Settings never learned the token was
bad and kept telling the user everything was fine.
"""
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.api.v1.endpoints.media as media_module
import app.integrations.router as router_module


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code

    async def aclose(self):
        pass


@contextmanager
def _fake_session_context(*_args, **_kwargs):
    yield MagicMock()


@pytest.mark.asyncio
async def test_signed_original_401_updates_integration_error_state():
    media_id = uuid4()
    uid = uuid4()

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
             media_module, "fetch_proxy_asset", new=AsyncMock(return_value=_FakeResponse(401))
         ), \
         patch.object(
             router_module, "_update_integration_error_state", new=AsyncMock()
         ) as mock_update_error_state:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await media_module.get_media_signed(
                media_id=media_id, uid=uid, exp=9999999999, sig="sig"
            )

    assert exc_info.value.status_code == 401
    mock_update_error_state.assert_called_once()
    call_args = mock_update_error_state.call_args.args
    assert call_args[0] == uid
