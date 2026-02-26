import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.service import sync_integration
from app.models.integration import IntegrationProvider


class _Result:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value

    def all(self):
        return self._value


@pytest.mark.asyncio
async def test_sync_integration_rolls_back_and_persists_error_state():
    user = SimpleNamespace(id=uuid.uuid4())
    integration = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        provider=IntegrationProvider.IMMICH,
        is_active=True,
        last_error=None,
        last_error_at=None,
    )
    refreshed_integration = SimpleNamespace(
        id=integration.id,
        user_id=user.id,
        provider=IntegrationProvider.IMMICH,
        is_active=True,
        last_error=None,
        last_error_at=None,
    )

    mock_session = MagicMock()
    mock_provider = SimpleNamespace(sync=AsyncMock(side_effect=RuntimeError("provider failed")))

    exec_mock = AsyncMock(
        side_effect=[
            _Result(integration),           # initial integration lookup
            _Result(refreshed_integration),  # re-fetch after rollback
        ]
    )
    rollback_mock = AsyncMock()
    commit_mock = AsyncMock()

    with patch("app.integrations.service._exec", exec_mock), \
         patch("app.integrations.service._rollback", rollback_mock), \
         patch("app.integrations.service._commit", commit_mock), \
         patch("app.integrations.service.get_provider_module", return_value=mock_provider):
        with pytest.raises(RuntimeError, match="provider failed"):
            await sync_integration(
                session=mock_session,
                user=user,
                provider=IntegrationProvider.IMMICH,
            )

    assert rollback_mock.await_count == 1
    commit_mock.assert_awaited_once()
    assert refreshed_integration.last_error == "provider failed"
    assert refreshed_integration.last_error_at is not None
