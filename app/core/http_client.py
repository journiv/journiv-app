"""
Shared HTTP client for internal services.

Provides a singleton httpx.AsyncClient per event loop for connection pooling
and efficient resource usage.
"""
import asyncio
import threading
from contextlib import asynccontextmanager
from typing import Callable

import httpx

from app.core.logging_config import log_info

LoopClients = dict[asyncio.AbstractEventLoop, httpx.AsyncClient]

_clients: LoopClients = {}
_clients_guard = threading.Lock()


def loop_scoped_client(
    clients: LoopClients,
    guard: threading.Lock,
    factory: Callable[[], httpx.AsyncClient],
) -> httpx.AsyncClient:
    """
    Return the client cached for the running event loop, creating it if needed.

    An httpx client's connections are bound to the loop that opened them, so
    reusing one client across loops (the Celery worker runs some tasks through
    a fresh `asyncio.run()` loop each time and others on a long-lived loop
    thread) raises "RuntimeError: Event loop is closed".

    Entries for loops that have since closed are dropped on every call. They
    can never be used again, and a client's connections hold a reference to
    their loop, so a weak-keyed cache would never release them either. Tasks
    that end a loop should still `aclose_loop_client` first so sockets close
    promptly rather than at garbage collection.

    `threading.Lock` (not `asyncio.Lock`, which is itself bound to a loop)
    guards the dict since callers may run on different threads.
    """
    loop = asyncio.get_running_loop()
    with guard:
        for stale_loop in [cached for cached in clients if cached.is_closed()]:
            del clients[stale_loop]
        client = clients.get(loop)
        if client is None or client.is_closed:
            client = factory()
            clients[loop] = client
    return client


async def aclose_loop_client(clients: LoopClients, guard: threading.Lock) -> bool:
    """Close and forget the client cached for the running event loop, if any."""
    loop = asyncio.get_running_loop()
    with guard:
        client = clients.pop(loop, None)
    if client is None or client.is_closed:
        return False
    await client.aclose()
    return True


def _create_client() -> httpx.AsyncClient:
    log_info("HTTP client created", timeout=10.0)
    return httpx.AsyncClient(timeout=10.0)


async def get_http_client() -> httpx.AsyncClient:
    """
    Get the shared AsyncClient instance for the running event loop.

    Lifecycle management (cleanup) for the API process's client is handled
    by the app's startup/shutdown events to ensure resources are properly
    released; short-lived loops close theirs with `close_http_client`.
    """
    return loop_scoped_client(_clients, _clients_guard, _create_client)


async def close_http_client():
    """Close the shared client for the running event loop, if it exists."""
    if await aclose_loop_client(_clients, _clients_guard):
        log_info("HTTP client closed")


@asynccontextmanager
async def http_client_context():
    """
    Context manager that yields the shared client.
    Does NOT close the client on exit (it's shared).
    """
    client = await get_http_client()
    yield client
