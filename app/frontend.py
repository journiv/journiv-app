"""Serve the primary React SPA and the temporary legacy Flutter SPA."""

from __future__ import annotations

import mimetypes
import os
from datetime import timedelta
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REACT_BUILD_PATH = Path(
    os.getenv("REACT_WEB_BUILD_PATH", str(PROJECT_ROOT / "frontend" / "dist"))
)
LEGACY_BUILD_PATH = Path(
    os.getenv("LEGACY_WEB_BUILD_PATH", str(PROJECT_ROOT / "web"))
)
ROOT_FLUTTER_RETIREMENT_WORKER = (
    Path(__file__).resolve().parent / "static" / "flutter_service_worker_retire.js"
)

ONE_WEEK = int(timedelta(weeks=1).total_seconds())
ONE_YEAR = int(timedelta(days=365).total_seconds())
NO_CACHE = "no-cache, no-store, must-revalidate, max-age=0"

# Backend-owned namespaces are denied by the React fallback even when no concrete
# route matches. Keeping this list beside the SPA router makes route ownership
# explicit and prevents a future missing API/public route from returning HTML.
BACKEND_ROOTS = frozenset(
    {
        "api",
        "docs",
        "media",
        "openapi.json",
        "plus",
        "pub",
        "redoc",
        "static",
    }
)

NO_CACHE_FILENAMES = frozenset(
    {
        "flutter_bootstrap.js",
        "flutter_service_worker.js",
        "index.html",
        "manifest.json",
        "service-worker.js",
        "version.json",
    }
)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404)


def _safe_file(build_path: Path, relative_path: str) -> Path:
    resolved_build_path = build_path.resolve()
    file_path = (build_path / relative_path).resolve()
    if not file_path.is_relative_to(resolved_build_path):
        raise _not_found()
    return file_path


def _looks_like_asset(relative_path: str) -> bool:
    path = PurePosixPath(relative_path)
    return bool(path.suffix) or (bool(path.parts) and path.parts[0] == "assets")


def _wants_html_document(request: Request) -> bool:
    """A top-level browser navigation, as opposed to a fetch/asset request."""
    return "text/html" in request.headers.get("accept", "")


def _serve_file(
    file_path: Path,
    relative_path: str,
    *,
    immutable_assets: bool,
    service_worker_scope: str,
) -> FileResponse:
    filename = PurePosixPath(relative_path).name
    if filename in NO_CACHE_FILENAMES:
        cache_control = NO_CACHE
    elif immutable_assets and relative_path.startswith("assets/"):
        # Vite fingerprints everything in assets/. Those files can be cached
        # permanently without making a deployment sticky.
        cache_control = f"public, max-age={ONE_YEAR}, immutable"
    else:
        # Flutter's filenames are largely stable and its release artifact uses
        # query-string revisions, so retain the existing bounded cache policy.
        cache_control = f"public, max-age={ONE_WEEK}"

    headers = {"Cache-Control": cache_control}
    if filename in {"flutter_service_worker.js", "service-worker.js"}:
        headers["Service-Worker-Allowed"] = service_worker_scope

    return FileResponse(
        file_path,
        headers=headers,
        media_type=mimetypes.guess_type(file_path)[0],
    )


def _serve_spa(
    build_path: Path,
    relative_path: str,
    *,
    immutable_assets: bool,
    service_worker_scope: str,
    wants_html_document: bool = False,
) -> FileResponse | JSONResponse:
    if not build_path.is_dir():
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": "Frontend not found"},
        )

    file_path = _safe_file(build_path, relative_path)
    if file_path.is_file():
        return _serve_file(
            file_path,
            relative_path,
            immutable_assets=immutable_assets,
            service_worker_scope=service_worker_scope,
        )

    # A missing asset is an actual 404. Returning index.html here produces a
    # misleading HTTP 200 and a browser MIME error that hides deployment bugs.
    # A client-side route can still contain a dot (a date, a slug), so a real
    # browser navigation (Accept: text/html) always falls through to the SPA.
    if _looks_like_asset(relative_path) and not wants_html_document:
        raise _not_found()

    index_file = build_path / "index.html"
    if index_file.is_file():
        return _serve_file(
            index_file,
            "index.html",
            immutable_assets=immutable_assets,
            service_worker_scope=service_worker_scope,
        )

    return JSONResponse(
        status_code=404,
        content={"error": "not_found", "message": "Frontend not found"},
    )


def create_frontend_router(
    react_build_path: Path = REACT_BUILD_PATH,
    legacy_build_path: Path = LEGACY_BUILD_PATH,
    retirement_worker_path: Path = ROOT_FLUTTER_RETIREMENT_WORKER,
) -> APIRouter:
    """Build the frontend router with explicit React and Flutter ownership."""
    router = APIRouter()

    @router.get("/flutter_service_worker.js", include_in_schema=False)
    async def retire_root_flutter_service_worker() -> FileResponse:
        """Replace a previously shipped root Flutter worker with a retiree."""
        if not retirement_worker_path.is_file():
            raise _not_found()
        return FileResponse(
            retirement_worker_path,
            media_type="application/javascript",
            headers={
                "Cache-Control": NO_CACHE,
                "Service-Worker-Allowed": "/",
            },
        )

    @router.get("/legacy", include_in_schema=False)
    async def legacy_slash_redirect() -> RedirectResponse:
        return RedirectResponse(url="/legacy/", status_code=308)

    @router.get(
        "/legacy/{full_path:path}", include_in_schema=False, response_model=None
    )
    async def serve_legacy(
        full_path: str, request: Request
    ) -> FileResponse | JSONResponse:
        return _serve_spa(
            legacy_build_path,
            full_path,
            immutable_assets=False,
            service_worker_scope="/legacy/",
            wants_html_document=_wants_html_document(request),
        )

    @router.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def serve_react(
        full_path: str, request: Request
    ) -> FileResponse | JSONResponse:
        root = full_path.split("/", 1)[0]
        if root in BACKEND_ROOTS:
            raise _not_found()
        return _serve_spa(
            react_build_path,
            full_path,
            immutable_assets=True,
            service_worker_scope="/",
            wants_html_document=_wants_html_document(request),
        )

    return router


frontend_router = create_frontend_router()
