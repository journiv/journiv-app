"""OIDC request and redirect contract coverage."""

from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.v1.endpoints.oidc import (
    LEGACY_FRONTEND,
    REACT_FRONTEND,
    _frontend_url,
    _request_frontend,
)
from app.core.config import settings
from app.main import app


class _TicketCache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: object, ex: int | None = None) -> None:  # noqa: ARG002
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


def _openapi_operation(path: str, method: str) -> dict:
    return app.openapi()["paths"][path][method]


def _request(referer: str | None = None) -> Request:
    headers = [(b"host", b"journiv.example")]
    if referer:
        headers.append((b"referer", referer.encode()))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/auth/oidc/login",
            "raw_path": b"/api/v1/auth/oidc/login",
            "query_string": b"",
            "headers": headers,
            "server": ("journiv.example", 443),
            "client": ("127.0.0.1", 1234),
        }
    )


def test_oidc_exchange_openapi_requires_typed_ticket_body():
    operation = _openapi_operation("/api/v1/auth/oidc/exchange", "post")
    request_body = operation["requestBody"]

    assert request_body["required"] is True
    schema = request_body["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/OidcTicketExchangeRequest"}

    model = app.openapi()["components"]["schemas"]["OidcTicketExchangeRequest"]
    assert model["required"] == ["ticket"]
    assert model["properties"]["ticket"]["type"] == "string"
    # A well-formed but unknown/expired ticket is 400; a missing or malformed
    # body is standard FastAPI request validation (422).
    assert "400" in operation["responses"]
    assert "422" in operation["responses"]


def test_oidc_redirect_endpoints_document_their_runtime_status():
    login_responses = _openapi_operation(
        "/api/v1/auth/oidc/login", "get"
    )["responses"]
    callback_responses = _openapi_operation(
        "/api/v1/auth/oidc/callback", "get"
    )["responses"]

    assert "302" in login_responses
    assert "200" not in login_responses
    assert "307" in callback_responses
    assert "200" not in callback_responses


def test_oidc_frontend_target_is_limited_to_same_origin_legacy_referrers():
    assert _request_frontend(_request()) == REACT_FRONTEND
    assert (
        _request_frontend(_request("https://journiv.example/legacy/settings"))
        == LEGACY_FRONTEND
    )
    assert (
        _request_frontend(_request("https://attacker.example/legacy/settings"))
        == REACT_FRONTEND
    )


def test_oidc_frontend_urls_use_only_fixed_react_or_legacy_paths(monkeypatch):
    monkeypatch.setattr(settings, "domain_name", "journiv.example")
    monkeypatch.setattr(settings, "domain_scheme", "https")
    request = _request()

    assert (
        _frontend_url(request, REACT_FRONTEND, "/oidc-finish?ticket=t")
        == "https://journiv.example/oidc-finish?ticket=t"
    )
    assert (
        _frontend_url(request, LEGACY_FRONTEND, "/oidc-finish?ticket=t")
        == "https://journiv.example/legacy/oidc-finish?ticket=t"
    )
    assert (
        _frontend_url(request, "untrusted", "/login?logout=success")
        == "https://journiv.example/login?logout=success"
    )


def test_oidc_exchange_preserves_single_use_ticket_behavior(monkeypatch):
    cache = _TicketCache()
    cache.set(
        "ticket:one-time",
        {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "user": {"id": "user-id", "email": "person@example.com"},
        },
    )
    monkeypatch.setattr(settings, "oidc_enabled", True)
    app.state.cache = cache
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/oidc/exchange", json={"ticket": "one-time"}
    )
    assert response.status_code == 200
    assert response.json()["access_token"] == "access-token"

    replay = client.post(
        "/api/v1/auth/oidc/exchange", json={"ticket": "one-time"}
    )
    assert replay.status_code == 400
    assert replay.json()["detail"] == "Invalid or expired ticket"


def test_oidc_exchange_rejects_invalid_body_with_422(monkeypatch):
    monkeypatch.setattr(settings, "oidc_enabled", True)
    app.state.cache = _TicketCache()
    client = TestClient(app)

    for payload in ({}, {"ticket": ""}, {"ticket": None}, {"ticket": 123}):
        response = client.post("/api/v1/auth/oidc/exchange", json=payload)
        assert response.status_code == 422, payload
        assert response.json()["error"] == "validation_error"

    malformed = client.post(
        "/api/v1/auth/oidc/exchange",
        content="not-json",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"] == "validation_error"
