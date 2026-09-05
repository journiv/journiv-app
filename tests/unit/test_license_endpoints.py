"""Unit tests for the license management endpoints."""
import pytest

from app.api.v1.endpoints import license
from app.models.user import User
from app.schemas.license import LicenseRegisterRequest, LicenseRegisterResponse


class _FakeRequestState:
    request_id = "test-request-id"


class _FakeRequest:
    state = _FakeRequestState()


def _admin() -> User:
    return User(
        email="admin@example.com",
        password="hashed-password",
        name="Admin",
        role="admin",
    )


@pytest.mark.asyncio
async def test_register_license_propagates_rate_limit(monkeypatch):
    """A rate-limited registration must surface `rate_limited` / `retry_after`.

    The service returns these fields on `PlusRateLimitError`; the endpoint used
    to rebuild the response without them, so the client could never show a
    cooldown and told the admin to check their key instead.
    """

    class RateLimitedService:
        def __init__(self, _db):
            pass

        async def register_license(self, **_kwargs):
            return {
                "successful": False,
                "signed_license": None,
                "error_message": "Rate limit exceeded. Please try again in 2 minutes.",
                "rate_limited": True,
                "retry_after": 120,
            }

    monkeypatch.setattr(license, "LicenseService", RateLimitedService)

    result = await license.register_license(
        http_request=_FakeRequest(),
        request=LicenseRegisterRequest(
            license="lic_abcdefghijklmnopqrstuvwxyz123456",
            email="admin@example.com",
        ),
        db=object(),
        current_user=_admin(),
    )

    assert isinstance(result, LicenseRegisterResponse)
    assert result.successful is False
    assert result.rate_limited is True
    assert result.retry_after == 120
    assert result.error_message == "Rate limit exceeded. Please try again in 2 minutes."


@pytest.mark.asyncio
async def test_register_license_preserves_server_failure_reason(monkeypatch):
    """A non-rate-limited failure must keep the server's `error_message`."""

    class RejectingService:
        def __init__(self, _db):
            pass

        async def register_license(self, **_kwargs):
            return {
                "successful": False,
                "signed_license": None,
                "error_message": "License already bound to another installation.",
            }

    monkeypatch.setattr(license, "LicenseService", RejectingService)

    result = await license.register_license(
        http_request=_FakeRequest(),
        request=LicenseRegisterRequest(
            license="lic_abcdefghijklmnopqrstuvwxyz123456",
            email="admin@example.com",
        ),
        db=object(),
        current_user=_admin(),
    )

    assert result.successful is False
    assert result.rate_limited is False
    assert result.retry_after is None
    assert result.error_message == "License already bound to another installation."
