"""
Immich integration provider.

This module implements the Immich-specific logic for connecting, listing assets,
and syncing photo/video metadata.

API Documentation: https://api.immich.app/introduction
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from inspect import isawaitable
from pathlib import Path
from typing import Any, Optional, Protocol, Union
from urllib.parse import urlencode
from uuid import UUID

import aiofiles
import aiohttp
from immichpy import AsyncClient
from immichpy.client.generated import (
    AssetMediaSize,
    AssetOrder,
    BulkIdsDto,
    CreateAlbumDto,
    MetadataSearchDto,
)
from immichpy.client.generated.exceptions import (
    ApiException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from sqlmodel import Session
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.encryption import decrypt_token
from app.core.logging_config import log_error, log_info, log_warning
from app.core.media_signing import build_signed_query
from app.core.scoped_cache import ScopedCache
from app.core.time_utils import utc_now
from app.integrations.schemas import IntegrationAssetResponse
from app.models.integration import AssetType, Integration, IntegrationProvider
from app.models.user import User

# Immich URL templates for the media proxy (these build URLs only; they do not
# issue HTTP requests, so they are not routed through the immichpy client).
IMMICH_API_ASSET_THUMBNAIL = "/api/assets/{asset_id}/thumbnail"
IMMICH_API_PERSON_THUMBNAIL = "/api/people/{person_id}/thumbnail"

# Immich caps metadata search / people pagination at 1000 items per page.
IMMICH_MAX_PAGE_SIZE = 1000
IMMICH_SEARCH_PEOPLE_WARNING_THRESHOLD = 1000

_session: Optional[aiohttp.ClientSession] = None


def _get_session() -> aiohttp.ClientSession:
    """Reuse a single aiohttp session to avoid connection churn across requests."""
    global _session
    if _session is None or _session.closed:
        timeout = aiohttp.ClientTimeout(connect=5.0, sock_read=60.0, total=120.0)
        _session = aiohttp.ClientSession(timeout=timeout)
    return _session


def _client(base_url: str, api_key: str) -> AsyncClient:
    """Build an immichpy client bound to a server + key over the shared session.

    The session is injected, so the returned client never owns (or closes) it;
    the shared session is reused for connection pooling.
    """
    return AsyncClient(api_key=api_key, base_url=base_url, http_client=_get_session())


class _JsonSerializable(Protocol):
    """Structural type for immichpy DTOs, which expose a generated ``to_json``."""

    def to_json(self) -> str: ...


def _dump(model: _JsonSerializable) -> dict[str, Any]:
    """Reproduce the raw Immich JSON payload from an immichpy DTO.

    ``to_json()`` emits camelCase aliases with ISO datetime strings and enum
    values, i.e. the exact wire shape the previous httpx code returned. This
    keeps every caller of this module unchanged.
    """
    return json.loads(model.to_json())


async def connect(
    session: Session | AsyncSession,
    user: User,
    base_url: str,
    credentials: dict[str, Any],
) -> str:
    """
    Connect to Immich and validate the user's API key.

    Steps:
        1. Extract api_key from credentials
        2. Call GET /api/users/me with x-api-key header
        3. Validate response and extract user ID
        4. Return external_user_id for storage
    """
    api_key = credentials.get("api_key")
    if not api_key:
        raise ValueError("Missing required credential: api_key")

    if not base_url.startswith(("http://", "https://")):
        raise ValueError("Base URL must start with http:// or https://")

    # Validate API key by calling Immich's /api/users/me endpoint
    try:
        me = await _client(base_url, api_key).users.get_my_user()

        # Extract user ID from response
        external_user_id = str(me.id) if me and me.id else None
        if not external_user_id:
            raise ValueError("Immich API response missing 'id' field")

        log_info(
            f"Successfully connected to Immich for user {user.id}, "
            f"external_user_id: {external_user_id}"
        )

        return external_user_id

    except (UnauthorizedException, ForbiddenException) as e:
        log_warning(e, f"Invalid Immich API key for user {user.id}: {e}")
        raise ValueError(
            "Invalid Immich API key. Please check your key and try again."
        ) from None

    except ApiException as e:
        log_error(e, message=f"Immich API error for user {user.id}: {e}")
        raise ValueError(f"Immich API error: {e.status}") from None

    except asyncio.TimeoutError as e:
        log_error(e, message=f"Timeout connecting to Immich at {base_url}")
        raise ValueError(
            "Connection to Immich timed out. Please check the URL and try again."
        ) from None

    except aiohttp.ClientError as e:
        log_error(e, message=f"Failed to connect to Immich at {base_url}: {e}")
        raise ValueError(
            f"Could not connect to Immich server at {base_url}. Please check the URL."
        ) from None


async def list_assets(
    session: Session | AsyncSession,
    user: User,
    integration: Integration,
    page: int = 1,
    limit: int = 50,
    force_refresh: bool = False,
) -> list[IntegrationAssetResponse]:
    """
    list Immich assets (photos/videos) for the user.

    Strategy:
        - If force_refresh=True: fetch live from Immich
        - Otherwise: return cached data from ImmichAsset table
        - If cache is empty: fetch live and populate cache
    """
    if not integration.is_active:
        raise ValueError(f"Integration {integration.id} is not active")

    # If not forcing refresh, try cache first
    if not force_refresh:
        cache = _get_cache()
        cached_data = cache.get(scope_id=str(user.id), cache_type="assets")
        if cached_data:
            assets_data = cached_data.get("items", [])
            start = (page - 1) * limit
            end = start + limit
            if len(assets_data) >= end:
                log_info(
                    f"Returning cached Immich assets for user {user.id} (page {page}, limit {limit})"
                )
                return [
                    _normalize_immich_asset(asset, integration.provider, str(user.id))
                    for asset in assets_data[start:end]
                ]

    # Fetch live from Immich using search metadata endpoint
    log_info(
        f"Fetching live Immich assets for user {user.id} (page {page}, limit {limit})"
    )

    api_key = decrypt_token(integration.access_token_encrypted)

    try:
        search_response = await _client(
            integration.base_url, api_key
        ).search.search_assets(
            MetadataSearchDto(
                page=page,
                size=min(limit, IMMICH_MAX_PAGE_SIZE),
                order=AssetOrder.DESC,
            )
        )

        # Extract assets from search response
        assets_result = search_response.assets
        items = assets_result.items if assets_result else []
        assets_data = [_dump(item) for item in items]
        total = assets_result.total if assets_result else len(assets_data)
        count = assets_result.count if assets_result else len(assets_data)

        log_info(f"Immich search returned {count} assets (total: {total})")

        # Normalize and optionally cache
        normalized_assets = []
        for asset_data in assets_data:
            normalized = _normalize_immich_asset(
                asset_data, integration.provider, str(user.id)
            )
            normalized_assets.append(normalized)

        # Cache the asset metadata if present
        if assets_data:
            _save_to_cache(str(user.id), assets_data)

        log_info(
            f"Fetched {len(normalized_assets)} live Immich assets for user {user.id}"
        )
        return normalized_assets

    except (UnauthorizedException, ForbiddenException) as e:
        log_warning(e, f"Invalid Immich API key for user {user.id}: {e}")
        raise ValueError(
            "Immich API key is no longer valid. Please reconnect."
        ) from None

    except Exception as e:
        log_error(e, message=f"Failed to fetch Immich assets for user {user.id}: {e}")
        raise


async def sync(
    session: Session | AsyncSession, user: User, integration: Integration
) -> None:
    """
    Background sync task to cache Immich asset metadata.

    This function runs periodically (e.g., every 6 hours) to keep the local
    cache up to date with the user's Immich library.

    Strategy:
        1. Fetch recent assets from Immich (up to INTEGRATION_CACHE_LIMIT)
        2. Store in ScopedCache
        3. Prune old entries from ScopedCache according to INTEGRATION_CACHE_LIMIT
        4. Update integration.last_synced_at on success
        5. Update integration.last_error on failure
    """
    if not integration.is_active:
        log_info(f"Skipping sync for inactive integration {integration.id}")
        return

    log_info(f"Starting Immich sync for user {user.id}, integration {integration.id}")

    try:
        api_key = decrypt_token(integration.access_token_encrypted)
        cache_limit = settings.integration_cache_limit

        # Fetch recent assets from Immich using search metadata endpoint
        search_response = await _client(
            integration.base_url, api_key
        ).search.search_assets(
            MetadataSearchDto(
                page=1,
                size=min(cache_limit, IMMICH_MAX_PAGE_SIZE),
                order=AssetOrder.DESC,
            )
        )

        # Extract assets from search response
        assets_result = search_response.assets
        items = assets_result.items if assets_result else []
        assets_data = [_dump(item) for item in items]
        log_info(f"Fetched {len(assets_data)} assets from Immich for sync")

        # Save to cache
        if assets_data:
            _save_to_cache(str(user.id), assets_data)

        # Update sync timestamp
        integration.last_synced_at = utc_now()
        integration.last_error = None
        integration.last_error_at = None
        session.add(integration)
        await _commit_session(session)

        log_info(
            f"Successfully synced Immich for user {user.id}, cached {len(assets_data)} assets"
        )

    except Exception as e:
        log_error(e, message=f"Failed to sync Immich for user {user.id}: {e}")
        # Update error tracking
        integration.last_error = str(e)[:500]  # Truncate to avoid DB errors
        integration.last_error_at = utc_now()
        session.add(integration)
        await _commit_session(session)
        raise


async def ensure_album_exists(
    base_url: str, api_key: str, album_name: str = "Journiv"
) -> Optional[str]:
    """
    Ensure an album with the given name exists.

    Returns:
        str: The album ID, or None if creation failed.
    """
    # Check if album exists
    album_id = await get_album_id_by_name(base_url, api_key, album_name)
    if album_id:
        log_info(f"Found existing Immich album '{album_name}': {album_id}")
        return album_id

    # Create if not exists
    log_info(f"Creating Immich album '{album_name}'")
    try:
        album_id = await create_album(base_url, api_key, album_name)
        log_info(f"Created Immich album '{album_name}': {album_id}")
        return album_id
    except ValueError as e:
        log_error(e, message=f"Failed to create Immich album '{album_name}': {e}")
        # If creation fails mainly due to concurrency (created just now), try finding it again
        return await get_album_id_by_name(base_url, api_key, album_name)


async def get_album_id_by_name(
    base_url: str, api_key: str, album_name: str
) -> Optional[str]:
    """Find an album ID by name."""
    try:
        albums = await _client(base_url, api_key).albums.get_all_albums()

        # Find album with matching name
        for album in albums:
            if album.album_name == album_name:
                return str(album.id)

        return None
    except Exception as e:
        log_warning(e, f"Failed to list Immich albums: {e}")
        return None


async def create_album(base_url: str, api_key: str, album_name: str) -> str:
    """Create a new album with description."""
    try:
        album = await _client(base_url, api_key).albums.create_album(
            CreateAlbumDto(
                albumName=album_name,
                description="Photos and Videos linked to Journiv journal entries",
            )
        )
        return str(album.id)
    except Exception as e:
        log_error(e, message=f"Failed to create album: {e}")
        raise ValueError(f"Failed to create album: {e}") from None


async def add_assets_to_album(
    base_url: str, api_key: str, album_id: str, asset_ids: list[str]
) -> None:
    """Add assets to an album."""
    if not asset_ids:
        return

    try:
        await _client(base_url, api_key).albums.add_assets_to_album(
            UUID(album_id),
            BulkIdsDto(ids=[UUID(asset_id) for asset_id in asset_ids]),
        )
        log_info(f"Added {len(asset_ids)} assets to Immich album {album_id}")

    except Exception as e:
        log_error(e, message=f"Failed to add assets to Immich album {album_id}: {e}")
        raise


async def remove_assets_from_album(
    base_url: str, api_key: str, album_id: str, asset_ids: list[str]
) -> None:
    """Remove assets from an album."""
    if not asset_ids:
        return

    try:
        await _client(base_url, api_key).albums.remove_asset_from_album(
            UUID(album_id),
            BulkIdsDto(ids=[UUID(asset_id) for asset_id in asset_ids]),
        )
        log_info(f"Removed {len(asset_ids)} assets from Immich album {album_id}")

    except Exception as e:
        log_error(
            e, message=f"Failed to remove assets from Immich album {album_id}: {e}"
        )
        raise


async def _commit_session(session: Session | AsyncSession) -> None:
    result = session.commit()
    if isawaitable(result):
        await result


# Cache instance
_cache: Optional[ScopedCache] = None


def _get_cache() -> ScopedCache:
    """Get or create the cache instance."""
    global _cache
    if _cache is None:
        _cache = ScopedCache(namespace="integrations:immich")
    return _cache


def _save_to_cache(user_id: str, assets_data: list[dict[str, Any]]) -> None:
    """
    Save assets to ScopedCache.
    """
    try:
        cache = _get_cache()
        # Ensure we only cache up to the limit
        limit = settings.integration_cache_limit
        cache_data = {"items": assets_data[:limit]}

        cache.set(
            scope_id=user_id,
            cache_type="assets",
            value=cache_data,
            ttl_seconds=settings.integration_sync_interval_hours
            * 3600
            * 2,  # TTL = 2 sync cycles
        )
    except Exception as e:
        log_warning(e, f"Failed to save Immich assets to cache for user {user_id}: {e}")


def _normalize_immich_asset(
    asset_data: dict[str, Any],
    provider: Union[IntegrationProvider, str],
    user_id: str,
) -> IntegrationAssetResponse:
    """
    Convert Immich API asset data to normalized IntegrationAssetResponse.

    Modern Immich search response structure:
    {
        "id": "d4bb1e5a-...",
        "type": "IMAGE" | "VIDEO",
        "createdAt": "2025-01-07T09:31:21.821Z",
        "exifInfo": {
            "dateTimeOriginal": "2025-01-07T09:31:21.000Z"
        },
        "originalFileName": "IMG_1234.jpg"  (may not be present in search response)
    }
    """
    asset_id = asset_data.get("id", "unknown")
    asset_type = _map_asset_type(asset_data.get("type", "OTHER"))

    # Title: prefer originalFileName, fall back to ID
    title = (
        asset_data.get("originalFileName")
        or asset_data.get("originalPath")
        or f"Asset {asset_id[:8]}"
    )

    # taken_at: prefer localDateTime (user requested for timeline grouping),
    # then exifInfo.dateTimeOriginal, fall back to createdAt
    exif_info = asset_data.get("exifInfo", {})
    taken_at_str = (
        asset_data.get("localDateTime")
        or exif_info.get("dateTimeOriginal")
        or asset_data.get("createdAt")
    )

    # Parse taken_at datetime
    taken_at = None
    if taken_at_str:
        try:
            # Handle Z suffix if present, though localDateTime might not have it
            clean_str = taken_at_str.replace("Z", "+00:00")
            taken_at = datetime.fromisoformat(clean_str)
            if taken_at.tzinfo is None:
                taken_at = taken_at.replace(tzinfo=timezone.utc)
            else:
                taken_at = taken_at.astimezone(timezone.utc)
        except (ValueError, AttributeError) as e:
            log_warning(
                e, f"Failed to parse taken_at for asset {asset_id}: {taken_at_str}"
            )

    thumb_url = _build_signed_proxy_url(
        provider=provider,
        asset_id=asset_id,
        user_id=user_id,
        variant="thumbnail",
        ttl_seconds=settings.media_thumbnail_signed_url_ttl_seconds,
    )
    # Use video-specific TTL if asset is a video
    original_ttl = (
        settings.media_signed_url_video_ttl_seconds
        if asset_type == AssetType.VIDEO
        else settings.media_signed_url_ttl_seconds
    )

    original_url = _build_signed_proxy_url(
        provider=provider,
        asset_id=asset_id,
        user_id=user_id,
        variant="original",
        ttl_seconds=original_ttl,
    )

    return IntegrationAssetResponse(
        id=asset_id,
        type=asset_type,
        title=title,
        taken_at=taken_at,
        thumb_url=thumb_url,
        original_url=original_url,
    )


async def get_asset_info(base_url: str, api_key: str, asset_id: str) -> dict[str, Any]:
    """
    Fetch details for a single asset from Immich.
    Falls back to search endpoint if direct lookup fails (e.g. 404).
    """
    client = _client(base_url, api_key)

    try:
        # 1. Try direct endpoint
        try:
            asset = await client.assets.get_asset_info(UUID(asset_id))
            return _dump(asset)
        except NotFoundException:
            # 2. Fallback to search endpoint
            # Some versions of Immich or some asset states might require search lookup
            search_response = await client.search.search_assets(
                MetadataSearchDto(id=UUID(asset_id))
            )
            items = search_response.assets.items if search_response.assets else []
            if items:
                return _dump(items[0])

    except Exception as e:
        log_warning(e, f"Failed to fetch Immich asset info for {asset_id}")

    return {}


async def list_people(
    base_url: str,
    api_key: str,
    *,
    page: int = 1,
    limit: int = 100,
    search: Optional[str] = None,
    include_hidden: bool = False,
) -> tuple[list[dict[str, Any]], int, bool]:
    """
    Fetch people from Immich.

    Immich supports paginated people listing. Its person search endpoint returns
    a full list on current releases, so search pagination is applied locally.
    """
    client = _client(base_url, api_key)
    limit = max(1, min(limit, IMMICH_MAX_PAGE_SIZE))
    page = max(1, page)

    if search and search.strip():
        results = await client.search.search_person(
            name=search.strip(), with_hidden=include_hidden
        )
        people = [_dump(person) for person in (results or [])]
        if len(people) > IMMICH_SEARCH_PEOPLE_WARNING_THRESHOLD:
            log_warning(
                "Immich people search returned "
                f"{len(people)} results without server-side pagination support"
            )
        start = (page - 1) * limit
        page_items = people[start : start + limit]
        return page_items, len(people), start + limit < len(people)

    response = await client.people.get_all_people(
        page=page, size=limit, with_hidden=include_hidden
    )
    people = [_dump(person) for person in (response.people or [])]
    total = int(response.total or len(people))
    has_more = (
        bool(response.has_next_page)
        if response.has_next_page is not None
        else page * limit < total
    )
    return people, total, has_more


async def get_person(
    base_url: str,
    api_key: str,
    person_id: str,
) -> dict[str, Any]:
    """Fetch a single Immich person."""
    person = await _client(base_url, api_key).people.get_person(UUID(person_id))
    return _dump(person) if person else {}


async def get_asset_faces(
    base_url: str,
    api_key: str,
    asset_id: str,
) -> list[dict[str, Any]]:
    """Fetch face detections for a single Immich asset."""
    faces = await _client(base_url, api_key).faces.get_faces(UUID(asset_id))
    return [_dump(face) for face in (faces or [])]


def get_person_thumbnail_url(base_url: str, person_id: str) -> str:
    """Build Immich person thumbnail URL."""
    return f"{base_url}{IMMICH_API_PERSON_THUMBNAIL.format(person_id=person_id)}"


async def get_person_thumbnail_bytes(
    base_url: str,
    api_key: str,
    person_id: str,
    *,
    max_bytes: int = 10 * 1024 * 1024,
) -> bytes:
    """Fetch an Immich person thumbnail for storage in Journiv."""
    content = await _client(base_url, api_key).people.get_person_thumbnail(
        UUID(person_id)
    )
    if len(content) > max_bytes:
        raise ValueError("Immich person thumbnail exceeds maximum profile image size")
    return bytes(content)


async def _raise_for_status(resp: aiohttp.ClientResponse) -> None:
    """Raise the same typed exception immichpy would for a non-2xx response."""
    if 200 <= resp.status <= 299:
        return
    body = (await resp.read()).decode("utf-8", "replace")
    raise ApiException.from_response(http_resp=resp, body=body, data=None)


async def download_original_to_file(
    base_url: str,
    api_key: str,
    asset_id: str,
    dest_path: Path,
) -> None:
    """Stream an asset's original file to ``dest_path``."""
    resp = await _client(
        base_url, api_key
    ).assets.download_asset_without_preload_content(UUID(asset_id))
    async with resp:
        await _raise_for_status(resp)
        async with aiofiles.open(dest_path, "wb") as f:
            async for chunk in resp.content.iter_chunked(1024 * 1024):
                await f.write(chunk)


