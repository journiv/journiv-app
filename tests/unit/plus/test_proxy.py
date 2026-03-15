"""
Unit tests for app.plus._proxy — httpx proxy router builder.

Covers:
- _forward: successful response is forwarded (status code, body, headers)
- _forward: httpx.TimeoutException  → 504 JSON response
- _forward: httpx.ConnectError      → 503 JSON response
- _forward: Host header is stripped; other headers pass through
- _forward: query params are forwarded
- build_proxy_routers: returns two routers with correct wildcard routes
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    method: str = "GET",
    url: str = "http://testserver/plus/foo",
    headers: dict | None = None,
    body: bytes = b"",
    query_params: dict | None = None,
) -> MagicMock:
    """Create a minimal mock of fastapi.Request sufficient for _forward()."""
    req = MagicMock()
    req.method = method
    req.headers = {**(headers or {})}
    req.body = AsyncMock(return_value=body)
    req.query_params = query_params or {}
    return req


def _make_httpx_response(
    status_code: int = 200,
    content: bytes = b'{"ok": true}',
    headers: dict | None = None,
) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.content = content
    resp.headers = headers or {"content-type": "application/json"}
    return resp


# ---------------------------------------------------------------------------
# _forward — success path
# ---------------------------------------------------------------------------


class TestForwardSuccess:
    @pytest.mark.asyncio
    async def test_returns_response_with_correct_status_code(self):
        from app.plus._proxy import _forward

        mock_resp = _make_httpx_response(status_code=200)
        with patch("app.plus._proxy._proxy_client") as mock_client:
            mock_client.request = AsyncMock(return_value=mock_resp)
            request = _make_request()
            response = await _forward(request, "http://sidecar:8001/api/v1/plus/foo")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_response_body(self):
        from app.plus._proxy import _forward

        body = b'{"data": "hello"}'
        mock_resp = _make_httpx_response(content=body)
        with patch("app.plus._proxy._proxy_client") as mock_client:
            mock_client.request = AsyncMock(return_value=mock_resp)
            response = await _forward(_make_request(), "http://sidecar:8001/path")

        assert response.body == body

    @pytest.mark.asyncio
    async def test_host_header_is_stripped(self):
        """The 'host' header must not be forwarded — it would confuse the sidecar."""
        from app.plus._proxy import _forward

        captured_headers: dict = {}

        async def _capture(method, url, headers, content, params):
            captured_headers.update(headers)
            return _make_httpx_response()

        with patch("app.plus._proxy._proxy_client") as mock_client:
            mock_client.request = _capture
            request = _make_request(
                headers={
                    "host": "journiv.example.com",
                    "authorization": "Bearer token123",
                    "x-custom": "value",
                }
            )
            await _forward(request, "http://sidecar:8001/path")

        assert "host" not in captured_headers
        assert captured_headers.get("authorization") == "Bearer token123"
        assert captured_headers.get("x-custom") == "value"

    @pytest.mark.asyncio
    async def test_query_params_forwarded(self):
        from app.plus._proxy import _forward

        captured_params: dict = {}

        async def _capture(method, url, headers, content, params):
            captured_params.update(params)
            return _make_httpx_response()

        with patch("app.plus._proxy._proxy_client") as mock_client:
            mock_client.request = _capture
            request = _make_request(query_params={"days": "30", "tag_id": "abc"})
            await _forward(request, "http://sidecar:8001/path")

        assert captured_params["days"] == "30"
        assert captured_params["tag_id"] == "abc"

    @pytest.mark.asyncio
    async def test_request_method_is_forwarded(self):
        from app.plus._proxy import _forward

        captured_method: list = []

        async def _capture(method, url, headers, content, params):
            captured_method.append(method)
            return _make_httpx_response()

        with patch("app.plus._proxy._proxy_client") as mock_client:
            mock_client.request = _capture
            await _forward(_make_request(method="POST"), "http://sidecar:8001/path")

        assert captured_method == ["POST"]

    @pytest.mark.asyncio
    async def test_request_body_forwarded(self):
        from app.plus._proxy import _forward

        captured_body: list = []

        async def _capture(method, url, headers, content, params):
            captured_body.append(content)
            return _make_httpx_response()

        with patch("app.plus._proxy._proxy_client") as mock_client:
            mock_client.request = _capture
            await _forward(
                _make_request(body=b"request-payload"), "http://sidecar:8001/path"
            )

        assert captured_body == [b"request-payload"]

    @pytest.mark.asyncio
    async def test_non_200_status_code_passes_through(self):
        from app.plus._proxy import _forward

        mock_resp = _make_httpx_response(
            status_code=404, content=b'{"detail":"not found"}'
        )
        with patch("app.plus._proxy._proxy_client") as mock_client:
            mock_client.request = AsyncMock(return_value=mock_resp)
            response = await _forward(_make_request(), "http://sidecar:8001/path")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_hop_by_hop_response_headers_are_filtered(self):
        from app.plus._proxy import _forward

        mock_resp = _make_httpx_response(
            headers={
                "content-type": "application/json",
                "connection": "keep-alive",
                "transfer-encoding": "chunked",
                "x-test": "ok",
            }
        )
        with patch("app.plus._proxy._proxy_client") as mock_client:
            mock_client.request = AsyncMock(return_value=mock_resp)
            response = await _forward(_make_request(), "http://sidecar:8001/path")

        assert "connection" not in response.headers
        assert "transfer-encoding" not in response.headers
        assert response.headers.get("x-test") == "ok"


# ---------------------------------------------------------------------------
# _forward — error handling
# ---------------------------------------------------------------------------


class TestForwardErrorHandling:
    @pytest.mark.asyncio
    async def test_timeout_exception_returns_504(self):
        from app.plus._proxy import _forward

        with patch("app.plus._proxy._proxy_client") as mock_client:
            mock_client.request = AsyncMock(
                side_effect=httpx.TimeoutException("timed out", request=MagicMock())
            )
            response = await _forward(_make_request(), "http://sidecar:8001/path")

        assert response.status_code == 504
        import json

        body = json.loads(response.body)
        assert (
            "timed out" in body["detail"].lower() or "timeout" in body["detail"].lower()
        )

    @pytest.mark.asyncio
    async def test_connect_error_returns_503(self):
        from app.plus._proxy import _forward

        with patch("app.plus._proxy._proxy_client") as mock_client:
            mock_client.request = AsyncMock(
                side_effect=httpx.ConnectError(
                    "connection refused", request=MagicMock()
                )
            )
            response = await _forward(_make_request(), "http://sidecar:8001/path")

        assert response.status_code == 503
        import json

        body = json.loads(response.body)
        assert "unavailable" in body["detail"].lower()

    @pytest.mark.asyncio
    async def test_504_body_is_json_with_detail_key(self):
        from app.plus._proxy import _forward
        import json

        with patch("app.plus._proxy._proxy_client") as mock_client:
            mock_client.request = AsyncMock(
                side_effect=httpx.TimeoutException("t", request=MagicMock())
            )
            response = await _forward(_make_request(), "http://sidecar:8001/path")

        body = json.loads(response.body)
        assert "detail" in body

    @pytest.mark.asyncio
    async def test_503_body_is_json_with_detail_key(self):
        from app.plus._proxy import _forward
        import json

        with patch("app.plus._proxy._proxy_client") as mock_client:
            mock_client.request = AsyncMock(
                side_effect=httpx.ConnectError("c", request=MagicMock())
            )
            response = await _forward(_make_request(), "http://sidecar:8001/path")

        body = json.loads(response.body)
        assert "detail" in body


# ---------------------------------------------------------------------------
# build_proxy_routers — route structure
# ---------------------------------------------------------------------------


class TestBuildProxyRouters:
    def test_returns_two_routers(self):
        from app.plus._proxy import build_proxy_routers
        from fastapi import APIRouter

        api_router, pub_router = build_proxy_routers("http://sidecar:8001")
        assert isinstance(api_router, APIRouter)
        assert isinstance(pub_router, APIRouter)

    def test_api_router_forwards_plus_path(self):
        """GET /plus/analytics/tags should be proxied to the sidecar."""
        from app.plus._proxy import build_proxy_routers

        api_router, pub_router = build_proxy_routers("http://sidecar:8001")

        app = FastAPI()
        app.include_router(api_router)
        app.include_router(pub_router)
        client = TestClient(app, raise_server_exceptions=False)

        # The route /plus/{path:path} must exist (any response is fine —
        # the sidecar is not running in tests)
        routes = {r.path for r in app.routes}
        assert "/plus/{path:path}" in routes

    def test_pub_router_has_pub_path(self):
        from app.plus._proxy import build_proxy_routers

        api_router, pub_router = build_proxy_routers("http://sidecar:8001")
        app = FastAPI()
        app.include_router(pub_router)

        routes = {r.path for r in app.routes}
        assert "/pub/{path:path}" in routes

    def test_pub_router_has_oembed_path(self):
        from app.plus._proxy import build_proxy_routers

        api_router, pub_router = build_proxy_routers("http://sidecar:8001")
        app = FastAPI()
        app.include_router(pub_router)

        routes = {r.path for r in app.routes}
        assert "/api/v1/oembed" in routes

    def test_proxy_url_is_correct_for_api_path(self):
        """Verify the URL constructed for the sidecar call contains the path."""
        from app.plus._proxy import build_proxy_routers

        forwarded_urls: list = []

        async def _capture_forward(request, url):
            forwarded_urls.append(url)
            # Return a minimal response to avoid errors in TestClient
            from fastapi.responses import JSONResponse

            return JSONResponse({"ok": True})

        api_router, pub_router = build_proxy_routers("http://sidecar:8001")
        app = FastAPI()
        app.include_router(api_router)

        with patch("app.plus._proxy._forward", side_effect=_capture_forward):
            client = TestClient(app, raise_server_exceptions=False)
            client.get("/plus/analytics/tags")

        assert any("api/v1/plus/analytics/tags" in u for u in forwarded_urls)
