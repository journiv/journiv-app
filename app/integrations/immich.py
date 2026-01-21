"""
Immich integration provider.

This module implements the Immich-specific logic for connecting, listing assets,
and syncing photo/video metadata.

API Documentation: https://api.immich.app/introduction
"""
from datetime import datetime, timezone
import time
from urllib.parse import urlencode
from inspect import isawaitable
from typing import Dict, Any, List, Optional, Union

import httpx
from sqlmodel import Session
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.media_signing import build_signed_query
from app.core.encryption import decrypt_token
from app.core.time_utils import utc_now
from app.core.logging_config import log_info, log_error, log_warning
from app.core.scoped_cache import ScopedCache
from app.models.integration import Integration, IntegrationProvider, AssetType
from app.integrations.schemas import IntegrationAssetResponse
from app.models.user import User

# Immich API endpoints
IMMICH_API_USER_ME = "/api/users/me"
IMMICH_API_SEARCH_METADATA = "/api/search/metadata"  # Search assets with pagination
IMMICH_API_ASSET_THUMBNAIL = "/api/assets/{asset_id}/thumbnail"
IMMICH_API_ALBUMS = "/api/albums"
IMMICH_API_ALBUM_ASSETS = "/api/albums/{album_id}/assets"

_client: Optional[httpx.AsyncClient] = None

def _get_client() -> httpx.AsyncClient:
    """Reuse a single client to avoid connection churn."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            verify=True,
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            transport=httpx.AsyncHTTPTransport(retries=2),
        )
    return _client


async def connect(
    session: Session | AsyncSession,
    user: User,
    base_url: str,
    credentials: Dict[str, Any]
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


    # Validate API key by calling Immich's /api/user/me endpoint
    try:
        client = _get_client()
        response = await client.get(
            f"{base_url}{IMMICH_API_USER_ME}",
            headers={"x-api-key": api_key},
        )

        response.raise_for_status()

        user_data = response.json()

        # Extract user ID from response
        external_user_id = user_data.get("id")
        if not external_user_id:
            raise ValueError("Immich API response missing 'id' field")

        log_info(
            f"Successfully connected to Immich for user {user.id}, "
            f"external_user_id: {external_user_id}"
        )

        return str(external_user_id)

    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            log_warning(e, f"Invalid Immich API key for user {user.id}: {e}")
            raise ValueError(
                "Invalid Immich API key. Please check your key and try again."
            )
        else:
            log_error(e, message=f"Immich API error for user {user.id}: {e}")
            raise ValueError(f"Immich API error: {e.response.status_code}")

    except httpx.TimeoutException as e:
        log_error(e, message=f"Timeout connecting to Immich at {base_url}")
        raise ValueError("Connection to Immich timed out. Please check the URL and try again.")

    except httpx.RequestError as e:
        log_error(e, message=f"Failed to connect to Immich at {base_url}: {e}")
        raise ValueError(f"Could not connect to Immich server at {base_url}. Please check the URL.")


async def list_assets(
    session: Session | AsyncSession,
    user: User,
    integration: Integration,
    page: int = 1,
    limit: int = 50,
    force_refresh: bool = False
) -> list[IntegrationAssetResponse]:
    """
    List Immich assets (photos/videos) for the user.

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
                log_info(f"Returning cached Immich assets for user {user.id} (page {page}, limit {limit})")
                return [
                    _normalize_immich_asset(asset, integration.provider, str(user.id))
                    for asset in assets_data[start:end]
                ]

    # Fetch live from Immich using search metadata endpoint
    log_info(f"Fetching live Immich assets for user {user.id} (page {page}, limit {limit})")

    api_key = decrypt_token(integration.access_token_encrypted)

    try:
        client = _get_client()
        response = await client.post(
            f"{integration.base_url}{IMMICH_API_SEARCH_METADATA}",
            headers={
                "x-api-key": api_key,
                "Content-Type": "application/json"
            },
            json={
                "page": page,
                "size": limit,
                "order": "desc",
            },
        )
        response.raise_for_status()
        search_response = response.json()

        # Extract assets from search response
        assets_result = search_response.get("assets", {})
        assets_data = assets_result.get("items", [])
        total = assets_result.get("total", len(assets_data))
        count = assets_result.get("count", len(assets_data))

        log_info(f"Immich search returned {count} assets (total: {total})")

        # Normalize and optionally cache
        normalized_assets = []
        for asset_data in assets_data:
            normalized = _normalize_immich_asset(asset_data, integration.provider, str(user.id))
            normalized_assets.append(normalized)

        # Cache the asset metadata if present
        if assets_data:
            _save_to_cache(str(user.id), assets_data)

        log_info(f"Fetched {len(normalized_assets)} live Immich assets for user {user.id}")
        return normalized_assets

    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            log_warning(e, f"Invalid Immich API key for user {user.id}: {e}")
            raise ValueError("Immich API key is no longer valid. Please reconnect.")
        else:
            log_error(e, message=f"Immich API error for user {user.id}: {e}")
            raise

    except Exception as e:
        log_error(e, message=f"Failed to fetch Immich assets for user {user.id}: {e}")
        raise


