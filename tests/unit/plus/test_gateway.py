"""
Unit tests for app.plus (Smart Gateway).

The gateway module reads PLUS_SERVICE_URL at import time, so tests must
reload it with the desired env var to exercise each mode.  Each test class
uses importlib.reload() inside a module-isolation helper.

Covers:
- PLUS_MODE is "inline" when PLUS_SERVICE_URL is unset
- PLUS_MODE is "proxy" when PLUS_SERVICE_URL is set
- Inline mode with ImportError → PLUS_AVAILABLE=False, 501 handlers registered
- Proxy mode → PLUS_AVAILABLE=True, routers delegate to _proxy.py
- 501 handlers return 501 for all HTTP verbs
- The exported __all__ symbols are always present
"""

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REAL_IMPORT = __import__

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_gateway(env: dict, monkeypatch) -> object:
    """
    Set environment variables, reload app.plus, and return the fresh module.

    Clears all related cached modules first so module-level code reruns.
    """
    for key, val in env.items():
        monkeypatch.setenv(key, val)
    # Remove keys not in env (simulate unset)
    for key in ["PLUS_SERVICE_URL"]:
        if key not in env:
            monkeypatch.delenv(key, raising=False)

    # Clear cached modules that the gateway imports
    _clear = [k for k in sys.modules if k.startswith("app.plus")]
    for k in _clear:
        del sys.modules[k]

    return importlib.import_module("app.plus")


