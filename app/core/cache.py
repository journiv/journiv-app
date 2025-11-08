"""
Cache service for OIDC state management and temporary data storage.

Supports Redis (production) and in-memory fallback (development).
"""
import json
import logging
import time
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)


class InMemoryCache:
    """
    Simple in-memory cache with TTL support for development.

    This is NOT suitable for production with multiple workers.
    Use Redis for production deployments.
    """

    def __init__(self):
        self._store: Dict[str, tuple[Any, Optional[float]]] = {}
        logger.warning(
            "Using in-memory cache. This is only suitable for development "
            "with a single worker. Use Redis (REDIS_URL) for production."
        )

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        """
        Set a key-value pair with optional expiration.

        Args:
            key: Cache key
            value: Value to store
            ex: Expiration time in seconds (optional)
        """
        expiry = time.time() + ex if ex else None
        self._store[key] = (value, expiry)

    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if key not in self._store:
            return None

        value, expiry = self._store[key]

        # Check if expired
        if expiry and time.time() > expiry:
            del self._store[key]
            return None

        return value

    def delete(self, key: str) -> None:
        """
        Delete a key from cache.

        Args:
            key: Cache key
        """
        self._store.pop(key, None)

    def clear(self) -> None:
        """Clear all cached data."""
        self._store.clear()


class RedisCache:
    """
    Redis-based cache for production use.

    Supports large deployments with multiple workers.
    """

    def __init__(self, redis_client):
        self._redis = redis_client
        logger.info("Using Redis cache for OIDC state management")

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        """
        Set a key-value pair with optional expiration.

        Args:
            key: Cache key
            value: Value to store (will be JSON serialized)
            ex: Expiration time in seconds (optional)
        """
        serialized = json.dumps(value)
        if ex:
            self._redis.setex(key, ex, serialized)
        else:
            self._redis.set(key, serialized)

    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        value = self._redis.get(key)
        if value is None:
            return None
        return json.loads(value)

    def delete(self, key: str) -> None:
        """
        Delete a key from cache.

        Args:
            key: Cache key
        """
        self._redis.delete(key)

    def clear(self) -> None:
        """Clear all cached data (use with caution!)."""
        self._redis.flushdb()


def create_cache(redis_url: Optional[str] = None):
    """
    Create a cache instance based on configuration.

    Args:
        redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
                  If None, falls back to in-memory cache

    Returns:
        Cache instance (RedisCache or InMemoryCache)
    """
    if redis_url:
        try:
            import redis

            # Parse Redis URL and create client
            redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )

            # Test connection
            redis_client.ping()

            return RedisCache(redis_client)
        except ImportError:
            logger.error(
                "Redis URL provided but 'redis' package not installed. "
                "Falling back to in-memory cache."
            )
        except Exception as exc:
            logger.error(
                f"Failed to connect to Redis at {redis_url}: {exc}. "
                "Falling back to in-memory cache."
            )

    # Fallback to in-memory cache
    return InMemoryCache()
