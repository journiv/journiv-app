import uuid
from datetime import datetime, timezone

from app.core.media_signing import attach_signed_urls, normalize_delta_media_ids
from app.models.entry import EntryMedia
from app.models.enums import MediaType, UploadStatus
from app.models.integration import IntegrationProvider
from app.schemas.entry import EntryMediaResponse


def _media_entry(entry_id: uuid.UUID, media_id: uuid.UUID, *, external_asset_id: str | None = None):
    return EntryMedia(
        id=media_id,
        entry_id=entry_id,
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
        file_path="/data/media/file.jpg" if external_asset_id is None else None,
        file_size=1024 if external_asset_id is None else None,
        external_provider=IntegrationProvider.IMMICH.value if external_asset_id else None,
        external_asset_id=external_asset_id,
    )


def test_normalize_delta_media_ids_keeps_existing_ids():
    entry_id = uuid.uuid4()
    media_id = uuid.uuid4()
    media = _media_entry(entry_id, media_id)

    delta = {"ops": [{"insert": {"image": str(media_id)}}]}
    normalized = normalize_delta_media_ids(delta, [media])

    assert normalized["ops"][0]["insert"]["image"] == str(media_id)


def test_normalize_delta_media_ids_from_media_path():
    entry_id = uuid.uuid4()
    media_id = uuid.uuid4()
    media = _media_entry(entry_id, media_id)

    source = f"https://example.com/api/v1/media/{media_id}/signed?uid=abc&exp=1&sig=xyz"
    delta = {"ops": [{"insert": {"image": source}}]}
    normalized = normalize_delta_media_ids(delta, [media])

    assert normalized["ops"][0]["insert"]["image"] == str(media_id)


def test_normalize_delta_media_ids_from_immich_proxy_and_scheme():
    entry_id = uuid.uuid4()
    media_id = uuid.uuid4()
    asset_id = str(uuid.uuid4())
    media = _media_entry(entry_id, media_id, external_asset_id=asset_id)

    delta = {
        "ops": [
            {"insert": {"image": f"/api/v1/integrations/immich/proxy/{asset_id}/original"}},
            {"insert": {"video": f"immich://{asset_id}"}},
            {"insert": {"audio": f"pending://immich/{asset_id}"}},
        ]
    }
    normalized = normalize_delta_media_ids(delta, [media])

    assert normalized["ops"][0]["insert"]["image"] == str(media_id)
    assert normalized["ops"][1]["insert"]["video"] == str(media_id)
    assert normalized["ops"][2]["insert"]["audio"] == str(media_id)


def test_normalize_delta_media_ids_sanitizes_multi_embed():
    entry_id = uuid.uuid4()
    media_id = uuid.uuid4()
    media = _media_entry(entry_id, media_id)

    delta = {"ops": [{"insert": {"image": str(media_id), "video": "ignored"}}]}
    normalized = normalize_delta_media_ids(delta, [media])

    assert normalized["ops"][0]["insert"] == {"image": str(media_id)}


def test_attach_signed_urls_link_only_immich_generates_urls():
    media_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    response = EntryMediaResponse(
        id=media_id,
        entry_id=entry_id,
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
        file_path=None,
        external_provider=IntegrationProvider.IMMICH.value,
        external_asset_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
    )

    signed = attach_signed_urls(
        response,
        user_id=str(uuid.uuid4()),
        external_base_url="https://immich.example.com",
    )

    assert signed.signed_url is not None
    assert str(media_id) in signed.signed_url
    assert signed.origin is not None
    assert signed.origin.source == IntegrationProvider.IMMICH.value


def test_attach_signed_urls_pending_media_skips_urls():
    media_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    response = EntryMediaResponse(
        id=media_id,
        entry_id=entry_id,
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=UploadStatus.PENDING,
        file_path="/data/media/file.jpg",
        created_at=datetime.now(timezone.utc),
    )

    signed = attach_signed_urls(response, user_id=str(uuid.uuid4()))

    assert signed.signed_url is None
    assert signed.signed_thumbnail_url is None


def test_attach_signed_urls_local_media_no_thumbnail():
    media_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    response = EntryMediaResponse(
        id=media_id,
        entry_id=entry_id,
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
        file_path="/data/media/file.jpg",
        file_size=1024,
        thumbnail_path=None,
        created_at=datetime.now(timezone.utc),
    )

    signed = attach_signed_urls(response, user_id=str(uuid.uuid4()))

    assert signed.signed_url is not None
    assert signed.signed_thumbnail_url is None
