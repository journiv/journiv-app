"""Regression tests for serving local HEIC display assets."""

import uuid
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import FileResponse

from app.api.v1.endpoints import media as media_endpoint


@pytest.mark.asyncio
async def test_signed_media_uses_browser_compatible_display_version(
    tmp_path: Path,
) -> None:
    """The signed display route must not send raw HEIC bytes to the browser."""
    media_id = uuid.uuid4()
    user_id = uuid.uuid4()
    display_path = tmp_path / "photo_display.webp"
    display_path.write_bytes(b"webp display bytes")

    media = MagicMock(
        external_provider=None,
        external_asset_id=None,
        file_path="images/photo.heic",
    )
    service = MagicMock()
    service.get_media_by_id.return_value = media
    service.get_media_file_for_display = AsyncMock(
        return_value={
            "range_info": None,
            "file_path": display_path,
            "content_type": "image/webp",
            "filename": "photo_display.webp",
            "file_size": display_path.stat().st_size,
        }
    )
    session = MagicMock()

    with (
        patch.object(
            media_endpoint,
            "is_signature_expired",
            return_value=False,
        ),
        patch.object(
            media_endpoint,
            "verify_media_signature",
            return_value=True,
        ),
        patch.object(
            media_endpoint,
            "_get_media_service",
            return_value=service,
        ),
        patch.object(
            media_endpoint.database_module,
            "get_session_context",
            return_value=nullcontext(session),
        ),
    ):
        response = await media_endpoint.get_media_signed(
            media_id=media_id,
            uid=user_id,
            exp=2_000_000_000,
            sig="valid-signature",
        )

    assert isinstance(response, FileResponse)
    assert Path(response.path) == display_path
    assert response.media_type == "image/webp"

    service.get_media_file_for_display.assert_awaited_once_with(
        media_id,
        user_id,
        session,
        None,
    )


@pytest.mark.asyncio
async def test_signed_legacy_heic_thumbnail_is_advertised_as_jpeg(
    tmp_path: Path,
) -> None:
    """Old JPEG thumbnails with a .heic suffix still need a JPEG MIME type."""
    media_id = uuid.uuid4()
    user_id = uuid.uuid4()
    legacy_thumbnail = tmp_path / "thumb_photo.heic"
    legacy_thumbnail.write_bytes(b"jpeg thumbnail bytes")

    media = MagicMock(
        external_provider=None,
        external_asset_id=None,
        thumbnail_path="images/thumb_photo.heic",
    )
    service = MagicMock()
    service.get_media_by_id.return_value = media
    service.get_media_thumbnail_path.return_value = legacy_thumbnail
    session = MagicMock()

    with (
        patch.object(
            media_endpoint,
            "is_signature_expired",
            return_value=False,
        ),
        patch.object(
            media_endpoint,
            "verify_media_signature",
            return_value=True,
        ),
        patch.object(
            media_endpoint,
            "_get_media_service",
            return_value=service,
        ),
        patch.object(
            media_endpoint.database_module,
            "get_session_context",
            return_value=nullcontext(session),
        ),
    ):
        response = await media_endpoint.get_media_thumbnail_signed(
            media_id=media_id,
            uid=user_id,
            exp=2_000_000_000,
            sig="valid-signature",
        )

    assert isinstance(response, FileResponse)
    assert Path(response.path) == legacy_thumbnail
    assert response.media_type == "image/jpeg"

    service.get_media_thumbnail_path.assert_called_once_with(media)