async def sync(
    session: Session | AsyncSession,
    user: User,
    integration: Integration
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
        client = _get_client()
        response = await client.post(
            f"{integration.base_url}{IMMICH_API_SEARCH_METADATA}",
            headers={
                "x-api-key": api_key,
                "Content-Type": "application/json"
            },
            json={
                "page": 1,
                "size": cache_limit,
                "order": "desc",
            },
        )
        response.raise_for_status()
        search_response = response.json()

        # Extract assets from search response
        assets_result = search_response.get("assets", {})
        assets_data = assets_result.get("items", [])
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

        log_info(f"Successfully synced Immich for user {user.id}, cached {len(assets_data)} assets")

    except Exception as e:
        log_error(e, message=f"Failed to sync Immich for user {user.id}: {e}")
        # Update error tracking
        integration.last_error = str(e)[:500]  # Truncate to avoid DB errors
        integration.last_error_at = utc_now()
        session.add(integration)
        await _commit_session(session)
        raise


async def ensure_album_exists(
    base_url: str,
    api_key: str,
    album_name: str = "Journiv"
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
    base_url: str,
    api_key: str,
    album_name: str
) -> Optional[str]:
    """Find an album ID by name."""
    try:
        async with httpx.AsyncClient(verify=True) as client:
            response = await client.get(
                f"{base_url}{IMMICH_API_ALBUMS}",
                headers={"x-api-key": api_key},
                timeout=30.0
            )
            response.raise_for_status()
            albums = response.json()

            # Find album with matching name
            for album in albums:
                if album.get("albumName") == album_name:
                    return album.get("id")

            return None
    except Exception as e:
        log_warning(e, f"Failed to list Immich albums: {e}")
        return None


async def create_album(
    base_url: str,
    api_key: str,
    album_name: str
) -> str:
    """Create a new album with description."""
    try:
        async with httpx.AsyncClient(verify=True) as client:
            response = await client.post(
                f"{base_url}{IMMICH_API_ALBUMS}",
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "albumName": album_name,
                    "description": "Photos and Videos linked to Journiv journal entries"
                },
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("id")
    except Exception as e:
        log_error(e, message=f"Failed to create album: {e}")
        raise ValueError(f"Failed to create album: {e}")


async def add_assets_to_album(
    base_url: str,
    api_key: str,
    album_id: str,
    asset_ids: List[str]
) -> None:
    """Add assets to an album."""
    if not asset_ids:
        return

    try:
        url = f"{base_url}{IMMICH_API_ALBUM_ASSETS.format(album_id=album_id)}"
        async with httpx.AsyncClient(verify=True) as client:
            response = await client.put(
                url,
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json"
                },
                json={"ids": asset_ids},
                timeout=30.0
            )
            response.raise_for_status()
            log_info(f"Added {len(asset_ids)} assets to Immich album {album_id}")

    except Exception as e:
        log_error(e, message=f"Failed to add assets to Immich album {album_id}: {e}")
        raise


async def remove_assets_from_album(
    base_url: str,
    api_key: str,
    album_id: str,
    asset_ids: List[str]
) -> None:
    """Remove assets from an album."""
    if not asset_ids:
        return

    try:
        url = f"{base_url}{IMMICH_API_ALBUM_ASSETS.format(album_id=album_id)}"

        async with httpx.AsyncClient(verify=True) as client:
            response = await client.request(
                "DELETE",
                url,
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json"
                },
                json={"ids": asset_ids},
                timeout=30.0
            )
            response.raise_for_status()
            log_info(f"Removed {len(asset_ids)} assets from Immich album {album_id}")

    except Exception as e:
        log_error(e, message=f"Failed to remove assets from Immich album {album_id}: {e}")
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


def _save_to_cache(user_id: str, assets_data: List[Dict[str, Any]]) -> None:
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
            ttl_seconds=settings.integration_sync_interval_hours * 3600 * 2  # TTL = 2 sync cycles
        )
    except Exception as e:
        log_warning(e, f"Failed to save Immich assets to cache for user {user_id}: {e}")


def _normalize_immich_asset(
    asset_data: Dict[str, Any],
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
    title = asset_data.get("originalFileName") or asset_data.get("originalPath") or f"Asset {asset_id[:8]}"

    # taken_at: prefer localDateTime (user requested for timeline grouping),
    # then exifInfo.dateTimeOriginal, fall back to createdAt
    exif_info = asset_data.get("exifInfo", {})
    taken_at_str = (
        asset_data.get("localDateTime") or
        exif_info.get("dateTimeOriginal") or
        asset_data.get("createdAt")
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
            log_warning(e, f"Failed to parse taken_at for asset {asset_id}: {taken_at_str}")

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


def _build_signed_proxy_url(
    provider: Union[IntegrationProvider, str],
    asset_id: str,
    user_id: str,
    variant: str,
    ttl_seconds: int,
) -> str:
    # Handle both enum and string types for provider
    provider_value = provider.value if isinstance(provider, IntegrationProvider) else provider
    expires_at = int(time.time()) + ttl_seconds
    query = build_signed_query(provider_value, variant, asset_id, str(user_id), expires_at)
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