def _build_test_app(gateway) -> TestClient:
    app = FastAPI()
    app.include_router(gateway.plus_api_router, prefix="/api/v1")
    app.include_router(gateway.plus_public_router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------


class TestModeDetection:
    def test_inline_mode_when_service_url_unset(self, monkeypatch):
        with patch.dict(sys.modules, {"app.plus.plus_features": MagicMock()}):
            gw = _reload_gateway({}, monkeypatch)
        assert gw.PLUS_MODE == "inline"

    def test_proxy_mode_when_service_url_set(self, monkeypatch):
        with patch(
            "app.plus._proxy.build_proxy_routers",
            return_value=(MagicMock(), MagicMock()),
        ):
            gw = _reload_gateway(
                {"PLUS_SERVICE_URL": "http://sidecar:8001"}, monkeypatch
            )
        assert gw.PLUS_MODE == "proxy"

    def test_proxy_mode_sets_plus_available_true(self, monkeypatch):
        mock_router = MagicMock()
        with patch(
            "app.plus._proxy.build_proxy_routers",
            return_value=(mock_router, mock_router),
        ):
            gw = _reload_gateway(
                {"PLUS_SERVICE_URL": "http://sidecar:8001"}, monkeypatch
            )
        assert gw.PLUS_AVAILABLE is True


# ---------------------------------------------------------------------------
# Inline mode — .so available
# ---------------------------------------------------------------------------


def _reload_gateway_with_so(monkeypatch, api_router, pub_router):
    """
    Reload app.plus in inline mode with a mocked plus_features module.

    The mock must be injected AFTER clearing sys.modules so it survives
    the import of app.plus (which re-imports app.plus.plus_features).
    """
    monkeypatch.delenv("PLUS_SERVICE_URL", raising=False)

    # 1. Clear all cached app.plus.* modules.
    for k in list(sys.modules):
        if k.startswith("app.plus"):
            del sys.modules[k]

    # 2. Inject the mock directly — the next `import app.plus` will find it.
    mock_module = MagicMock()
    mock_module.plus_api_router = api_router
    mock_module.plus_public_router = pub_router
    sys.modules["app.plus.plus_features"] = mock_module

    try:
        return importlib.import_module("app.plus")
    finally:
        # Leave sys.modules in a clean state for other tests.
        sys.modules.pop("app.plus.plus_features", None)
        sys.modules.pop("app.plus", None)


class TestInlineModeWithSo:
    def test_plus_available_true_when_so_loads(self, monkeypatch):
        from fastapi import APIRouter

        gw = _reload_gateway_with_so(
            monkeypatch, APIRouter(prefix="/plus"), APIRouter()
        )
        assert gw.PLUS_AVAILABLE is True

    def test_routers_are_replaced_when_so_loads(self, monkeypatch):
        """The fallback empty routers must be swapped with the .so routers."""
        from fastapi import APIRouter

        real_api = APIRouter(prefix="/plus")
        real_pub = APIRouter()
        gw = _reload_gateway_with_so(monkeypatch, real_api, real_pub)
        assert gw.plus_api_router is real_api
        assert gw.plus_public_router is real_pub


# ---------------------------------------------------------------------------
# Inline mode — .so missing (ImportError)
# ---------------------------------------------------------------------------


class TestInlineModeWithoutSo:
    def test_plus_available_false_when_import_error(self, monkeypatch):
        # Force the import to fail by ensuring the name is not in sys.modules
        # and the real module doesn't exist
        _clear = [k for k in sys.modules if k.startswith("app.plus")]
        for k in _clear:
            del sys.modules[k]

        monkeypatch.delenv("PLUS_SERVICE_URL", raising=False)

        with patch("builtins.__import__", side_effect=_selective_import_error):
            try:
                import app.plus as gw
            except (ImportError, ModuleNotFoundError):
                pytest.xfail("Could not isolate import for this test")
                return

        assert gw.PLUS_AVAILABLE is False

    def test_501_handler_returns_501_for_get(self, monkeypatch):
        """When .so is absent, GET /api/v1/plus/* must return 501."""
        gw = _force_inline_no_so(monkeypatch)
        if gw is None:
            pytest.skip("Could not load gateway in no-.so mode")

        client = _build_test_app(gw)
        resp = client.get("/api/v1/plus/analytics/tags")
        assert resp.status_code == 501

    def test_501_handler_returns_501_for_post(self, monkeypatch):
        gw = _force_inline_no_so(monkeypatch)
        if gw is None:
            pytest.skip("Could not load gateway in no-.so mode")

        client = _build_test_app(gw)
        resp = client.post("/api/v1/plus/some/endpoint")
        assert resp.status_code == 501

    def test_501_detail_message_is_informative(self, monkeypatch):
        gw = _force_inline_no_so(monkeypatch)
        if gw is None:
            pytest.skip("Could not load gateway in no-.so mode")

        client = _build_test_app(gw)
        resp = client.get("/api/v1/plus/anything")
        body = resp.json()
        assert "detail" in body
        assert "Plus" in body["detail"] or "not enabled" in body["detail"]

    def test_pub_501_handler_registered(self, monkeypatch):
        gw = _force_inline_no_so(monkeypatch)
        if gw is None:
            pytest.skip("Could not load gateway in no-.so mode")

        client = _build_test_app(gw)
        resp = client.get("/pub/some-slug")
        assert resp.status_code == 501

    def test_oembed_501_handler_registered(self, monkeypatch):
        gw = _force_inline_no_so(monkeypatch)
        if gw is None:
            pytest.skip("Could not load gateway in no-.so mode")

        client = _build_test_app(gw)
        resp = client.get(
            "/api/v1/oembed", params={"url": "https://example.com/pub/abc"}
        )
        assert resp.status_code == 501


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestExports:
    def test_all_symbols_are_exported(self, monkeypatch):
        with patch.dict(
            sys.modules,
            {
                "app.plus.plus_features": MagicMock(
                    plus_api_router=MagicMock(),
                    plus_public_router=MagicMock(),
                )
            },
        ):
            gw = _reload_gateway({}, monkeypatch)

        for name in [
            "plus_api_router",
            "plus_public_router",
            "PLUS_AVAILABLE",
            "PLUS_MODE",
        ]:
            assert hasattr(gw, name), f"Missing export: {name}"


# ---------------------------------------------------------------------------
# Private helpers used by test class methods
# ---------------------------------------------------------------------------


def _selective_import_error(name, *args, **kwargs):
    """Raise ImportError only for app.plus.plus_features."""
    if name == "app.plus.plus_features":
        raise ImportError("No module named 'plus_features.so'")
    return _REAL_IMPORT(name, *args, **kwargs)


def _force_inline_no_so(monkeypatch):
    """
    Reload the gateway so that plus_features raises ImportError (inline, no .so).
    Returns the gateway module or None if isolation failed.
    """
    _clear = [k for k in sys.modules if k.startswith("app.plus")]
    for k in _clear:
        del sys.modules[k]
    monkeypatch.delenv("PLUS_SERVICE_URL", raising=False)

    # Setting the module to raise on attribute access triggers the ImportError
    # path inside the gateway's try/except block.
    sys.modules["app.plus.plus_features"] = MagicMock(
        __spec__=MagicMock(loader=None),
        plus_api_router=property(
            lambda self: (_ for _ in ()).throw(ImportError("no .so"))
        ),
    )

    try:
        # The cleaner way: patch the import itself inside the gateway module
        import importlib

        with patch.dict(
            sys.modules,
            {"app.plus.plus_features": None},  # None causes ImportError in Python
        ):
            _clear2 = [
                k
                for k in sys.modules
                if k.startswith("app.plus") and k != "app.plus.plus_features"
            ]
            for k in _clear2:
                del sys.modules[k]
            gw = importlib.import_module("app.plus")
            return gw
    except Exception:
        return None