async def download_media_bytes(
    base_url: str,
    api_key: str,
    asset_id: str,
    size: AssetMediaSize,
) -> bytes:
    """Download an asset's thumbnail/preview and return its bytes in memory."""
    resp = await _client(base_url, api_key).assets.view_asset_without_preload_content(
        UUID(asset_id), size=size
    )
    async with resp:
        await _raise_for_status(resp)
        return await resp.read()


def get_cached_asset_type(user_id: str, asset_id: str) -> Optional[AssetType]:
    """
    Try to find asset type in local integration cache.
    """
    try:
        cache = _get_cache()
        cached_data = cache.get(scope_id=user_id, cache_type="assets")
        if cached_data and "items" in cached_data:
            for item in cached_data["items"]:
                if item.get("id") == asset_id:
                    return _map_asset_type(item.get("type", "OTHER"))
    except Exception:
        pass
    return None


def get_asset_url(
    base_url: str,
    asset_id: str,
    variant: str,
    asset_type: AssetType = AssetType.IMAGE,
) -> str:
    """
    Get the Immich URL for a given asset and variant.

    For variant='original', uses the provided asset_type to determine
    if it's a video playback URL or image thumbnail.
    """
    if variant == "thumbnail":
        return f"{base_url}{IMMICH_API_ASSET_THUMBNAIL.format(asset_id=asset_id)}"

    if variant == "original":
        if asset_type == AssetType.VIDEO:
            return f"{base_url}/api/assets/{asset_id}/video/playback"
        else:
            # Default to image (preview)
            # Use thumbnail?size=preview to get JPEG/WebP (avoids HEIC issues)
            return f"{base_url}/api/assets/{asset_id}/thumbnail?size=preview"

    raise ValueError(f"Unknown variant {variant}")


def _build_signed_proxy_url(
    provider: Union[IntegrationProvider, str],
    asset_id: str,
    user_id: str,
    variant: str,
    ttl_seconds: int,
) -> str:
    # Handle both enum and string types for provider
    provider_value = (
        provider.value if isinstance(provider, IntegrationProvider) else provider
    )
    expires_at = int(time.time()) + ttl_seconds
    query = build_signed_query(
        provider_value, variant, asset_id, str(user_id), expires_at
    )
    return (
        f"/api/v1/integrations/{provider_value}/proxy/{asset_id}/{variant}"
        f"?{urlencode(query)}"
    )


def _map_asset_type(immich_type: str) -> AssetType:
    """
    Map Immich asset type to AssetType enum.

    Immich types: IMAGE, VIDEO
    """
    type_map = {
        "IMAGE": AssetType.IMAGE,
        "VIDEO": AssetType.VIDEO,
    }
    return type_map.get(immich_type, AssetType.OTHER)
