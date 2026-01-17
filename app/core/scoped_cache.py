"""
Shared cache utilities for scoped, namespaced caches.

Provides a thin wrapper to standardize key construction, TTL handling,
and timestamp augmentation across cache implementations.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from app.core.cache import InMemoryCache, RedisCache, create_cache
from app.core.config import settings
from app.core.logging_config import LogCategory, log_warning

logger = logging.getLogger(LogCategory.APP)


class ScopedCache:
    """
    Base class for cache wrappers with namespaced keys.

    Each cache entry is keyed as: "{namespace}:{cache_type}:{scope_id}".
    """

    def __init__(self, namespace: str, cache_backend=None, log: Optional[logging.Logger] = None):
        self._namespace = namespace
        self._cache = cache_backend or create_cache(settings.redis_url)
        self._logger = log or logger

    def _make_key(self, scope_id: str, cache_type: str) -> str:
        """
        Generate a namespaced cache key.

        Args:
            scope_id: Identifier for the cache scope (must not contain ':')
            cache_type: Type of cache entry (must not contain ':')

        Returns:
            Cache key in format: "{namespace}:{cache_type}:{scope_id}"

        Raises:
            ValueError: If scope_id or cache_type contains ':' character
        """
        scope_id = str(scope_id)
        cache_type = str(cache_type)
        if ':' in cache_type:
            raise ValueError(f"cache_type must not contain ':' character, got: {cache_type}")
        if ':' in scope_id:
            raise ValueError(f"scope_id must not contain ':' character, got: {scope_id}")
        return f"{self._namespace}:{cache_type}:{scope_id}"

    @staticmethod
    def _with_timestamps(value: Dict[str, Any], *fields: str) -> Dict[str, Any]:
        """Return a copy of value with one or more timestamp fields added."""
        stamped = dict(value)
        timestamp = datetime.now(timezone.utc).isoformat()
        for field in fields:
            stamped[field] = timestamp
        return stamped

    def get(self, scope_id: str, cache_type: str) -> Optional[Dict[str, Any]]:
        """Fetch a cached value by scope and type."""
        try:
            key = self._make_key(scope_id, cache_type)
            return self._cache.get(key)
        except Exception as e:
            self._logger.error(
                f"Cache get operation failed: scope_id={scope_id}, cache_type={cache_type}, error={type(e).__name__}: {e}"
            )
            return None

    def set(self, scope_id: str, cache_type: str, value: Dict[str, Any], ttl_seconds: Optional[int]) -> None:
        """Store a cached value by scope and type."""
        try:
            key = self._make_key(scope_id, cache_type)
            self._cache.set(key, value, ex=ttl_seconds)
        except Exception as e:
            self._logger.error(
                f"Cache set operation failed: scope_id={scope_id}, cache_type={cache_type}, error={type(e).__name__}: {e}"
            )

    def delete(self, scope_id: str, cache_type: str) -> None:
        """Delete a cached value by scope and type."""
        try:
            key = self._make_key(scope_id, cache_type)
            self._cache.delete(key)
        except Exception as e:
            self._logger.error(
                f"Cache delete operation failed: scope_id={scope_id}, cache_type={cache_type}, error={type(e).__name__}: {e}"
            )

    def invalidate(self, scope_id: str, cache_types: Iterable[str]) -> None:
        """Delete multiple cache entries for a scope."""
        for cache_type in cache_types:
            self.delete(scope_id, cache_type)

    def clear_all(self) -> None:
        """Clear all cache entries in this namespace (use with caution)."""
        pattern = f"{self._namespace}:*"
        log_warning(f"Clearing cache data for namespace: {self._namespace}", namespace=self._namespace)

        deleted_count = 0
        batch_size = 100

        if isinstance(self._cache, RedisCache):
            try:
                redis_client = self._cache._redis
                keys_to_delete = []

                for key in redis_client.scan_iter(match=pattern, count=batch_size):
                    keys_to_delete.append(key)
                    if len(keys_to_delete) >= batch_size:
                        redis_client.delete(*keys_to_delete)
                        deleted_count += len(keys_to_delete)
                        keys_to_delete = []

                if keys_to_delete:
                    redis_client.delete(*keys_to_delete)
                    deleted_count += len(keys_to_delete)

                if deleted_count > 0:
                    self._logger.info(f"Cleared {deleted_count} cache keys for namespace: {self._namespace}")
                else:
                    self._logger.info(f"No cache keys found for namespace: {self._namespace}")
            except AttributeError:
                raise RuntimeError(
                    f"Redis cache backend does not support pattern-based deletion. "
                    f"Cannot clear namespace '{self._namespace}' without affecting other cache data."
                )
            except Exception as e:
                self._logger.error(
                    f"Failed to clear namespace cache: namespace={self._namespace}, "
                    f"error={type(e).__name__}: {e}"
                )
                raise
        elif isinstance(self._cache, InMemoryCache):
            try:
                keys_to_delete = [
                    key for key in self._cache._store.keys()
                    if key.startswith(f"{self._namespace}:")
                ]
                for key in keys_to_delete:
                    self._cache.delete(key)
                deleted_count = len(keys_to_delete)

                if deleted_count > 0:
                    self._logger.info(f"Cleared {deleted_count} cache keys for namespace: {self._namespace}")
                else:
                    self._logger.info(f"No cache keys found for namespace: {self._namespace}")
            except AttributeError:
                raise RuntimeError(
                    f"In-memory cache backend does not support pattern-based deletion. "
                    f"Cannot clear namespace '{self._namespace}' without affecting other cache data."
                )
            except Exception as e:
                self._logger.error(
                    f"Failed to clear namespace cache: namespace={self._namespace}, "
                    f"error={type(e).__name__}: {e}"
                )
                raise
        else:
            raise RuntimeError(
                f"Cache backend type '{type(self._cache).__name__}' does not support pattern-based deletion. "
                f"Cannot clear namespace '{self._namespace}' without affecting other cache data. "
                f"Backend must implement scan_iter (Redis) or provide key iteration (InMemoryCache)."
            )
