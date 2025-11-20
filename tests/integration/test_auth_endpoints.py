"""
Integration coverage for authentication endpoints.
"""
import uuid

from tests.lib import ApiUser, JournivApiClient, make_api_user


def _unique_credentials(prefix: str = "auth") -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    email = f"{prefix}-{suffix}@example.com"
    password = f"Pass-{suffix}-Aa1!"
    return email, password


def test_user_registration_and_login(api_client: JournivApiClient):
    """New users can register, log in, and fetch their profile."""
    email, password = _unique_credentials()
    created = api_client.register_user(
        email=email,
        password=password,
        name="Integration Test",
    )
    assert created["email"] == email
    assert created["is_active"] is True
    assert created["time_zone"]
    assert created["is_oidc_user"] is False
    assert created["name"] == "Integration Test"

    tokens = api_client.login(email, password)
    assert tokens["user"]["email"] == email
    assert tokens["user"]["is_active"] is True
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    profile = api_client.current_user(tokens["access_token"])
    assert profile["email"] == email
    assert profile["id"] == tokens["user"]["id"]


def test_login_rejects_invalid_credentials(api_client: JournivApiClient):
    """Invalid credentials should return 401 without leaking detail."""
    response = api_client.request(
        "POST",
        "/auth/login",
        json={"email": "missing@example.com", "password": "nope"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]


def test_refresh_token_flow(api_client: JournivApiClient):
    """Refreshing the token returns a brand new access token."""
    user = make_api_user(api_client)
    assert user.refresh_token, "API did not issue a refresh token"

    refreshed = api_client.refresh(user.refresh_token)
    assert refreshed["access_token"] != user.access_token

    profile = api_client.current_user(refreshed["access_token"])
    assert profile["id"] == user.user_id


def test_refresh_rejects_invalid_token(api_client: JournivApiClient):
    """Tampered refresh tokens should be rejected."""
    response = api_client.request(
        "POST",
        "/auth/refresh",
        json={"refresh_token": "not-a-real-token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]


def test_oauth_token_endpoint_accepts_form_credentials(
    api_client: JournivApiClient, api_user: ApiUser
):
    """OAuth2 password grant endpoint should mirror login behavior."""
    response = api_client.request(
        "POST",
        "/auth/token",
        data={"username": api_user.email, "password": api_user.password},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert payload["token_type"] == "bearer"


def test_oauth_token_endpoint_rejects_bad_credentials(api_client: JournivApiClient):
    """OAuth2 password grant should return 401 for invalid credentials."""
    response = api_client.request(
        "POST",
        "/auth/token",
        data={"username": "unknown@example.com", "password": "nope"},
    )
    assert response.status_code == 401


def test_logout_requires_and_uses_authentication(
    api_client: JournivApiClient, api_user: ApiUser
):
    unauthorized = api_client.request("POST", "/auth/logout")
    assert unauthorized.status_code == 401

    response = api_client.request(
        "POST", "/auth/logout", token=api_user.access_token
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"]
    assert body["detail"]


def test_protected_endpoint_requires_token(api_client: JournivApiClient):
    """Hitting a protected endpoint without auth returns 401."""
    response = api_client.request("GET", "/users/me")
    assert response.status_code == 401


def test_registering_duplicate_email_is_rejected(
    api_client: JournivApiClient, api_user: ApiUser
):
    """Registering the same email twice should raise 400/409."""
    response = api_client.request(
        "POST",
        "/auth/register",
        json={
            "email": api_user.email,
            "password": api_user.password,
            "name": "Dup User",
            "first_name": "Dup",
            "last_name": "User",
        },
    )
    assert response.status_code in (400, 409)
    detail = response.json().get("detail", "")
    assert "already" in detail.lower()
