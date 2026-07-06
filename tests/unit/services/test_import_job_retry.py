"""Coverage for ImportJobService._with_retry (journiv's backoff wrapper).

Only the retry *decision* is journiv-owned: retry on transient 5xx/timeout/
network errors, treat auth/not-found as terminal. The exception types
themselves come from immichpy and are not re-tested here.
"""
from unittest.mock import AsyncMock

import pytest
from immichpy.client.generated.exceptions import NotFoundException, ServiceException

from app.services.import_job_service import ImportJobService


def _service() -> ImportJobService:
    # _with_retry does not touch instance state, so skip __init__ dependencies.
    return ImportJobService.__new__(ImportJobService)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Skip the real backoff wait so retry tests stay fast."""
    monkeypatch.setattr("app.services.import_job_service.asyncio.sleep", AsyncMock())


@pytest.mark.asyncio
async def test_returns_result_without_retry():
    op = AsyncMock(return_value="ok")
    assert await _service()._with_retry(op, what="x") == "ok"
    assert op.await_count == 1


@pytest.mark.asyncio
async def test_retries_transient_server_error_then_succeeds():
    op = AsyncMock(side_effect=[ServiceException(status=503), "ok"])
    assert await _service()._with_retry(op, what="x", max_retries=2) == "ok"
    assert op.await_count == 2


@pytest.mark.asyncio
async def test_does_not_retry_terminal_not_found():
    op = AsyncMock(side_effect=NotFoundException(status=404))
    with pytest.raises(NotFoundException):
        await _service()._with_retry(op, what="x")
    assert op.await_count == 1


@pytest.mark.asyncio
async def test_raises_after_exhausting_retries():
    op = AsyncMock(side_effect=ServiceException(status=500))
    with pytest.raises(ServiceException):
        await _service()._with_retry(op, what="x", max_retries=2)
    assert op.await_count == 3  # initial + 2 retries
