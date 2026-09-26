"""
Regression tests for the Immich picker asset cache being overwritten by a
single live page.

`list_assets` served pages from the cached `items` list when it was long
enough, but a live single-page fetch (cache miss, or a page beyond the
synced window) called `_save_to_cache`, which replaces the WHOLE cached
list with just that one page. Fetching page 1 live, then page 2 live, then
requesting page 1 again returned page 2's items: the picker showed
duplicate or wrong photos. Only `sync()` (a full page-1 batch up to the
cache limit) may write the cache now; live fetches never do.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.cache import InMemoryCache
from app.core.scoped_cache import ScopedCache
from app.integrations import immich
from app.models.integration import Integration, IntegrationProvider
from app.models.user import User


def _make_user_and_integration():
    user = User(id="00000000-0000-0000-0000-000000000001")
    integration = Integration(
        id="00000000-0000-0000-0000-000000000002",
        user_id=user.id,
        provider=IntegrationProvider.IMMICH,
        is_active=True,
        base_url="http://immich.test",
        access_token_encrypted="enc",
        external_user_id="immich-user-1",
    )
    return user, integration


def _assets(start: int, count: int) -> list[dict]:
    return [{"id": f"asset-{i}", "type": "IMAGE"} for i in range(start, start + count)]


def _fake_client(pages: dict[int, list[dict]]):
    """A fake httpx client whose search-metadata POST returns the page
    requested in the request body, like the real Immich search endpoint."""

    async def _post(url, headers=None, json=None):
        page = json["page"]
        items = pages.get(page, [])
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "assets": {"items": items, "total": sum(len(v) for v in pages.values()), "count": len(items)}
        }
        return response

    client = AsyncMock()
    client.post = AsyncMock(side_effect=_post)
    return client


@pytest.mark.asyncio
async def test_page1_then_page2_then_page1_returns_correct_items():
    user, integration = _make_user_and_integration()
    test_cache = ScopedCache(namespace="test_immich_picker", cache_backend=InMemoryCache())

    pages = {1: _assets(0, 100), 2: _assets(100, 100)}
    fake_client = _fake_client(pages)

    with patch("app.integrations.immich._get_client", return_value=fake_client), \
         patch("app.integrations.immich._get_cache", return_value=test_cache), \
         patch("app.integrations.immich.decrypt_token", return_value="fake-key"):
        page1_first = await immich.list_assets(MagicMock(), user, integration, page=1, limit=100)
        page2 = await immich.list_assets(MagicMock(), user, integration, page=2, limit=100)
        page1_second = await immich.list_assets(MagicMock(), user, integration, page=1, limit=100)

    assert [a.id for a in page1_first] == [f"asset-{i}" for i in range(0, 100)]
    assert [a.id for a in page2] == [f"asset-{i}" for i in range(100, 200)]
    # The bug: this used to come back as page 2's items because the live
    # fetch for page 2 had overwritten the whole cache.
    assert [a.id for a in page1_second] == [f"asset-{i}" for i in range(0, 100)]


@pytest.mark.asyncio
async def test_live_fetch_does_not_shrink_a_synced_cache():
    user, integration = _make_user_and_integration()
    test_cache = ScopedCache(namespace="test_immich_picker", cache_backend=InMemoryCache())

    # sync() already populated a 250-item cache.
    synced_items = _assets(0, 250)
    test_cache.set(scope_id=str(user.id), cache_type="assets", value={"items": synced_items}, ttl_seconds=3600)

    # A live fetch beyond the synced window (page 5, size 50 -> items 200-249
    # are cached but requesting an out-of-range page forces a live call).
    pages = {10: _assets(500, 50)}
    fake_client = _fake_client(pages)

    with patch("app.integrations.immich._get_client", return_value=fake_client), \
         patch("app.integrations.immich._get_cache", return_value=test_cache), \
         patch("app.integrations.immich.decrypt_token", return_value="fake-key"):
        await immich.list_assets(MagicMock(), user, integration, page=10, limit=50, force_refresh=True)

    cached = test_cache.get(scope_id=str(user.id), cache_type="assets")
    assert cached is not None
    assert len(cached["items"]) == 250
    assert cached["items"] == synced_items
