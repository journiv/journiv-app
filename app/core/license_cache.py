"""
License information cache for Journiv Plus.

Provides 8-hour caching of license information from journiv-plus server
to reduce API calls.

Uses Redis when available (production), falls back to in-memory cache (dev).
"""
import logging
import threading
from typing import Iterable, Optional

from app.core.config import LICENSE_CACHE_TTL
from app.core.logging_config import LogCategory, log_debug, log_info
from app.core.scoped_cache import ScopedCache

logger = logging.getLogger(LogCategory.APP)

# Lock for thread-safe singleton initialization
_cache_lock = threading.Lock()


class LicenseCache(ScopedCache):
    """
    Cache wrapper for license information from journiv-plus server.

    Caches license info for 8 hours to minimize license server calls.
    Keys are scoped by install_id to support multiple installations.
    """

    def __init__(self, cache_backend=None):
        """
        Initialize license cache.

        Args:
            cache_backend: Optional cache backend (for testing).
                          If None, creates cache from settings.
        """
        super().__init__("license", cache_backend=cache_backend, log=logger)
        log_debug("LicenseCache initialized")

    def invalidate(self, scope_id: str, cache_types: Optional[Iterable[str]] = None) -> None:
        """
        Invalidate all cached license data for an installation.

        Use this when:
        - User registers a new license
        - User resets their license
        - License is manually invalidated

        Args:
            install_id: Installation UUID
        """
        types = list(cache_types) if cache_types is not None else ["info"]
        super().invalidate(scope_id, types)

        log_info(f"Invalidated license cache for install_id={scope_id}", install_id=scope_id)

    def get_info(self, install_id: str) -> Optional[dict]:
        """
        Get cached license information.

        Args:
            install_id: Installation UUID

        Returns:
            License info dict or None if not cached
        """
        cached = self.get(install_id, "info")

        if cached is not None:
            log_debug(f"License info cache HIT for install_id={install_id}", install_id=install_id)
            return cached

        log_debug(f"License info cache MISS for install_id={install_id}", install_id=install_id)
        return None

    def set_info(self, install_id: str, info: dict) -> None:
        """
        Cache license information for 8 hours.

        Args:
            install_id: Installation UUID
            info: License information dictionary
        """
        value = self._with_timestamps(info, "cached_at")
        self.set(install_id, "info", value, LICENSE_CACHE_TTL)
        log_info(f"Cached license info for install_id={install_id}", install_id=install_id, ttl_seconds=LICENSE_CACHE_TTL)

    def clear_all(self) -> None:
        """
        Clear all license cache data (use with caution!).

        This clears all keys in the 'license' namespace.
        """
        super().clear_all()


# Global license cache instance
_license_cache: Optional[LicenseCache] = None


def get_license_cache() -> LicenseCache:
    """
    Get or create the global license cache instance.

    Returns:
        LicenseCache singleton instance
    """
    global _license_cache

    if _license_cache is None:
        with _cache_lock:
            # Double-check pattern to avoid unnecessary locking
            if _license_cache is None:
                _license_cache = LicenseCache()

    assert _license_cache is not None
    return _license_cache
