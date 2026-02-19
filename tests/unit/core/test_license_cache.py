"""
Unit tests for license information cache.

Tests the LicenseCache wrapper that provides 8-hour caching for license
information to reduce API calls to journiv-plus license server.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.core.config import LICENSE_CACHE_TTL
from app.core.license_cache import LicenseCache, get_license_cache


class TestLicenseCacheKeys:
    """Test cache key generation."""

    def test_make_key_info(self):
        """Test info cache key format."""
        cache = LicenseCache(cache_backend=MagicMock())
        install_id = "550e8400-e29b-41d4-a716-446655440000"

        key = cache._make_key(install_id, "info")

        assert key == "license:info:550e8400-e29b-41d4-a716-446655440000"

    def test_make_key_different_install_ids(self):
        """Test that different install_ids produce different keys."""
        cache = LicenseCache(cache_backend=MagicMock())

        key1 = cache._make_key("install-1", "info")
        key2 = cache._make_key("install-2", "info")

        assert key1 != key2


class TestInfoCache:
    """Test license info caching."""

    def test_get_info_miss(self):
        """Test info cache miss returns None."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        cache = LicenseCache(cache_backend=mock_cache)
        result = cache.get_info("install-id")

        assert result is None

    def test_get_info_hit(self):
        """Test info cache hit returns data."""
        mock_cache = MagicMock()
        expected_info = {
            "has_license": True,
            "is_active": True,
            "registered_email": "user@example.com",
            "cached_at": datetime.now(timezone.utc).isoformat()
        }
        mock_cache.get.return_value = expected_info

        cache = LicenseCache(cache_backend=mock_cache)
        result = cache.get_info("install-id")

        assert result == expected_info

    def test_set_info(self):
        """Test caching license info."""
        mock_cache = MagicMock()
        cache = LicenseCache(cache_backend=mock_cache)

        info = {
            "has_license": True,
            "is_active": True,
            "registered_email": "user@example.com"
        }

        cache.set_info("install-id", info)

        call_args = mock_cache.set.call_args
        assert call_args[0][0] == "license:info:install-id"
        assert call_args[0][1]["has_license"] is True
        assert call_args[0][1]["is_active"] is True
        assert "cached_at" in call_args[0][1]
        assert call_args[1]["ex"] == LICENSE_CACHE_TTL


class TestCacheInvalidation:
    """Test cache invalidation."""

    def test_invalidate_clears_info_key(self):
        """Test that invalidate deletes info key."""
        mock_cache = MagicMock()
        cache = LicenseCache(cache_backend=mock_cache)

        cache.invalidate("install-id")

        # Should delete info key
        assert mock_cache.delete.call_count == 1
        calls = [call[0][0] for call in mock_cache.delete.call_args_list]
        assert "license:info:install-id" in calls

    def test_invalidate_different_install_ids(self):
        """Test that invalidate only affects specified install_id."""
        mock_cache = MagicMock()
        cache = LicenseCache(cache_backend=mock_cache)

        cache.invalidate("install-1")

        calls = [call[0][0] for call in mock_cache.delete.call_args_list]
        # Should only delete install-1 keys, not install-2
        assert all("install-1" in call for call in calls)
        assert all("install-2" not in call for call in calls)


class TestCacheTTL:
    """Test cache TTL configuration."""

    def test_info_ttl_8_hours(self):
        """Test that info cache TTL is 8 hours (28800 seconds)."""
        assert LICENSE_CACHE_TTL == 28800

    def test_set_info_uses_ttl(self):
        """Test that set_info uses correct TTL."""
        mock_cache = MagicMock()
        cache = LicenseCache(cache_backend=mock_cache)

        cache.set_info("install-id", {"has_license": True})

        call_args = mock_cache.set.call_args
        assert call_args[1]["ex"] == 28800  # 8 hours


class TestGlobalCacheInstance:
    """Test global cache instance management."""

    @pytest.fixture(autouse=True)
    def reset_global_cache(self, monkeypatch):
        """Reset global cache before each test and restore after."""
        import app.core.license_cache
        original_value = app.core.license_cache._license_cache
        monkeypatch.setattr(app.core.license_cache, "_license_cache", None)
        yield
        monkeypatch.setattr(app.core.license_cache, "_license_cache", original_value)

    def test_get_license_cache_creates_instance(self):
        """Test that get_license_cache returns a LicenseCache instance."""
        cache = get_license_cache()

        assert isinstance(cache, LicenseCache)

    def test_get_license_cache_singleton(self):
        """Test that get_license_cache returns same instance."""
        cache1 = get_license_cache()
        cache2 = get_license_cache()

        assert cache1 is cache2


class TestCacheIntegration:
    """Test full cache workflow."""

    def test_full_info_workflow(self):
        """Test complete info cache workflow."""
        mock_cache = MagicMock()
        cache = LicenseCache(cache_backend=mock_cache)

        # Initial miss
        mock_cache.get.return_value = None
        result = cache.get_info("install-id")
        assert result is None

        # Set info
        info = {"has_license": True, "tier": "supporter"}
        cache.set_info("install-id", info)

        # Simulate cache hit
        cached_data = {
            "has_license": True,
            "tier": "supporter",
            "cached_at": datetime.now(timezone.utc).isoformat()
        }
        mock_cache.get.return_value = cached_data
        result = cache.get_info("install-id")
        assert result is not None
        assert result["has_license"] is True
        assert result["tier"] == "supporter"

        # Invalidate
        cache.invalidate("install-id")
        mock_cache.delete.assert_called()

    def test_multiple_install_ids_isolated(self):
        """Test that multiple install IDs have isolated caches."""
        mock_cache = MagicMock()
        cache = LicenseCache(cache_backend=mock_cache)

        # Set different values for different install IDs
        cache.set_info("install-1", {"tier": "supporter"})
        cache.set_info("install-2", {"tier": "believer"})

        # Verify different keys were used
        calls = mock_cache.set.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "license:info:install-1"
        assert calls[1][0][0] == "license:info:install-2"
        assert calls[0][0][1]["tier"] == "supporter"
        assert calls[1][0][1]["tier"] == "believer"
