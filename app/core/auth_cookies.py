"""The refresh-session cookie.

Deliberately NOT named `access_token`: `app/api/dependencies.py` treats a
cookie of that name as a full credential on every authenticated endpoint,
and the API has no CSRF protection. This cookie carries only the refresh
token and is pinned to the auth path so it can never authenticate a data
request.
"""

from typing import Literal, Optional

from fastapi import Response

from app.core.config import settings

REFRESH_COOKIE_NAME = "journiv_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"
AUTH_CLIENT_HEADER = "X-Journiv-Client"
AuthClient = Literal["legacy", "pwa"]


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.domain_scheme == "https",
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=settings.refresh_token_expire_days * 86400,
    )


def deliver_refresh_token(
    response: Response, refresh_token: str, client: AuthClient
) -> Optional[str]:
    """Deliver refresh credentials using the contract selected by the client."""
    if client == "pwa":
        set_refresh_cookie(response, refresh_token)
        return None
    return refresh_token


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.domain_scheme == "https",
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )
