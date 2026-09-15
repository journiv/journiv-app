"""
Integration coverage for authentication endpoints.
"""

import uuid

from app.core.auth_cookies import AUTH_CLIENT_HEADER, REFRESH_COOKIE_NAME
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


def test_oauth_token_endpoint_uses_cookie_contract_for_pwa(
    api_client: JournivApiClient, api_user: ApiUser
):
    try:
        response = api_client.request(
            "POST",
            "/auth/token",
            data={"username": api_user.email, "password": api_user.password},
            headers={AUTH_CLIENT_HEADER: "pwa"},
        )

        assert response.status_code == 200
        assert "refresh_token" not in response.json()
        assert response.cookies.get(REFRESH_COOKIE_NAME)
    finally:
        api_client.clear_cookies()


def test_oauth_token_endpoint_rejects_bad_credentials(api_client: JournivApiClient):
    """OAuth2 password grant should return 401 for invalid credentials."""
    response = api_client.request(
        "POST",
        "/auth/token",
        data={"username": "unknown@example.com", "password": "nope"},
    )
    assert response.status_code == 401


def test_logout_succeeds_with_or_without_authentication(
    api_client: JournivApiClient, api_user: ApiUser
):
    """Logout's only effect is clearing the refresh cookie, so it must
    succeed for any caller -- this is what makes the offline-logout retry
    (a request with no access token at all) work."""
    unauthenticated = api_client.request("POST", "/auth/logout")
    assert unauthenticated.status_code == 200

    response = api_client.request("POST", "/auth/logout", token=api_user.access_token)
    assert response.status_code == 200
    body = response.json()
    assert body["message"]
    assert body["detail"]


def test_logout_clears_cookie_with_expired_or_malformed_token(
    api_client: JournivApiClient,
):
    response = api_client.request("POST", "/auth/logout", token="not-a-real-jwt")
    assert response.status_code == 200
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        header.startswith(f'{REFRESH_COOKIE_NAME}=""') and "Max-Age=0" in header
        for header in set_cookie_headers
    )


def test_logout_ignores_an_access_token_cookie(
    api_client: JournivApiClient, api_user: ApiUser
):
    """Logout authenticates from the Bearer header only.

    `get_current_user` still has a fallback that accepts a cookie named
    `access_token` as a full credential, and the API has no CSRF protection
    (frontend/docs/known-gaps.md). That fallback is unreachable only because
    every dependency in front of it rejects a header-less request first.
    Logout is the one endpoint that deliberately does not, so it is the one
    place the fallback could come back to life -- assert it stays dead. The
    call still succeeds (logout always does); what must not happen is the
    cookie being *consulted* as a credential.
    """
    response = api_client.request(
        "POST", "/auth/logout", cookies={"access_token": api_user.access_token}
    )
    assert response.status_code == 200
    # This suite calls a separately running server, so a local mock cannot
    # observe its audit logger. The same-process assertion that
    # `log_user_action` is untouched lives in tests/unit/test_auth_contract.py.
    # The schema half of this -- that `access_token` is not a documented
    # cookie parameter on this operation -- is asserted in-process by
    # tests/unit/test_openapi_contract.py, which does not need a running
    # server on the revision under test.


def test_logout_is_idempotent(api_client: JournivApiClient, api_user: ApiUser):
    """Calling logout twice must be indistinguishable from calling it once."""
    first = api_client.request("POST", "/auth/logout", token=api_user.access_token)
    second = api_client.request("POST", "/auth/logout", token=api_user.access_token)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    profile = api_client.current_user(api_user.access_token)
    assert profile["email"] == api_user.email


