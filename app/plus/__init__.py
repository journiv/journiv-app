"""
Journiv Plus Smart Gateway.

Controls how Plus features are served based on the PLUS_SERVICE_URL
environment variable:

  PLUS_SERVICE_URL unset  →  Convenience Mode (inline)
      The compiled plus_features.so is imported and its routers are mounted
      directly into the main FastAPI app. Zero network overhead.

  PLUS_SERVICE_URL set    →  Privacy Mode (proxy)
      A singleton httpx client forwards matching requests to the Plus
      sidecar running at PLUS_SERVICE_URL. The main app image does not
      need to contain the .so binary.

In both modes two FastAPI routers are exported:
  plus_api_router    — authenticated Plus API  (/api/v1/plus/*)
  plus_public_router — public publishing URLs  (/pub/*, /api/v1/oembed)
"""

import logging
import os
from importlib import import_module
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.logging_config import LogCategory

logger = logging.getLogger(LogCategory.PLUS)

PLUS_SERVICE_URL: str = os.getenv("PLUS_SERVICE_URL", "").strip()
PLUS_MODE: str = "proxy" if PLUS_SERVICE_URL else "inline"
PLUS_AVAILABLE: bool = False


def _sanitize_service_url_for_log(url: str) -> str:
    """Strip credentials from service URLs before logging."""
    if not url:
        return ""

    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    safe_netloc = host or parts.netloc.split("@")[-1]
    return urlunsplit((parts.scheme, safe_netloc, parts.path, parts.query, parts.fragment))

# Fallback empty routers — replaced below in each mode.
plus_api_router: APIRouter = APIRouter()
plus_public_router: APIRouter = APIRouter()

# ---------------------------------------------------------------------------
# Convenience / Inline Mode
# ---------------------------------------------------------------------------
if PLUS_MODE == "inline":
    _plus_loaded = False
    try:
        plus_features = import_module("app.plus.plus_features")
        _api_router = plus_features.plus_api_router
        _pub_router = plus_features.plus_public_router

        plus_api_router = _api_router
        plus_public_router = _pub_router
        PLUS_AVAILABLE = True
        _plus_loaded = True

        try:
            version_module = import_module("app.plus._version")
            _v = version_module.__version__

            logger.info("Journiv Plus v%s loaded (inline mode).", _v)
        except Exception:
            logger.info("Journiv Plus loaded (inline mode).")

    except ModuleNotFoundError:
        # .so binary simply not present — expected for core-only deployments.
        logger.info(
            "Journiv Plus binary not found — running without Plus features. "
            "Deploy a Plus-enabled image or set PLUS_SERVICE_URL for proxy mode."
        )

    except ImportError as _err:
        # .so exists but has a symbol/ABI issue (wrong Python version, bad build).
        logger.warning(
            "Journiv Plus binary found but failed to import (%s). "
            "Possible ABI or Python version mismatch.",
            _err,
        )

    except Exception as _err:
        # .so loaded but initialization failed (SQLAlchemy conflict, missing env, etc.).
        logger.warning(
            "Journiv Plus failed to initialize (%s: %s). "
            "Running without Plus features.",
            type(_err).__name__,
            _err,
        )

    if not _plus_loaded:
        # Register explicit 501 handlers so callers receive a clear message
        # instead of a generic 404.
        _501_body = {
            "detail": "Journiv Plus features are not enabled in this deployment."
        }

        @plus_api_router.api_route(
            "/plus/{path:path}",
            methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            include_in_schema=False,
        )
        async def _plus_not_available(path: str) -> JSONResponse:  # noqa: ARG001
            return JSONResponse(status_code=501, content=_501_body)

        @plus_public_router.get("/pub/{path:path}", include_in_schema=False)
        async def _pub_not_available(path: str) -> JSONResponse:  # noqa: ARG001
            return JSONResponse(status_code=501, content=_501_body)

        @plus_public_router.get("/api/v1/oembed", include_in_schema=False)
        async def _oembed_not_available() -> JSONResponse:
            return JSONResponse(status_code=501, content=_501_body)

# ---------------------------------------------------------------------------
# Privacy / Proxy Mode
# ---------------------------------------------------------------------------
else:
    from app.plus._proxy import build_proxy_routers

    plus_api_router, plus_public_router = build_proxy_routers(PLUS_SERVICE_URL)
    PLUS_AVAILABLE = True
    logger.info(
        "Journiv Plus running in proxy mode → %s.",
        _sanitize_service_url_for_log(PLUS_SERVICE_URL),
    )

__all__ = [
    "plus_api_router",
    "plus_public_router",
    "PLUS_AVAILABLE",
    "PLUS_MODE",
]
