import uuid

import pytest
from unittest.mock import MagicMock, patch

from app.models.user import User
from app.models.enums import UserRole


@pytest.mark.asyncio
async def test_get_current_user_uses_cache():
    from app.api import dependencies

    dependencies._user_cache = None

    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        password="hashedpassword",
        name="Test User",
        role=UserRole.USER,
        is_active=True,
    )

    with patch.object(
        dependencies.settings, "redis_url", "redis://localhost:6379/0"
    ), patch("app.api.dependencies.verify_token") as mock_verify, patch(
        "app.api.dependencies.UserService"
    ) as mock_user_service:
        mock_verify.return_value = {"sub": str(user.id)}
        service_instance = mock_user_service.return_value
        service_instance.get_user_by_id.return_value = user

        session = MagicMock()

        first = await dependencies.get_current_user(token="token", cookie_token=None, session=session)
        assert first.id == user.id
        service_instance.get_user_by_id.assert_called_once_with(str(user.id))

        service_instance.get_user_by_id.reset_mock()
        second = await dependencies.get_current_user(token="token", cookie_token=None, session=session)
        assert second.id == user.id
        service_instance.get_user_by_id.assert_not_called()
    dependencies._user_cache = None


@pytest.mark.asyncio
async def test_get_current_user_detached_success():
    """Test get_current_user_detached returns user with valid credentials."""
    from app.api import dependencies
    from fastapi import HTTPException

    user = User(
        id=uuid.uuid4(),
        email="simple@example.com",
        password="hashedpassword",
        name="Simple User",
        is_active=True,
    )

    with patch("app.api.dependencies.verify_token") as mock_verify, \
         patch("app.api.dependencies.UserService") as mock_user_service, \
         patch("app.core.database.get_session_context") as mock_get_context:

        mock_verify.return_value = {"sub": str(user.id)}

        # Mock UserService
        service_instance = mock_user_service.return_value
        service_instance.get_user_by_id.return_value = user

        # Mock Context Manager for session
        mock_session = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_session
        mock_get_context.return_value = mock_ctx

        result = await dependencies.get_current_user_detached(token="valid_token")

        assert result.id == user.id
        mock_session.expunge.assert_called_once_with(user)


@pytest.mark.asyncio
async def test_get_current_user_detached_invalid_uuid():
    """Test get_current_user_detached raises 401 for invalid UUID subject."""
    from app.api import dependencies
    from fastapi import HTTPException

    with patch("app.api.dependencies.verify_token") as mock_verify:
        # Return a non-UUID subject
        mock_verify.return_value = {"sub": "not-a-uuid"}

        with pytest.raises(HTTPException) as exc:
             await dependencies.get_current_user_detached(token="token_with_bad_sub")

        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_detached_cache_hit():
    """Test get_current_user_detached uses cache and avoids DB."""
    from app.api import dependencies

    dependencies._user_cache = None
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="cached@example.com",
        password="hashedpassword",
        name="Cached User",
        is_active=True,
    )

    with patch.object(dependencies.settings, "redis_url", "redis://localhost:6379/0"), \
         patch("app.api.dependencies.verify_token") as mock_verify, \
         patch("app.api.dependencies._get_user_cache") as mock_get_cache:

        mock_verify.return_value = {"sub": str(user_id)}

        # Mock cache hit
        mock_cache = MagicMock()
        mock_cache.get.side_effect = lambda scope_id, cache_type: (
            user.model_dump(mode="json") if cache_type == "auth" else None
        )
        mock_get_cache.return_value = mock_cache

        # Mock DB context (failed check: should NOT be called)
        with patch("app.core.database.get_session_context") as mock_get_context:
             result = await dependencies.get_current_user_detached(token="cached_token")

             assert result.id == user.id
             mock_get_context.assert_not_called()

    dependencies._user_cache = None
