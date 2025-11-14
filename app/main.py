"""
Main FastAPI application for Journiv.
"""

import time
import socket
import mimetypes
import logging
from pathlib import Path
from urllib.parse import urlparse
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.cache import create_cache
from app.core.exceptions import (
    JournivAppException, UserNotFoundError, UserAlreadyExistsError,
    InvalidCredentialsError, JournalNotFoundError, EntryNotFoundError,
    MoodNotFoundError, PromptNotFoundError, MediaNotFoundError,
    FileTooLargeError, InvalidFileTypeError, FileValidationError,
    TagNotFoundError, UnauthorizedError,
)
from app.core.logging_config import setup_logging, log_info, log_warning, log_error
from app.core.rate_limiting import limiter, rate_limit_exceeded_handler
from app.middleware.request_logging import request_id_ctx, RequestLoggingMiddleware
from app.middleware.csp_middleware import create_csp_middleware

# -----------------------------------------------------------------------------
# Startup / Shutdown
# -----------------------------------------------------------------------------
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    log_info("Starting up Journiv Service...")
    try:
        init_db()
        log_info("Database initialization completed!")

        if settings.oidc_enabled:
            app.state.cache = create_cache(settings.redis_url)
            log_info("Cache initialization completed!")
    except Exception as exc:
        log_error(exc)
        raise
    yield
    log_info("Shutting down Journiv Service...")


# -----------------------------------------------------------------------------
# App Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A self-hosted private journal app with mood tracking, prompts, and analytics",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# -----------------------------------------------------------------------------
# Middleware Configuration
# -----------------------------------------------------------------------------
# Rate Limiting
app.state.limiter = limiter
try:
    from slowapi.errors import RateLimitExceeded
    from app.core.rate_limiting import SLOWAPI_AVAILABLE
    if SLOWAPI_AVAILABLE:
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
        log_info("Rate limiting enabled with slowapi")
    else:
        log_warning("slowapi not available, rate limiting disabled")
except ImportError:
    log_warning("slowapi not available, rate limiting disabled")

# CORS
cors_enabled = bool(settings.enable_cors)
cors_origins = settings.cors_origins or []
if cors_enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
        max_age=3600,
    )
    log_info(f"CORS enabled for origins: {cors_origins}")
else:
    log_info("CORS disabled (same-origin SPA mode)")

# Best-effort domain fallback
if not settings.domain_name:
    try:
        settings.domain_name = socket.gethostname() or "localhost"
        log_info(f"DOMAIN_NAME not set; auto-detected hostname '{settings.domain_name}'")
    except Exception:
        settings.domain_name = "localhost"
        log_warning("DOMAIN_NAME not set and hostname auto-detect failed; defaulting to 'localhost'")

def _extract_hostname(value: str) -> str:
    """Extract hostname from URL or domain string."""
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"//{value}")
    if parsed.hostname:
        return parsed.hostname
    if parsed.path:
        return parsed.path.split(":", 1)[0]
    return ""


# Trusted Hosts
if settings.environment != "production":
    trusted_hosts = ["*"]
    log_info("TrustedHostMiddleware allowing all hosts in development environment.")
else:
    trusted_hosts = []
    if cors_enabled:
        for origin in cors_origins:
            hostname = _extract_hostname(origin)
            if hostname and hostname not in trusted_hosts:
                trusted_hosts.append(hostname)
        for loopback in ("localhost", "127.0.0.1"):
            if loopback not in trusted_hosts:
                trusted_hosts.append(loopback)
        if not [host for host in trusted_hosts if host not in {"localhost", "127.0.0.1"}]:
            log_warning(
                "CORS enabled but no valid hostnames extracted from CORS_ORIGINS; allowing all hosts as fallback."
            )
            trusted_hosts = ["*"]
    else:
        domain_host = _extract_hostname(settings.domain_name)
        if domain_host and domain_host not in trusted_hosts:
            trusted_hosts.append(domain_host)
        for loopback in ("localhost", "127.0.0.1"):
            if loopback not in trusted_hosts:
                trusted_hosts.append(loopback)
        if not domain_host:
            log_warning(
                "DOMAIN_NAME not configured while CORS is disabled in production; allowing all hosts as fallback."
            )
            trusted_hosts = ["*"]

    if trusted_hosts != ["*"]:
        log_info(f"TrustedHostMiddleware allowed hosts: {trusted_hosts}")
    else:
        log_warning("TrustedHostMiddleware allowing all hosts.")

# GZip Middleware.
# This compresses responses (HTML, JSON, JS, CSS, etc.) larger than 1KB.
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)

# Logging Middleware
app.add_middleware(RequestLoggingMiddleware)

