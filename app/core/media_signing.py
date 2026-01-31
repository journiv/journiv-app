"""
Helpers for signing and validating media URLs.
"""
from __future__ import annotations

import time
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse
from urllib.parse import urlencode

from app.core.config import settings
from app.core.logging_config import log_warning, log_debug
from app.core.scoped_cache import ScopedCache
from app.core.signing import generate_media_signature
from app.models.entry import EntryMedia
from app.models.enums import UploadStatus
from app.models.integration import IntegrationProvider
from app.schemas.entry import EntryMediaResponse, MediaOrigin
from app.utils.quill_delta import transform_delta_media

# Shared cache instance to avoid creating new Redis connections on every request
_delta_media_cache: Optional[ScopedCache] = None


def _build_signed_url(path: str, query: dict[str, str | int]) -> str:
    """Build a signed URL from path and query parameters."""
    if not path:
        raise ValueError("path cannot be empty")
    query_string = urlencode(query)
    return f"{path}?{query_string}"


def build_signed_query(
    media_type: str,
    variant: str,
    media_id: str,
    user_id: str,
    expires_at: int,
) -> dict[str, str | int]:
    signature = generate_media_signature(
        media_type,
        variant,
        media_id,
        user_id,
        expires_at,
        settings.secret_key,
    )
    return {"uid": user_id, "exp": expires_at, "sig": signature}


def signed_url_for_journiv(
    media_id: str,
    user_id: str,
    variant: str,
    expires_at: int,
) -> str:
    """Generate a signed URL for Journiv-hosted media (internal or proxied external)."""
    if not media_id or not str(media_id).strip():
        raise ValueError("media_id cannot be empty")
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id cannot be empty")

    path = (
        f"/api/v1/media/{media_id}/thumbnail/signed"
        if variant == "thumbnail"
        else f"/api/v1/media/{media_id}/signed"
    )
    return _build_signed_url(
        path,
        build_signed_query("journiv", variant, media_id, user_id, expires_at),
    )


def signed_url_for_immich(
    asset_id: str,
    user_id: str,
    variant: str,
    expires_at: int,
) -> str:
    """Generate a signed URL for Immich-hosted media (proxied through Journiv)."""
    if not asset_id or not str(asset_id).strip():
        raise ValueError("asset_id cannot be empty")
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id cannot be empty")

    path = f"/api/v1/integrations/{IntegrationProvider.IMMICH.value}/proxy/{asset_id}/{variant}"
    return _build_signed_url(
        path,
        build_signed_query(IntegrationProvider.IMMICH.value, variant, asset_id, user_id, expires_at),
    )


def attach_signed_urls(
    response: EntryMediaResponse,
    user_id: str,
    include_incomplete: bool = False,
    external_base_url: Optional[str] = None,
) -> EntryMediaResponse:
    """
    Attach signed URLs to media response.
    """
    # Validate inputs
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id cannot be empty")

    # Set origin metadata for Immich media
    if response.external_provider == IntegrationProvider.IMMICH.value and response.external_asset_id:
        response.origin = MediaOrigin(
            source=IntegrationProvider.IMMICH.value,
            external_id=response.external_asset_id,
            external_url=_build_external_url(external_base_url, response.external_asset_id),
        )
    elif response.external_provider is None and response.file_path:
        response.origin = MediaOrigin(source="internal")

    # 1. Skip URL generation for failed uploads
    if response.upload_status == UploadStatus.FAILED:
        response.signed_url = None
        response.signed_thumbnail_url = None
        return response

    # 2. Define logic to differentiate "Link-Only" from "In-Progress Copy"
    is_immich_link_only = (
        response.external_provider == IntegrationProvider.IMMICH.value
        and not response.file_path
        and response.upload_status == UploadStatus.COMPLETED
    )

    # 3. Determine if we should generate URLs based on the state
    # For originals: generate if it's a stable link-only asset OR we have a local file
    should_generate_original = is_immich_link_only or bool(response.file_path)

    # For thumbnails: generate if it's a stable link-only asset OR we have a local thumbnail
    should_generate_thumbnail = is_immich_link_only or bool(response.thumbnail_path)

    # Skip URL generation for pending/processing uploads unless explicitly included
    if not include_incomplete and not is_immich_link_only and response.upload_status != UploadStatus.COMPLETED:
        response.signed_url = None
        response.signed_thumbnail_url = None
        return response

    now = int(time.time())

    # Determine TTL based on media type (videos get longer TTL for streaming)
    media_type_str = str(response.media_type).lower() if response.media_type else ""
    is_video = media_type_str == "video"
    ttl_seconds = (
        settings.media_signed_url_video_ttl_seconds if is_video
        else settings.media_signed_url_ttl_seconds
    )

    expires_at = now + ttl_seconds

    if response.id is None:
        log_warning("Skipping signed URL generation: media id is missing")
        response.signed_url = None
        response.signed_thumbnail_url = None
        return response

    # 4. Generate Original URL
    if should_generate_original:
        response.signed_url = signed_url_for_journiv(
            str(response.id),
            user_id,
            "original",
            expires_at,
        )
        response.signed_url_expires_at = expires_at
    else:
        response.signed_url = None

    # 5. Generate Thumbnail URL
    if should_generate_thumbnail:
        thumb_expires_at = now + settings.media_thumbnail_signed_url_ttl_seconds
        response.signed_thumbnail_url = signed_url_for_journiv(
            str(response.id),
            user_id,
            "thumbnail",
            thumb_expires_at,
        )
        response.signed_thumbnail_expires_at = thumb_expires_at
    else:
        response.signed_thumbnail_url = None

    return response


