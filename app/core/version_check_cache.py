"""
Version check cache for Journiv Plus integration.

Provides caching of version check results to reduce API calls to the Plus server
and enable offline access to update information.

Uses Redis when available (production), falls back to in-memory cache (dev).
"""
import logging
import threading
from typing import Any, Dict, Iterable, Optional

from app.core.config import VERSION_CHECK_CACHE_TTL
from app.core.logging_config import LogCategory, log_info
from app.core.scoped_cache import ScopedCache

logger = logging.getLogger(LogCategory.APP)


class VersionCheckCache(ScopedCache):
    """
    Cache wrapper for version check results.

    Caches version check results to minimize Plus server calls and enable
    offline access to update information.
    """

    def __init__(self, cache_backend=None):
        """
        Initialize version check cache.

        Args:
            cache_backend: Optional cache backend (for testing).
                          If None, creates cache from settings.
        """
        super().__init__("version_check", cache_backend=cache_backend, log=logger)
        logger.debug("VersionCheckCache initialized")

    def get_latest_success(self, instance_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get cached latest successful version check result.

        Args:
            instance_uuid: Instance UUID

        Returns:
            Version check result dict or None if not cached
        """
        cached = self.get(instance_uuid, "latest_success")

        if cached is not None:
            logger.debug(f"Version check cache HIT (success) for instance={instance_uuid}")
            return cached

        logger.debug(f"Version check cache MISS (success) for instance={instance_uuid}")
        return None

    def set_latest_success(self, instance_uuid: str, result: Dict[str, Any]) -> None:
        """
        Cache latest successful version check result.

        Args:
            instance_uuid: Instance UUID
            result: Version check result dictionary
        """
        value = self._with_timestamps(result, "checked_at", "cached_at")
        self.set(instance_uuid, "latest_success", value, VERSION_CHECK_CACHE_TTL)
        log_info(
            f"Cached version check (success) for instance={instance_uuid}",
            instance_uuid=instance_uuid,
            ttl_seconds=VERSION_CHECK_CACHE_TTL
        )

    def get_latest_all(self, instance_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get cached latest version check result (successful or not).

        Args:
            instance_uuid: Instance UUID

        Returns:
            Version check result dict or None if not cached
        """
        cached = self.get(instance_uuid, "latest_all")

        if cached is not None:
            logger.debug(f"Version check cache HIT (all) for instance={instance_uuid}")
            return cached

        logger.debug(f"Version check cache MISS (all) for instance={instance_uuid}")
        return None

    def set_latest_all(self, instance_uuid: str, result: Dict[str, Any]) -> None:
        """
        Cache latest version check result (any status).

        Args:
            instance_uuid: Instance UUID
            result: Version check result dictionary
        """
        value = self._with_timestamps(result, "checked_at", "cached_at")
        self.set(instance_uuid, "latest_all", value, VERSION_CHECK_CACHE_TTL)
        log_info(
            f"Cached version check (all) for instance={instance_uuid}",
            instance_uuid=instance_uuid,
            ttl_seconds=VERSION_CHECK_CACHE_TTL
        )

    def invalidate(self, scope_id: str, cache_types: Iterable[str]) -> None:
        """
        Invalidate cached version check data for a scope.

        Args:
            scope_id: Instance or scope identifier to invalidate.
            cache_types: Iterable of cache type names to clear.
        """
        super().invalidate(scope_id, cache_types)

        log_info(f"Invalidated version check cache for instance={scope_id}", instance_uuid=scope_id)


# Global version check cache instance
_version_check_cache: Optional[VersionCheckCache] = None
_version_check_cache_lock = threading.Lock()


def get_version_check_cache() -> VersionCheckCache:
    """
    Get or create the global version check cache instance.

    Returns:
        VersionCheckCache singleton instance
    """
    global _version_check_cache

    if _version_check_cache is None:
        with _version_check_cache_lock:
            if _version_check_cache is None:
                _version_check_cache = VersionCheckCache()

    assert _version_check_cache is not None
    return _version_check_cache