# CSP / HSTS Middleware
CSPMiddlewareClass = create_csp_middleware(
    environment=settings.environment,
    enable_csp=settings.enable_csp,
    enable_hsts=settings.enable_hsts and (settings.environment == "production"),
    enable_csp_reporting=settings.enable_csp_reporting,
    csp_report_uri=settings.csp_report_uri
    or ("/api/v1/security/csp-report" if settings.environment == "production" else None),
)
app.add_middleware(CSPMiddlewareClass)

# Session Middleware (required for OIDC state management with Authlib)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    https_only=(settings.environment == "production"),
    same_site="lax",  # required for OIDC redirects to keep cookies alive
)

# -----------------------------------------------------------------------------
# General Middleware
# -----------------------------------------------------------------------------
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add X-Process-Time header."""
    start_time = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(time.time() - start_time)
    return response

# -----------------------------------------------------------------------------
# Exception Handlers
# -----------------------------------------------------------------------------
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    request_id = request_id_ctx.get()
    log_error(exc, request_id=request_id)
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "message": str(exc), "request_id": request_id},
    )


@app.exception_handler(JournivAppException)
async def journal_app_exception_handler(request: Request, exc: JournivAppException):
    request_id = request_id_ctx.get()
    log_error(exc, request_id=request_id)

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    if isinstance(exc, (UserNotFoundError, JournalNotFoundError, EntryNotFoundError,
                        MoodNotFoundError, PromptNotFoundError, MediaNotFoundError,
                        TagNotFoundError)):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, UserAlreadyExistsError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, InvalidCredentialsError):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(exc, UnauthorizedError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, (FileTooLargeError, InvalidFileTypeError, FileValidationError)):
        status_code = status.HTTP_400_BAD_REQUEST

    message = (
        "An unexpected internal error occurred."
        if settings.environment == "production" and status_code == 500
        else str(exc)
    )
    return JSONResponse(
        status_code=status_code,
        content={"error": type(exc).__name__, "message": message, "request_id": request_id},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    request_id = request_id_ctx.get()
    log_error(exc, request_id=request_id)
    msg = (
        "An unexpected error occurred. Please try again later."
        if settings.environment == "production"
        else str(exc)
    )
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "message": msg, "request_id": request_id},
    )

# -----------------------------------------------------------------------------
# API Routers & Media
# -----------------------------------------------------------------------------
app.include_router(api_router, prefix=settings.api_v1_prefix)

media_path = Path(settings.media_root)
if media_path.exists():
    app.mount("/media", StaticFiles(directory=str(media_path)), name="media")
else:
    log_warning(f"Media directory {media_path} does not exist. File uploads may not work properly.")

# -----------------------------------------------------------------------------
# Flutter Web PWA Mount (with 1-week caching)
# -----------------------------------------------------------------------------
import logging, mimetypes
from datetime import timedelta
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger("uvicorn")
WEB_BUILD_PATH = Path(__file__).resolve().parent.parent / "web"

if WEB_BUILD_PATH.exists():
    # Serve the Flutter web build directory
    app.mount("/", StaticFiles(directory=str(WEB_BUILD_PATH), html=True), name="frontend")

    ONE_WEEK = int(timedelta(weeks=1).total_seconds())

    def serve_static_file(file_path: Path, cache: bool = True) -> FileResponse:
        """Serve static files with sensible caching headers."""
        if not file_path.exists():
            raise HTTPException(status_code=404)

        # index.html and manifest.json are always fetched fresh
        if not cache:
            cache_header = "no-cache, no-store, must-revalidate"
        else:
            cache_header = f"public, max-age={ONE_WEEK}"

        headers = {"Cache-Control": cache_header}
        return FileResponse(file_path, headers=headers, media_type=mimetypes.guess_type(file_path)[0])

    @app.get("/manifest.json", include_in_schema=False)
    async def manifest():
        return serve_static_file(WEB_BUILD_PATH / "manifest.json", cache=False)

    @app.get("/flutter_service_worker.js", include_in_schema=False)
    async def service_worker():
        return serve_static_file(WEB_BUILD_PATH / "flutter_service_worker.js", cache=False)

    @app.get("/icons/{icon_name}", include_in_schema=False)
    async def icons(icon_name: str):
        return serve_static_file(WEB_BUILD_PATH / "icons" / icon_name)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str, request: Request):
        """Serve Flutter SPA index.html for all non-API routes."""
        if full_path.startswith(("api/", "media/", "static/")):
            raise HTTPException(status_code=404)

        index_file = WEB_BUILD_PATH / "index.html"
        if index_file.exists():
            return serve_static_file(index_file, cache=False)

        log.error("Flutter web index.html not found.")
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": "Frontend not found"},
        )


# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
