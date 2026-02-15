"""Tests for HEIC/HEIF-specific signed URL gating in attach_signed_urls."""
import uuid
from datetime import datetime, timezone

from app.core.media_signing import attach_signed_urls
from app.models.enums import MediaType, UploadStatus
from app.schemas.entry import EntryMediaResponse


def _heic_response(
    *,
    file_path: str | None = "/data/media/img.heic",
    display_path: str | None = None,
    upload_status: UploadStatus = UploadStatus.COMPLETED,
    mime_type: str = "image/heic",
) -> EntryMediaResponse:
    return EntryMediaResponse(
        id=uuid.uuid4(),
        entry_id=uuid.uuid4(),
        media_type=MediaType.IMAGE,
        mime_type=mime_type,
        upload_status=upload_status,
        file_path=file_path,
        display_path=display_path,
        file_size=1024,
        created_at=datetime.now(timezone.utc),
    )


def test_heic_without_display_path_skips_signed_url():
    """HEIC with file_path but no display_path should NOT get a signed URL."""
    response = _heic_response(file_path="/data/media/img.heic", display_path=None)

    signed = attach_signed_urls(response, user_id=str(uuid.uuid4()))

    assert signed.signed_url is None


def test_heic_with_display_path_generates_signed_url():
    """HEIC with display_path set should get a signed URL."""
    response = _heic_response(
        file_path="/data/media/img.heic",
        display_path="/data/media/img_display.webp",
    )

    signed = attach_signed_urls(response, user_id=str(uuid.uuid4()))

    assert signed.signed_url is not None
    assert str(response.id) in signed.signed_url


def test_heif_mime_type_also_gates_on_display_path():
    """image/heif should behave the same as image/heic."""
    response = _heic_response(mime_type="image/heif", display_path=None)

    signed = attach_signed_urls(response, user_id=str(uuid.uuid4()))

    assert signed.signed_url is None


def test_heic_sequence_mime_type_gates_on_display_path():
    """image/heic-sequence should also be gated."""
    response = _heic_response(mime_type="image/heic-sequence", display_path=None)

    signed = attach_signed_urls(response, user_id=str(uuid.uuid4()))

    assert signed.signed_url is None


def test_jpeg_still_uses_file_path():
    """Non-HEIC images should still use file_path for URL generation."""
    response = EntryMediaResponse(
        id=uuid.uuid4(),
        entry_id=uuid.uuid4(),
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
        file_path="/data/media/photo.jpg",
        display_path=None,
        file_size=2048,
        created_at=datetime.now(timezone.utc),
    )

    signed = attach_signed_urls(response, user_id=str(uuid.uuid4()))

    assert signed.signed_url is not None


def test_heic_include_incomplete_still_gates_on_display_path():
    """Even with include_incomplete=True, HEIC without display_path gets no URL."""
    response = _heic_response(
        upload_status=UploadStatus.COMPLETED,
        display_path=None,
    )

    signed = attach_signed_urls(
        response, user_id=str(uuid.uuid4()), include_incomplete=True
    )

    assert signed.signed_url is None
