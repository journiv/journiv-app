import gzip

import pytest

from app.middleware.compression import MediaSafeGZipMiddleware, is_compressible

BODY = b"x" * 4096


def _app(status: int, content_type: str, body: bytes = BODY):
    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", content_type.encode()),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    return app


async def _run(app, headers):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/media/1/signed",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    await MediaSafeGZipMiddleware(app, minimum_size=1024)(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return {k.decode().lower(): v.decode() for k, v in start["headers"]}, body


@pytest.mark.asyncio
async def test_json_is_still_gzipped():
    headers, body = await _run(_app(200, "application/json"), {"Accept-Encoding": "gzip"})

    assert headers["content-encoding"] == "gzip"
    assert gzip.decompress(body) == BODY


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", ["video/webm", "audio/mp4", "image/jpeg", "application/zip"])
async def test_media_is_sent_verbatim(content_type):
    headers, body = await _run(_app(200, content_type), {"Accept-Encoding": "gzip, deflate, br"})

    assert "content-encoding" not in headers
    assert headers["content-length"] == str(len(BODY))
    assert body == BODY


@pytest.mark.asyncio
async def test_partial_content_is_never_encoded():
    # Content-Range counts the file's bytes, so the body must be those bytes.
    headers, body = await _run(_app(206, "text/plain"), {"Accept-Encoding": "gzip"})

    assert "content-encoding" not in headers
    assert body == BODY


@pytest.mark.asyncio
async def test_range_requests_bypass_compression():
    headers, body = await _run(
        _app(200, "application/json"), {"Accept-Encoding": "gzip", "Range": "bytes=0-"}
    )

    assert "content-encoding" not in headers
    assert body == BODY


@pytest.mark.asyncio
async def test_clients_without_gzip_get_identity():
    headers, body = await _run(_app(200, "application/json"), {})

    assert "content-encoding" not in headers
    assert body == BODY


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("application/json", True),
        ("text/html; charset=utf-8", True),
        ("application/javascript", True),
        ("image/svg+xml", True),
        ("video/webm", False),
        ("audio/webm;codecs=opus", False),
        ("image/webp", False),
        ("font/woff2", False),
        ("application/octet-stream", False),
        ("", True),
    ],
)
def test_is_compressible(content_type, expected):
    assert is_compressible(content_type) is expected
