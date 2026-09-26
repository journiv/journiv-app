"""Cleanup of per-task HTTP clients must not change a task's outcome."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.tasks import _run_with_session


@pytest.mark.asyncio
@pytest.mark.parametrize("task_fails", [False, True])
async def test_task_cleanup_attempts_both_clients_without_masking_outcome(task_fails):
    @asynccontextmanager
    async def session():
        yield object()

    task_error = RuntimeError("task failed")
    task = AsyncMock(side_effect=task_error if task_fails else None, return_value="done")
    with (
        patch("app.integrations.tasks.async_session_factory", side_effect=session),
        patch("app.integrations.tasks.immich.close_client", new_callable=AsyncMock) as close_immich,
        patch("app.integrations.tasks.close_http_client", new_callable=AsyncMock) as close_http,
        patch("app.integrations.tasks.log_error"),
    ):
        close_immich.side_effect = RuntimeError("Immich close failed")
        close_http.side_effect = RuntimeError("HTTP close failed")
        if task_fails:
            with pytest.raises(RuntimeError) as raised:
                await _run_with_session(task)
            assert raised.value is task_error
        else:
            assert await _run_with_session(task) == "done"

    close_immich.assert_awaited_once()
    close_http.assert_awaited_once()