def test_login_sets_httponly_refresh_cookie(api_client: JournivApiClient):
    email, password = _unique_credentials("cookie")
    api_client.register_user(email=email, password=password, name="Cookie Test")
    try:
        response = api_client.request(
            "POST",
            "/auth/login",
            json={"email": email, "password": password},
            headers={AUTH_CLIENT_HEADER: "pwa"},
        )
        assert response.status_code == 200
        assert "refresh_token" not in response.json()
        cookie = response.cookies.get(REFRESH_COOKIE_NAME)
        assert cookie
        set_cookie_header = response.headers["set-cookie"]
        assert "HttpOnly" in set_cookie_header
        assert "SameSite=lax" in set_cookie_header
        assert "Path=/api/v1/auth" in set_cookie_header
        # Never confuse this with the dead access_token cookie fallback.
        assert not set_cookie_header.startswith("access_token=")
    finally:
        api_client.clear_cookies()


def test_login_preserves_legacy_refresh_token_contract(api_client: JournivApiClient):
    email, password = _unique_credentials("legacy")
    api_client.register_user(email=email, password=password, name="Legacy Test")
    api_client.clear_cookies()

    response = api_client.request(
        "POST", "/auth/login", json={"email": email, "password": password}
    )

    assert response.status_code == 200
    assert response.json()["refresh_token"]
    assert response.cookies.get(REFRESH_COOKIE_NAME) is None


def test_refresh_accepts_cookie_with_no_body(api_client: JournivApiClient):
    user = make_api_user(api_client)
    try:
        login = api_client.request(
            "POST",
            "/auth/login",
            json={"email": user.email, "password": user.password},
            headers={AUTH_CLIENT_HEADER: "pwa"},
        )
        assert login.status_code == 200

        # No body at all -- the client relies entirely on the cookie jar.
        refreshed = api_client.request("POST", "/auth/refresh")
        assert refreshed.status_code == 200
        payload = refreshed.json()
        assert payload["access_token"]
        assert payload["access_token"] != login.json()["access_token"]

        profile = api_client.current_user(payload["access_token"])
        assert profile["id"] == user.user_id
    finally:
        api_client.clear_cookies()


def test_refresh_accepts_body_token_without_cookie(api_client: JournivApiClient):
    """Flutter (/legacy/) compatibility: a body-supplied refresh token still
    works even when no cookie is present."""
    user = make_api_user(api_client)
    api_client.clear_cookies()
    assert user.refresh_token

    refreshed = api_client.refresh(user.refresh_token)
    assert refreshed["access_token"]


def test_refresh_with_neither_body_nor_cookie_is_rejected(
    api_client: JournivApiClient,
):
    api_client.clear_cookies()
    response = api_client.request("POST", "/auth/refresh")
    assert response.status_code == 401


def test_refresh_after_logout_is_rejected(api_client: JournivApiClient):
    user = make_api_user(api_client)
    try:
        login = api_client.request(
            "POST",
            "/auth/login",
            json={"email": user.email, "password": user.password},
            headers={AUTH_CLIENT_HEADER: "pwa"},
        )
        assert login.status_code == 200

        logout = api_client.request("POST", "/auth/logout")
        assert logout.status_code == 200

        refreshed = api_client.request("POST", "/auth/refresh")
        assert refreshed.status_code == 401
    finally:
        api_client.clear_cookies()


def test_no_endpoint_sets_an_access_token_cookie(
    api_client: JournivApiClient, api_user: ApiUser
):
    """Regression guard for the latent CSRF vector: nothing in the API may
    ever set a cookie literally named access_token -- app.api.dependencies
    treats one as a full bearer credential and the API has no CSRF
    protection."""
    try:
        responses = [
            api_client.request(
                "POST",
                "/auth/login",
                json={"email": api_user.email, "password": api_user.password},
                headers={AUTH_CLIENT_HEADER: "pwa"},
            ),
            api_client.request("POST", "/auth/refresh"),
            api_client.request("POST", "/auth/logout"),
        ]
        for response in responses:
            for set_cookie in response.headers.get_list("set-cookie"):
                assert not set_cookie.startswith("access_token="), set_cookie
    finally:
        api_client.clear_cookies()


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
