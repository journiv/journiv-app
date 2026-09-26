"""
Regression tests for shared HTTP clients reused across event loops.

`app.integrations.immich._get_client` and `app.core.http_client.get_http_client`
used to cache a single module-global `httpx.AsyncClient`. In the Celery worker,
some tasks run through `asyncio.run()` (a fresh loop each call, closed at the
end) while others run on a separate long-lived loop thread. A client created
on one loop, once that loop closed, raised
`RuntimeError: Event loop is closed` when reused on another loop — this was
the most likely root cause of Immich import jobs failing (issue #367).

Both helpers now key their cache by the running event loop, so a client is
never reused across loops. These tests reproduce the original failure with a
real keep-alive local HTTP server: without the fix, the second `asyncio.run()`
call reuses the first call's (now loop-closed) client and raises.
"""
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.core.http_client import get_http_client
from app.integrations.immich import _get_client


class _OKHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OKHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


async def _request_with(get_client_fn, url):
    client = get_client_fn()
    if asyncio.iscoroutine(client):
        client = await client
    response = await client.get(url)
    response.raise_for_status()
    return response.text


def test_immich_client_survives_across_asyncio_run_calls(local_server):
    """A client created in one asyncio.run() loop must not be reused, closed,
    on a later asyncio.run() call — each call gets a working client instead
    of raising RuntimeError: Event loop is closed."""
    first = asyncio.run(_request_with(_get_client, local_server))
    second = asyncio.run(_request_with(_get_client, local_server))

    assert first == "ok"
    assert second == "ok"


def test_shared_http_client_survives_across_asyncio_run_calls(local_server):
    """Same scenario for the generic shared client used outside Immich."""
    first = asyncio.run(_request_with(get_http_client, local_server))
    second = asyncio.run(_request_with(get_http_client, local_server))

    assert first == "ok"
    assert second == "ok"


def test_immich_client_and_shared_http_client_cached_per_loop(local_server):
    """Repeated calls on the SAME loop still reuse one client (no churn)."""

    async def scenario():
        immich_client_1 = _get_client()
        immich_client_2 = _get_client()
        shared_client_1 = await get_http_client()
        shared_client_2 = await get_http_client()
        return immich_client_1, immich_client_2, shared_client_1, shared_client_2

    immich_1, immich_2, shared_1, shared_2 = asyncio.run(scenario())

    assert immich_1 is immich_2
    assert shared_1 is shared_2


def test_clients_of_closed_loops_are_released(local_server):
    """A client's connections hold its loop, so a weak-keyed cache never let go
    of either: every asyncio.run() task leaked a client and its sockets. Entries
    for closed loops must be dropped on the next lookup."""
    from app.core import http_client
    from app.integrations import immich

    for _ in range(5):
        asyncio.run(_request_with(_get_client, local_server))
        asyncio.run(_request_with(get_http_client, local_server))

    async def cached_counts():
        _get_client()
        await get_http_client()
        return len(immich._clients), len(http_client._clients)

    assert asyncio.run(cached_counts()) == (1, 1)


def test_close_helpers_close_the_running_loops_clients(local_server):
    """Short-lived loops (integrations/tasks._run_with_session) close their
    clients before the loop ends instead of leaving sockets open until GC."""
    from app.core.http_client import close_http_client
    from app.integrations.immich import close_client

    async def scenario():
        immich_client = _get_client()
        shared_client = await get_http_client()
        await _request_with(_get_client, local_server)
        await close_client()
        await close_http_client()
        return immich_client, shared_client

    immich_client, shared_client = asyncio.run(scenario())

    assert immich_client.is_closed
    assert shared_client.is_closed
