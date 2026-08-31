"""OIDC request and redirect contract coverage."""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


class _TicketCache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: object) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


def _openapi_operation(path: str, method: str) -> dict:
    return app.openapi()["paths"][path][method]


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
