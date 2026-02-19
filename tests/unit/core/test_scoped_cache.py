"""
Unit tests for ScopedCache base class.

Tests cache key generation, validation, and basic cache operations.
"""
from unittest.mock import MagicMock

import pytest

from app.core.scoped_cache import ScopedCache


class TestScopedCacheKeyGeneration:
    """Test cache key generation and validation."""

    def test_make_key_basic(self):
        """Test basic key generation."""
        cache = ScopedCache("test_namespace", cache_backend=MagicMock())

        key = cache._make_key("scope-123", "validation")

        assert key == "test_namespace:validation:scope-123"

    def test_make_key_different_scopes(self):
        """Test that different scope_ids produce different keys."""
        cache = ScopedCache("test_namespace", cache_backend=MagicMock())

        key1 = cache._make_key("scope-1", "validation")
        key2 = cache._make_key("scope-2", "validation")

        assert key1 != key2
        assert key1 == "test_namespace:validation:scope-1"
        assert key2 == "test_namespace:validation:scope-2"

    def test_make_key_different_cache_types(self):
        """Test that different cache_types produce different keys."""
        cache = ScopedCache("test_namespace", cache_backend=MagicMock())

        key1 = cache._make_key("scope-123", "validation")
        key2 = cache._make_key("scope-123", "info")

        assert key1 != key2
        assert key1 == "test_namespace:validation:scope-123"
        assert key2 == "test_namespace:info:scope-123"

    def test_make_key_rejects_colon_in_cache_type(self):
        """Test that cache_type with colon raises ValueError."""
        cache = ScopedCache("test_namespace", cache_backend=MagicMock())

        with pytest.raises(ValueError, match="cache_type must not contain ':'"):
            cache._make_key("scope-123", "validation:extra")

    def test_make_key_rejects_colon_in_scope_id(self):
        """Test that scope_id with colon raises ValueError."""
        cache = ScopedCache("test_namespace", cache_backend=MagicMock())

        with pytest.raises(ValueError, match="scope_id must not contain ':'"):
            cache._make_key("scope:123", "validation")

    def test_make_key_rejects_colon_in_both(self):
        """Test that both parameters with colons raise ValueError (cache_type first)."""
        cache = ScopedCache("test_namespace", cache_backend=MagicMock())

        with pytest.raises(ValueError, match="cache_type must not contain ':'"):
            cache._make_key("scope:123", "validation:extra")

    def test_make_key_allows_other_special_chars(self):
        """Test that other special characters are allowed."""
        cache = ScopedCache("test_namespace", cache_backend=MagicMock())

        key = cache._make_key("scope-123_abc", "validation-type")

        assert key == "test_namespace:validation-type:scope-123_abc"


class TestScopedCacheOperations:
    """Test basic cache operations."""

    def test_get(self):
        """Test get operation."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = {"data": "test"}
        cache = ScopedCache("test_namespace", cache_backend=mock_cache)

        result = cache.get("scope-123", "validation")

        assert result == {"data": "test"}
        mock_cache.get.assert_called_once_with("test_namespace:validation:scope-123")

    def test_set(self):
        """Test set operation."""
        mock_cache = MagicMock()
        cache = ScopedCache("test_namespace", cache_backend=mock_cache)

        cache.set("scope-123", "validation", {"data": "test"}, ttl_seconds=3600)

        mock_cache.set.assert_called_once_with("test_namespace:validation:scope-123", {"data": "test"}, ex=3600)

    def test_delete(self):
        """Test delete operation."""
        mock_cache = MagicMock()
        cache = ScopedCache("test_namespace", cache_backend=mock_cache)

        cache.delete("scope-123", "validation")

        mock_cache.delete.assert_called_once_with("test_namespace:validation:scope-123")

    def test_invalidate(self):
        """Test invalidate operation."""
        mock_cache = MagicMock()
        cache = ScopedCache("test_namespace", cache_backend=mock_cache)

        cache.invalidate("scope-123", ["validation", "info"])

        assert mock_cache.delete.call_count == 2
        mock_cache.delete.assert_any_call("test_namespace:validation:scope-123")
        mock_cache.delete.assert_any_call("test_namespace:info:scope-123")




