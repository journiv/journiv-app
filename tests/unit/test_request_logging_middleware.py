import logging

import pytest

from app.core.config import settings
from app.middleware.request_logging import RequestLoggingMiddleware


async def _ok_app(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [],
        }
    )
    await send({"type": "http.response.body", "body": b"ok"})


async def _not_found_app(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 404,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": b'{"detail":"Missing"}'})


async def _run_request(app):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/health",
        "client": ("127.0.0.1", 12345),
    }
    await app(scope, receive, send)
    return messages


def _response_headers(messages):
    start = next(message for message in messages if message["type"] == "http.response.start")
    return dict(start["headers"])


@pytest.mark.asyncio
async def test_successful_requests_are_quiet_by_default(monkeypatch, caplog):
    monkeypatch.setattr(settings, "log_http_requests", False)
    middleware = RequestLoggingMiddleware(_ok_app)

    with caplog.at_level(logging.INFO, logger="app.middleware.request_logging"):
        messages = await _run_request(middleware)

    assert b"x-request-id" in _response_headers(messages)
    assert "Request started" not in caplog.text
    assert "Request completed successfully" not in caplog.text


@pytest.mark.asyncio
async def test_successful_request_logging_can_be_enabled(monkeypatch, caplog):
    monkeypatch.setattr(settings, "log_http_requests", True)
    middleware = RequestLoggingMiddleware(_ok_app)

    with caplog.at_level(logging.INFO, logger="app.middleware.request_logging"):
        await _run_request(middleware)

    assert "Request started" in caplog.text
    assert "Request completed successfully" in caplog.text


@pytest.mark.asyncio
async def test_client_errors_are_logged_when_successful_requests_are_quiet(monkeypatch, caplog):
    monkeypatch.setattr(settings, "log_http_requests", False)
    middleware = RequestLoggingMiddleware(_not_found_app)

    with caplog.at_level(logging.WARNING, logger="app.middleware.request_logging"):
        await _run_request(middleware)

    assert "Request completed with client error" in caplog.text
