"""Dual-SPA serving and backend-route isolation tests."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.frontend import create_frontend_router


@pytest.fixture
def frontend_client(tmp_path: Path) -> TestClient:
    react = tmp_path / "react"
    legacy = tmp_path / "legacy"
    (react / "assets").mkdir(parents=True)
    legacy.mkdir()
    (react / "index.html").write_text(
        '<div id="react-app"></div><script src="/assets/app-hash.js"></script>'
    )
    (react / "assets" / "app-hash.js").write_text("globalThis.REACT = true;")
    (react / "service-worker.js").write_text("")
    (legacy / "index.html").write_text(
        '<base href="/legacy/"><div id="flutter-app"></div>'
    )
    (legacy / "main.dart.js").write_text("globalThis.FLUTTER = true;")
    (legacy / "flutter_service_worker.js").write_text("")
    retirement_worker = tmp_path / "retire.js"
    retirement_worker.write_text(
        'caches.delete("flutter-app-cache"); self.registration.unregister();'
    )

    app = FastAPI()

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/instance/config")
    async def instance_config():
        return {"kind": "backend"}

    @app.get("/api/v1/auth/oidc/callback")
    async def oidc_callback():
        return {"kind": "backend"}

    @app.get("/pub/{identifier}")
    async def published(identifier: str):
        return {"identifier": identifier}

    @app.get("/media/{path:path}")
    async def media(path: str):
        return {"path": path}

    app.include_router(
        create_frontend_router(react, legacy, retirement_worker)
    )
    return TestClient(app)


def test_react_is_root_spa_with_nested_route_fallback(frontend_client: TestClient):
    for path in ("/", "/settings/profile", "/journals/example"):
        response = frontend_client.get(path)
        assert response.status_code == 200
        assert 'id="react-app"' in response.text
        assert response.headers["cache-control"].startswith("no-cache")


def test_flutter_is_legacy_spa_with_nested_route_fallback(
    frontend_client: TestClient,
):
    redirect = frontend_client.get("/legacy", follow_redirects=False)
    assert redirect.status_code == 308
    assert redirect.headers["location"] == "/legacy/"

    for path in ("/legacy/", "/legacy/settings/profile"):
        response = frontend_client.get(path)
        assert response.status_code == 200
        assert 'id="flutter-app"' in response.text
        assert '<base href="/legacy/">' in response.text


def test_valid_assets_are_served_with_asset_content_types_and_cache_policy(
    frontend_client: TestClient,
):
    react_asset = frontend_client.get("/assets/app-hash.js")
    assert react_asset.status_code == 200
    assert react_asset.headers["content-type"].startswith(
        ("application/javascript", "text/javascript")
    )
    assert react_asset.headers["cache-control"].endswith("immutable")

    flutter_asset = frontend_client.get("/legacy/main.dart.js")
    assert flutter_asset.status_code == 200
    assert flutter_asset.headers["content-type"].startswith(
        ("application/javascript", "text/javascript")
    )
    assert "immutable" not in flutter_asset.headers["cache-control"]


@pytest.mark.parametrize(
    "path",
    [
        "/assets/missing.js",
        "/missing.css",
        "/legacy/assets/missing.png",
        "/legacy/missing.js",
    ],
)
def test_missing_assets_do_not_return_spa_html(
    frontend_client: TestClient, path: str
):
    response = frontend_client.get(path)
    assert response.status_code == 404
    assert "react-app" not in response.text
    assert "flutter-app" not in response.text


@pytest.mark.parametrize(
    "path",
    ["/timeline/2024.01.01", "/journals/my.trip", "/legacy/entry/2024.01.01"],
)
def test_browser_navigation_to_dotted_client_route_falls_back_to_spa(
    frontend_client: TestClient, path: str
):
    # A real browser navigation sends Accept: text/html. A client-side route may
    # legitimately contain a dot, so it must not be mistaken for a missing asset.
    response = frontend_client.get(path, headers={"accept": "text/html"})
    assert response.status_code == 200
    assert ("flutter-app" if path.startswith("/legacy/") else "react-app") in (
        response.text
    )

    # The same path fetched as an asset (no text/html) is still a real 404.
    assert frontend_client.get(path, headers={"accept": "*/*"}).status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/health",
        "/api/v1/instance/config",
        "/api/v1/auth/oidc/callback",
        "/pub/public-id",
        "/media/example.jpg",
        "/openapi.json",
        "/docs",
    ],
)
def test_backend_routes_are_never_intercepted(
    frontend_client: TestClient, path: str
):
    response = frontend_client.get(path)
    assert response.status_code == 200
    assert "react-app" not in response.text
    assert "flutter-app" not in response.text


def test_unknown_backend_namespaces_are_not_spa_routes(
    frontend_client: TestClient,
):
    for path in ("/api/not-a-route", "/pub/not/a/route", "/docs/not-a-route"):
        response = frontend_client.get(path)
        assert response.status_code == 404
        assert "react-app" not in response.text


def test_root_flutter_service_worker_is_a_no_cache_retirement_worker(
    frontend_client: TestClient,
):
    response = frontend_client.get("/flutter_service_worker.js")
    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("no-cache")
    assert response.headers["service-worker-allowed"] == "/"
    assert "flutter-app-cache" in response.text
    assert "unregister" in response.text


def test_legacy_worker_cannot_claim_root_scope(frontend_client: TestClient):
    response = frontend_client.get("/legacy/flutter_service_worker.js")
    assert response.status_code == 200
    assert response.headers["service-worker-allowed"] == "/legacy/"


def test_future_react_worker_can_claim_only_its_intended_root_scope(
    frontend_client: TestClient,
):
    response = frontend_client.get("/service-worker.js")
    assert response.status_code == 200
    assert response.headers["service-worker-allowed"] == "/"


def test_real_app_backend_routes_remain_backend_owned():
    from app.main import app

    client = TestClient(app)
    expected_statuses = {
        "/api/v1/health": 200,
        "/api/v1/auth/oidc/callback": 404,
        "/pub/not-published": 501,
        "/openapi.json": 200,
        "/api/v1/openapi.json": 200,
        "/docs": 200,
    }
    for path, expected_status in expected_statuses.items():
        response = client.get(path)
        assert response.status_code == expected_status
        assert (
            "text/html" not in response.headers.get("content-type", "")
            or path == "/docs"
        )
