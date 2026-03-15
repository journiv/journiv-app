import uuid
from pathlib import Path

from app.models.enums import MediaType, UploadStatus
from app.models.moment import MomentMedia
from app.services.pdf_service import EntryPDFService


def _build_media(
    *,
    media_id: uuid.UUID,
    file_path: str | None,
    mime_type: str = "image/jpeg",
    display_path: str | None = None,
    external_provider: str | None = None,
    external_asset_id: str | None = None,
) -> MomentMedia:
    return MomentMedia(
        id=media_id,
        moment_id=uuid.uuid4(),
        media_type=MediaType.IMAGE,
        file_path=file_path,
        file_size=1,
        display_path=display_path,
        mime_type=mime_type,
        upload_status=UploadStatus.COMPLETED,
        external_provider=external_provider,
        external_asset_id=external_asset_id,
    )


def test_media_resolver_uses_local_display_asset_for_owned_pdf(tmp_path: Path):
    service = EntryPDFService(session=None)
    service.media_service.media_root = tmp_path

    display_file = tmp_path / "images" / "photo_display.webp"
    display_file.parent.mkdir(parents=True, exist_ok=True)
    display_file.write_bytes(b"webp")

    media_id = uuid.uuid4()
    media = _build_media(
        media_id=media_id,
        file_path="images/photo.heic",
        mime_type="image/heic",
        display_path="images/photo_display.webp",
    )

    resolver = service._build_media_url_resolver(
        media_items=[media],
        user_id=uuid.uuid4(),
    )

    assert resolver("image", str(media_id)) == display_file.as_uri()


def test_media_resolver_maps_signed_media_url_back_to_local_file(tmp_path: Path):
    service = EntryPDFService(session=None)
    service.media_service.media_root = tmp_path

    original_file = tmp_path / "images" / "photo.jpg"
    original_file.parent.mkdir(parents=True, exist_ok=True)
    original_file.write_bytes(b"jpg")

    media_id = uuid.uuid4()
    media = _build_media(
        media_id=media_id,
        file_path="images/photo.jpg",
    )

    resolver = service._build_media_url_resolver(
        media_items=[media],
        user_id=uuid.uuid4(),
    )

    signed_source = f"/api/v1/media/{media_id}/signed?uid=user&exp=1&sig=test"
    assert resolver("image", signed_source) == original_file.as_uri()


def test_media_resolver_uses_public_media_route_when_local_file_missing():
    service = EntryPDFService(session=None)

    media_id = uuid.uuid4()
    media = _build_media(
        media_id=media_id,
        file_path=None,
        external_provider="immich",
        external_asset_id=str(uuid.uuid4()),
    )

    resolver = service._build_media_url_resolver(
        media_items=[media],
        public_fallback=True,
    )

    assert (
        resolver("image", str(media_id))
        == f"{service._get_base_url()}/pub/media/{media_id}"
    )


def test_media_resolver_rejects_unknown_absolute_url():
    service = EntryPDFService(session=None)

    resolver = service._build_media_url_resolver(
        media_items=[],
        user_id=uuid.uuid4(),
    )

    assert resolver("video", "https://example.com/video.mp4") == ""


def test_media_resolver_rejects_unknown_root_relative_path():
    service = EntryPDFService(session=None)

    resolver = service._build_media_url_resolver(
        media_items=[],
        user_id=uuid.uuid4(),
    )

    assert resolver("image", "/not-a-media-route/example.jpg") == ""


def test_media_resolver_allows_trusted_public_media_path():
    service = EntryPDFService(session=None)

    resolver = service._build_media_url_resolver(
        media_items=[],
        public_fallback=True,
    )

    assert (
        resolver("video", "/pub/media/fallback-preview")
        == f"{service._get_base_url()}/pub/media/fallback-preview"
    )


def test_collect_attachment_image_urls_includes_moment_images_not_in_delta(
    tmp_path: Path,
):
    service = EntryPDFService(session=None)
    service.media_service.media_root = tmp_path

    first_file = tmp_path / "images" / "first.jpg"
    second_file = tmp_path / "images" / "second.jpg"
    first_file.parent.mkdir(parents=True, exist_ok=True)
    first_file.write_bytes(b"1")
    second_file.write_bytes(b"2")

    first = _build_media(media_id=uuid.uuid4(), file_path="images/first.jpg")
    second = _build_media(media_id=uuid.uuid4(), file_path="images/second.jpg")

    resolver = service._build_media_url_resolver(
        media_items=[first, second],
        user_id=uuid.uuid4(),
    )

    attachment_items = service._collect_attachment_items(
        delta_payload={"ops": [{"insert": "\n"}]},
        media_items=[first, second],
        media_url_resolver=resolver,
    )

    assert attachment_items == [
        {
            "kind": "image",
            "url": first_file.as_uri(),
            "label": "Image attachment",
            "alt_text": "",
        },
        {
            "kind": "image",
            "url": second_file.as_uri(),
            "label": "Image attachment",
            "alt_text": "",
        },
    ]


