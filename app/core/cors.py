"""Shared CORS policy constants."""

from typing import Any, Final, Sequence, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Browser media elements use byte-range requests to load video metadata and
# seek without downloading the entire file. Keep these headers explicit so
# cross-origin Flutter web/PWA clients can use the signed media endpoints.
CORS_ALLOW_HEADERS: Final[tuple[str, ...]] = (
    "Authorization",
    "Content-Type",
    "Accept",
    "Origin",
    "X-Requested-With",
    "X-Journiv-Client",
    "Range",
)

CORS_EXPOSE_HEADERS: Final[tuple[str, ...]] = (
    "Accept-Ranges",
    "Content-Length",
    "Content-Range",
)


def add_cors_middleware(app: FastAPI, origins: Sequence[str]) -> None:
    """Configure the application's cross-origin request policy."""
    app.add_middleware(
        cast(Any, CORSMiddleware),
        allow_origins=list(origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=CORS_ALLOW_HEADERS,
        expose_headers=CORS_EXPOSE_HEADERS,
        max_age=3600,
    )
