from unittest.mock import patch

from fastapi import Response

from app.core.auth_cookies import (
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    clear_refresh_cookie,
    deliver_refresh_token,
    set_refresh_cookie,
)


def _set_cookie_header(response: Response) -> str:
    values = response.headers.getlist("set-cookie")
    assert len(values) == 1
    return values[0]


def test_set_refresh_cookie_attributes_over_http():
    response = Response()
    with patch("app.core.auth_cookies.settings") as mock_settings:
        mock_settings.domain_scheme = "http"
        mock_settings.refresh_token_expire_days = 7
        set_refresh_cookie(response, "a-refresh-token")

    header = _set_cookie_header(response)
    assert f"{REFRESH_COOKIE_NAME}=a-refresh-token" in header
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    assert f"Path={REFRESH_COOKIE_PATH}" in header
    assert "Max-Age=604800" in header
    assert "Secure" not in header


def test_set_refresh_cookie_is_secure_over_https():
    response = Response()
    with patch("app.core.auth_cookies.settings") as mock_settings:
        mock_settings.domain_scheme = "https"
        mock_settings.refresh_token_expire_days = 7
        set_refresh_cookie(response, "a-refresh-token")

    header = _set_cookie_header(response)
    assert "Secure" in header


def test_clear_refresh_cookie_matches_set_cookie_attributes():
    response = Response()
    with patch("app.core.auth_cookies.settings") as mock_settings:
        mock_settings.domain_scheme = "https"
        clear_refresh_cookie(response)

    header = _set_cookie_header(response)
    assert header.startswith(f'{REFRESH_COOKIE_NAME}=""')
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=lax" in header
    assert f"Path={REFRESH_COOKIE_PATH}" in header
    assert "Max-Age=0" in header


def test_pwa_refresh_token_is_delivered_only_by_cookie():
    response = Response()
    with patch("app.core.auth_cookies.settings") as mock_settings:
        mock_settings.domain_scheme = "https"
        mock_settings.refresh_token_expire_days = 7
        body_token = deliver_refresh_token(response, "refresh-token", "pwa")

    assert body_token is None
    assert REFRESH_COOKIE_NAME in _set_cookie_header(response)


def test_legacy_refresh_token_is_delivered_only_in_body():
    response = Response()

    body_token = deliver_refresh_token(response, "refresh-token", "legacy")

    assert body_token == "refresh-token"
    assert response.headers.getlist("set-cookie") == []
