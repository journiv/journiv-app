"""Shared CORS policy constants."""

from typing import Final

# Browser media elements use byte-range requests to load video metadata and
# seek without downloading the entire file. Keep these headers explicit so
# cross-origin Flutter web/PWA clients can use the signed media endpoints.
CORS_ALLOW_HEADERS: Final[tuple[str, ...]] = (
    "Authorization",
    "Content-Type",
    "Accept",
    "Origin",
    "X-Requested-With",
    "Range",
)

CORS_EXPOSE_HEADERS: Final[tuple[str, ...]] = (
    "Accept-Ranges",
    "Content-Length",
    "Content-Range",
)
