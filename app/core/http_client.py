"""
Shared HTTP client for internal services.

Provides a singleton httpx.AsyncClient for connection pooling and efficient resource usage.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import httpx

from app.core.logging_config import log_info

_client: Optional[httpx.AsyncClient] = None
_client_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    """Get or create the client lock."""
    global _client_lock
    if _client_lock is None:
        _client_lock = asyncio.Lock()
    return _client_lock


async def get_http_client() -> httpx.AsyncClient:
    """
    Get the shared AsyncClient instance.

    Creates a new instance if one doesn't exist or is closed.

    This uses a lazy initialization pattern which ensures a client is always available
    when needed. Lifecycle management (cleanup) is handled by the app's startup/shutdown
    events to ensure resources are properly released.
    """
    global _client
    if _client is None or _client.is_closed:
        async with _get_lock():
            if _client is None or _client.is_closed:
                _client = httpx.AsyncClient(timeout=10.0)
                log_info("HTTP client created", timeout=10.0)
    assert _client is not None
    return _client


async def close_http_client():
    """Close the shared client if it exists."""
    global _client
    async with _get_lock():
        if _client and not _client.is_closed:
            await _client.aclose()
            _client = None
            log_info("HTTP client closed")


@asynccontextmanager
async def http_client_context():
    """
    Context manager that yields the shared client.
    Does NOT close the client on exit (it's shared).
    """
    client = await get_http_client()
    yield client
