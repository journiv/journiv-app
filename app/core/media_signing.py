"""
Helpers for signing and validating media URLs.
"""
from __future__ import annotations

import time
from typing import Optional
from urllib.parse import urlencode

from app.core.config import settings
from app.core.signing import generate_media_signature
from app.models.enums import UploadStatus
from app.models.integration import IntegrationProvider
from app.schemas.entry import EntryMediaResponse, MediaOrigin


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
        raise ValueError("Cannot generate signed URL for media with no ID")

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
