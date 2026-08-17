import os

from fastapi.testclient import TestClient

FRONTEND_ORIGIN = "http://localhost:7357"

os.environ["ENABLE_CORS"] = "true"
os.environ["CORS_ORIGINS"] = FRONTEND_ORIGIN

from app.main import app  # noqa: E402


def test_video_range_preflight_is_allowed() -> None:
    client = TestClient(app)

    response = client.options(
        "/api/v1/memory",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Range",
        },
    )

    assert response.status_code == 200
    assert "range" in response.headers["access-control-allow-headers"].lower()


def test_video_range_response_headers_are_exposed() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/memory", headers={"Origin": FRONTEND_ORIGIN})

    exposed_headers = response.headers["access-control-expose-headers"].lower()
    assert "accept-ranges" in exposed_headers
    assert "content-length" in exposed_headers
    assert "content-range" in exposed_headers
