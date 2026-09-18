"""Authentication endpoint contract coverage."""

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User


def test_logout_openapi_is_unauthenticated_without_cookie_parameter() -> None:
    operation = app.openapi()["paths"]["/api/v1/auth/logout"]["post"]

    assert operation.get("security") in (None, [])
    assert [
        parameter
        for parameter in operation.get("parameters", [])
        if parameter.get("in") == "cookie"
    ] == []
    assert set(operation["responses"]) == {"200", "500"}


def test_logout_does_not_authenticate_from_access_token_cookie() -> None:
    """A cookie-only request succeeds anonymously and is not audit-attributed."""
    user = User(
        id=uuid.uuid4(),
        email="cookie-only@example.com",
        password="hashed-password",
        name="Cookie Only",
        is_active=True,
    )
    with (
        patch("app.api.v1.endpoints.auth.log_user_action") as log_user_action,
        patch(
            "app.api.dependencies.verify_token",
            return_value={"sub": str(user.id)},
        ) as verify_token,
        patch("app.api.dependencies.UserService") as user_service,
    ):
        user_service.return_value.get_user_by_id.return_value = user
        response = TestClient(app).post(
            "/api/v1/auth/logout",
            cookies={"access_token": "cookie-access-token"},
        )

    assert response.status_code == 200
    verify_token.assert_not_called()
    log_user_action.assert_not_called()