def attach_signed_urls_to_delta(
    delta: Optional[dict],
    media_items: list[EntryMedia],
    user_id: str,
    *,
    cache: Optional[ScopedCache] = None,
    external_base_url: Optional[str] = None,
) -> Optional[dict]:
    """
    Replace media IDs in a Quill Delta with signed URLs for client consumption.
    """
    global _delta_media_cache
    if cache is None:
        if _delta_media_cache is None:
            _delta_media_cache = ScopedCache("entry_delta_media")
        cache = _delta_media_cache

    media_map = {str(media.id): media for media in media_items}

    def transform_to_signed_url(_key: str, media_id: str) -> Optional[str]:
        media = media_map.get(media_id)
        if not media:
            return None
        return _resolve_signed_url(media, user_id, cache, external_base_url)

    return transform_delta_media(delta, transform_to_signed_url)


_MEDIA_ID_PATTERN = r"([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})"
_MEDIA_PATH_RE = re.compile(rf"/api/v1/media/{_MEDIA_ID_PATTERN}", re.IGNORECASE)
_IMMICH_PROXY_RE = re.compile(
    rf"/api/v1/integrations/immich/proxy/{_MEDIA_ID_PATTERN}",
    re.IGNORECASE,
)
_IMMICH_SCHEME_RE = re.compile(rf"^immich://{_MEDIA_ID_PATTERN}$", re.IGNORECASE)
_IMMICH_PENDING_RE = re.compile(rf"^pending://immich/{_MEDIA_ID_PATTERN}$", re.IGNORECASE)


def normalize_delta_media_ids(
    delta: Optional[dict],
    media_items: list[EntryMedia],
) -> Optional[dict]:
    """Normalize media URLs in a Quill delta to media UUIDs before persistence."""
    media_by_id = {str(media.id): media for media in media_items}
    immich_by_asset_id = {
        str(media.external_asset_id): str(media.id)
        for media in media_items
        if media.external_provider == IntegrationProvider.IMMICH.value and media.external_asset_id
    }

    # Track statistics for logging
    stats = {
        "total_sources": 0,
        "mapped_sources": 0,
        "empty_sources": 0,
    }

    def transform_to_media_id(key: str, source: str) -> Optional[str]:
        stats["total_sources"] += 1

        if source == "":
            stats["empty_sources"] += 1
            log_warning("normalize_delta_media_ids: empty source encountered", source_key=key)
            return None

        media_id = _extract_media_id_from_source(source, media_by_id, immich_by_asset_id)
        if media_id:
            stats["mapped_sources"] += 1
            return media_id
        else:
            log_warning(
                "normalize_delta_media_ids: no mapping found",
                source_key=key,
                source=source,
            )
            return None

    result = transform_delta_media(delta, transform_to_media_id)

    if result:
        ops_count = len(result.get("ops", []))
        log_debug(
            "normalize_delta_media_ids: completed",
            ops=ops_count,
            media_count=len(media_by_id),
            immich_asset_count=len(immich_by_asset_id),
            total_sources=stats["total_sources"],
            mapped_sources=stats["mapped_sources"],
            empty_sources=stats["empty_sources"],
        )

    return result