def test_collect_attachment_items_skips_inline_video(tmp_path: Path):
    service = EntryPDFService(session=None)
    service.media_service.media_root = tmp_path

    video_file = tmp_path / "videos" / "clip.mp4"
    video_thumb = tmp_path / "videos" / "thumbnails" / "thumb_clip.jpg"
    video_file.parent.mkdir(parents=True, exist_ok=True)
    video_thumb.parent.mkdir(parents=True, exist_ok=True)
    video_file.write_bytes(b"video")
    video_thumb.write_bytes(b"thumb")

    video = MomentMedia(
        id=uuid.uuid4(),
        moment_id=uuid.uuid4(),
        media_type=MediaType.VIDEO,
        file_path="videos/clip.mp4",
        file_size=1,
        thumbnail_path="videos/thumbnails/thumb_clip.jpg",
        mime_type="video/mp4",
        upload_status=UploadStatus.COMPLETED,
    )

    media_resolver = service._build_media_url_resolver(
        media_items=[video],
        user_id=uuid.uuid4(),
    )
    thumb_resolver = service._build_media_url_resolver(
        media_items=[video],
        user_id=uuid.uuid4(),
        variant="thumbnail",
    )

    attachment_items = service._collect_attachment_items(
        delta_payload={
            "ops": [
                {"insert": {"video": str(video.id)}},
                {"insert": "\n"},
            ]
        },
        media_items=[video],
        media_url_resolver=media_resolver,
        thumbnail_url_resolver=thumb_resolver,
    )

    assert attachment_items == []


def test_collect_attachment_items_keeps_non_inline_video(tmp_path: Path):
    service = EntryPDFService(session=None)
    service.media_service.media_root = tmp_path

    video_file = tmp_path / "videos" / "clip.mp4"
    video_thumb = tmp_path / "videos" / "thumbnails" / "thumb_clip.jpg"
    video_thumb.parent.mkdir(parents=True, exist_ok=True)
    video_file.write_bytes(b"video")
    video_thumb.write_bytes(b"thumb")

    video = MomentMedia(
        id=uuid.uuid4(),
        moment_id=uuid.uuid4(),
        media_type=MediaType.VIDEO,
        file_path="videos/clip.mp4",
        file_size=1,
        thumbnail_path="videos/thumbnails/thumb_clip.jpg",
        mime_type="video/mp4",
        upload_status=UploadStatus.COMPLETED,
    )

    media_resolver = service._build_media_url_resolver(
        media_items=[video],
        user_id=uuid.uuid4(),
    )
    thumb_resolver = service._build_media_url_resolver(
        media_items=[video],
        user_id=uuid.uuid4(),
        variant="thumbnail",
    )

    attachment_items = service._collect_attachment_items(
        delta_payload={"ops": [{"insert": "\n"}]},
        media_items=[video],
        media_url_resolver=media_resolver,
        thumbnail_url_resolver=thumb_resolver,
    )

    assert len(attachment_items) == 1
    assert attachment_items[0]["kind"] == "video"
    assert attachment_items[0]["label"] == "Video attachment"
    assert attachment_items[0]["alt_text"] == ""
    assert attachment_items[0]["preview_url"] == video_thumb.as_uri()
    assert attachment_items[0]["url"].startswith(
        f"{service._get_base_url()}/api/v1/media/{video.id}/signed?"
    )


def test_public_thumbnail_resolver_does_not_fake_preview_route():
    service = EntryPDFService(session=None)

    media = MomentMedia(
        id=uuid.uuid4(),
        moment_id=uuid.uuid4(),
        media_type=MediaType.VIDEO,
        file_path=None,
        file_size=1,
        thumbnail_path=None,
        mime_type="video/mp4",
        upload_status=UploadStatus.COMPLETED,
        external_provider="immich",
        external_asset_id=str(uuid.uuid4()),
    )

    thumb_resolver = service._build_media_url_resolver(
        media_items=[media],
        public_fallback=True,
        variant="thumbnail",
    )

    assert thumb_resolver("video", str(media.id)) == ""
