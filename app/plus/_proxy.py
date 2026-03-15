"""
httpx proxy router builder for Plus Privacy Mode.

A singleton AsyncClient is created once at module import time.
Reusing it across requests avoids repeated TCP handshakes and TLS
negotiation, which matters even on an internal Docker network.
"""

import logging
from typing import Iterable

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Module-level singleton — shared across all requests for the lifetime of
# the process.  Call close_proxy_client() on app shutdown to release resources.
_proxy_client = httpx.AsyncClient(timeout=30.0)

_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _filter_proxy_headers(
    headers: Iterable[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Remove hop-by-hop headers that must not be forwarded by proxies."""
    return [(k, v) for k, v in headers if k.lower() not in _HOP_BY_HOP_HEADERS]


def _header_or_param_items(values: object) -> list[tuple[str, str]]:
    """Return key/value pairs from httpx/starlette multi-maps or plain dicts."""
    if hasattr(values, "multi_items"):
        return list(values.multi_items())  # type: ignore[no-any-return]
    if hasattr(values, "items"):
        return list(values.items())  # type: ignore[no-any-return]
    return []


def build_proxy_routers(service_url: str) -> tuple[APIRouter, APIRouter]:
    """
    Build two wildcard proxy routers that forward to the Plus sidecar.

    Args:
        service_url: Base URL of the Plus sidecar, e.g. "http://plus-sidecar:8001".

    Returns:
        (api_router, pub_router)
          api_router — forwards /plus/{path} → {service_url}/api/v1/plus/{path}
          pub_router — forwards /pub/{path}  → {service_url}/pub/{path}
                       and /api/v1/oembed    → {service_url}/api/v1/oembed
    """
    api_router = APIRouter()
    pub_router = APIRouter()

    @api_router.api_route(
        "/plus/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def proxy_plus_api(path: str, request: Request) -> Response:
        return await _forward(request, f"{service_url}/api/v1/plus/{path}")

    @pub_router.get("/pub/{path:path}", include_in_schema=False)
    async def proxy_pub(path: str, request: Request) -> Response:
        return await _forward(request, f"{service_url}/pub/{path}")

    @pub_router.get("/api/v1/oembed", include_in_schema=False)
    async def proxy_oembed(request: Request) -> Response:
        return await _forward(request, f"{service_url}/api/v1/oembed")

    return api_router, pub_router


async def _forward(request: Request, url: str) -> Response:
    """Forward a request to the Plus sidecar and stream the response back."""
    try:
        forwarded_params: list[tuple[str, str | int | float | None]] = [
            (key, value) for key, value in _header_or_param_items(request.query_params)
        ]

        response = await _proxy_client.request(
            method=request.method,
            url=url,
            # Strip the Host header so the sidecar doesn't reject the request.
            headers=_filter_proxy_headers(
                (k, v) for k, v in request.headers.items() if k.lower() != "host"
            ),
            content=await request.body(),
            params=forwarded_params,
        )
        response_headers = _filter_proxy_headers(_header_or_param_items(response.headers))
        proxied_response = Response(
            content=response.content,
            status_code=response.status_code,
        )
        proxied_response.raw_headers = [
            (key.encode("latin-1"), value.encode("latin-1"))
            for key, value in response_headers
        ]
        return proxied_response
    except httpx.TimeoutException:
        logger.error("Plus sidecar timed out: %s", url)
        return JSONResponse(
            status_code=504,
            content={"detail": "Plus service timed out. Please try again."},
        )
    except httpx.ConnectError:
        logger.error("Cannot reach Plus sidecar: %s", url)
        return JSONResponse(
            status_code=503,
            content={"detail": "Plus service is unavailable. Please try again later."},
        )
    except httpx.RequestError as exc:
        logger.error("Plus sidecar request failed %s: %s", url, exc)
        return JSONResponse(
            status_code=502,
            content={"detail": "Plus service error. Please try again later."},
        )


async def close_proxy_client() -> None:
    """Close the shared httpx client on app shutdown."""
    await _proxy_client.aclose()