def _extract_media_id_from_source(
    source: str,
    media_by_id: dict[str, EntryMedia],
    immich_by_asset_id: dict[str, str],
) -> Optional[str]:
    if source in media_by_id:
        return source

    uri = urlparse(source)
    if uri.query:
        query_params = parse_qs(uri.query)
        media_ids = query_params.get("media_id") or []
        for media_id in media_ids:
            if media_id in media_by_id:
                return media_id

    path = uri.path or source

    media_match = _MEDIA_PATH_RE.search(path)
    if media_match:
        media_id = media_match.group(1)
        if media_id in media_by_id:
            return media_id

    immich_match = _IMMICH_PROXY_RE.search(path)
    if immich_match:
        asset_id = immich_match.group(1)
        if asset_id in immich_by_asset_id:
            log_warning(
                "normalize_delta_media_ids: immich proxy mapped",
                asset_id=asset_id,
                media_id=immich_by_asset_id[asset_id],
            )
        return immich_by_asset_id.get(asset_id)

    immich_scheme_match = _IMMICH_SCHEME_RE.match(source)
    if immich_scheme_match:
        asset_id = immich_scheme_match.group(1)
        if asset_id in immich_by_asset_id:
            log_warning(
                "normalize_delta_media_ids: immich scheme mapped",
                asset_id=asset_id,
                media_id=immich_by_asset_id[asset_id],
            )
        return immich_by_asset_id.get(asset_id)

    immich_pending_match = _IMMICH_PENDING_RE.match(source)
    if immich_pending_match:
        asset_id = immich_pending_match.group(1)
        if asset_id in immich_by_asset_id:
            log_warning(
                "normalize_delta_media_ids: immich pending mapped",
                asset_id=asset_id,
                media_id=immich_by_asset_id[asset_id],
            )
        return immich_by_asset_id.get(asset_id)

    id_match = re.search(_MEDIA_ID_PATTERN, source, re.IGNORECASE)
    if id_match:
        media_id = id_match.group(1)
        if media_id in media_by_id:
            return media_id

    return None


def _resolve_signed_url(
    media: EntryMedia,
    user_id: str,
    cache: ScopedCache,
    external_base_url: Optional[str],
) -> Optional[str]:
    cache_key = f"{user_id}__{media.entry_id}__{media.id}__original"
    cached = cache.get(cache_key, "signed_url")
    if cached:
        expires_at = cached.get("expires_at")
        if isinstance(expires_at, int) and not is_signature_expired(
            expires_at,
            settings.media_signed_url_grace_seconds,
        ):
            return cached.get("url")

    try:
        response = attach_signed_urls(
            EntryMediaResponse.model_validate(media),
            user_id,
            external_base_url=external_base_url,
        )
    except Exception as exc:  # noqa: BLE001 - Broad except intentional for best-effort media signing
        log_warning(exc, "Failed to sign media in delta hydration (attach_signed_urls/model_validate)")
        return None
    if response.signed_url and response.signed_url_expires_at:
        cache.set(
            cache_key,
            "signed_url",
            {"url": response.signed_url, "expires_at": response.signed_url_expires_at},
            ttl_seconds=settings.media_signed_url_ttl_seconds,
        )
    return response.signed_url


def _build_external_url(base_url: Optional[str], asset_id: str) -> Optional[str]:
    if not base_url:
        return None
    normalized = base_url.rstrip('/')
    return f"{normalized}/photos/{asset_id}"


def is_signature_expired(expires_at: int, grace_seconds: int, now: Optional[int] = None) -> bool:
    """
    Check if a signature has expired.
    """
    if grace_seconds < 0:
        raise ValueError("grace_seconds must be non-negative")
    if grace_seconds > 300:
        raise ValueError("grace_seconds cannot exceed 300 seconds")

    current = now if now is not None else int(time.time())
    return expires_at + grace_seconds < current
