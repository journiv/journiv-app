from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.cors import add_cors_middleware

FRONTEND_ORIGIN = "http://localhost:7357"


def _create_test_app() -> FastAPI:
    app = FastAPI()
    add_cors_middleware(app, [FRONTEND_ORIGIN])

    @app.get("/api/v1/memory")
    def memory() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_video_range_preflight_is_allowed() -> None:
    client = TestClient(_create_test_app())

    response = client.options(
        "/api/v1/memory",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Range",
        },
    )

    assert response.status_code == 200
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "range" in allowed_headers
    assert "x-journiv-client" in allowed_headers


def test_video_range_response_headers_are_exposed() -> None:
    client = TestClient(_create_test_app())

    response = client.get("/api/v1/memory", headers={"Origin": FRONTEND_ORIGIN})

    exposed_headers = response.headers["access-control-expose-headers"].lower()
    assert "accept-ranges" in exposed_headers
    assert "content-length" in exposed_headers
    assert "content-range" in exposed_headers
