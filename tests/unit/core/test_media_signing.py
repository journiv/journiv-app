import time
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.core.media_signing import (
    attach_signed_urls,
    attach_signed_urls_to_delta,
    normalize_delta_media_ids,
)
from app.models.moment import MomentMedia
from app.models.enums import MediaType, UploadStatus
from app.models.integration import IntegrationProvider
from app.schemas.entry import MomentMediaResponse


def _media_entry(moment_id: uuid.UUID, media_id: uuid.UUID, *, external_asset_id: str | None = None):
    return MomentMedia(
        id=media_id,
        moment_id=moment_id,
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
        file_path="/data/media/file.jpg" if external_asset_id is None else None,
        file_size=1024 if external_asset_id is None else None,
        external_provider=IntegrationProvider.IMMICH.value if external_asset_id else None,
        external_asset_id=external_asset_id,
    )


def test_normalize_delta_media_ids_keeps_existing_ids():
    moment_id = uuid.uuid4()
    media_id = uuid.uuid4()
    media = _media_entry(moment_id, media_id)

    delta = {"ops": [{"insert": {"image": str(media_id)}}]}
    normalized = normalize_delta_media_ids(delta, [media])

    assert normalized["ops"][0]["insert"]["image"] == str(media_id)


def test_normalize_delta_media_ids_from_media_path():
    moment_id = uuid.uuid4()
    media_id = uuid.uuid4()
    media = _media_entry(moment_id, media_id)

    source = f"https://example.com/api/v1/media/{media_id}/signed?uid=abc&exp=1&sig=xyz"
    delta = {"ops": [{"insert": {"image": source}}]}
    normalized = normalize_delta_media_ids(delta, [media])

    assert normalized["ops"][0]["insert"]["image"] == str(media_id)


def test_normalize_delta_media_ids_from_immich_proxy_and_scheme():
    moment_id = uuid.uuid4()
    media_id = uuid.uuid4()
    asset_id = str(uuid.uuid4())
    media = _media_entry(moment_id, media_id, external_asset_id=asset_id)

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
    moment_id = uuid.uuid4()
    media_id = uuid.uuid4()
    media = _media_entry(moment_id, media_id)

    delta = {"ops": [{"insert": {"image": str(media_id), "video": "ignored"}}]}
    normalized = normalize_delta_media_ids(delta, [media])

    assert normalized["ops"][0]["insert"] == {"image": str(media_id)}


def test_attach_signed_urls_link_only_immich_generates_urls():
    media_id = uuid.uuid4()
    moment_id = uuid.uuid4()
    response = MomentMediaResponse(
        id=media_id,
        moment_id=moment_id,
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
    moment_id = uuid.uuid4()
    response = MomentMediaResponse(
        id=media_id,
        moment_id=moment_id,
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
    moment_id = uuid.uuid4()
    response = MomentMediaResponse(
        id=media_id,
        moment_id=moment_id,
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


def _immich_response(upload_status: UploadStatus) -> MomentMediaResponse:
    return MomentMediaResponse(
        id=uuid.uuid4(),
        moment_id=uuid.uuid4(),
        media_type=MediaType.IMAGE,
        mime_type="application/octet-stream",
        upload_status=upload_status,
        file_path=None,
        external_provider=IntegrationProvider.IMMICH.value,
        external_asset_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
    )


def test_attach_signed_urls_in_progress_immich_copy_is_proxied_when_incomplete_requested():
    """The import response must give the editor a URL while the copy downloads."""
    response = _immich_response(UploadStatus.PROCESSING)

    signed = attach_signed_urls(response, user_id=str(uuid.uuid4()), include_incomplete=True)

    assert signed.signed_url is not None
    assert str(response.id) in signed.signed_url
    assert signed.signed_thumbnail_url is not None


def test_attach_signed_urls_in_progress_immich_copy_skipped_by_default():
    response = _immich_response(UploadStatus.PROCESSING)

    signed = attach_signed_urls(response, user_id=str(uuid.uuid4()))

    assert signed.signed_url is None
    assert signed.signed_thumbnail_url is None


def test_attach_signed_urls_failed_immich_media_skips_urls():
    response = _immich_response(UploadStatus.FAILED)

    signed = attach_signed_urls(response, user_id=str(uuid.uuid4()), include_incomplete=True)

    assert signed.signed_url is None
    assert signed.signed_thumbnail_url is None


class _MemoryCache:
    def __init__(self):
        self._store: dict[tuple[str, str], dict] = {}

    def get(self, key, namespace):
        return self._store.get((key, namespace))

    def set(self, key, namespace, value, ttl_seconds=None):
        self._store[(key, namespace)] = value


def _unsignable_media(moment_id: uuid.UUID) -> list[MomentMedia]:
    """Media rows attach_signed_urls gives no URL: the states issue #367 hit."""
    return [
        MomentMedia(
            id=uuid.uuid4(),
            moment_id=moment_id,
            media_type=MediaType.IMAGE,
            mime_type="image/jpeg",
            upload_status=UploadStatus.FAILED,
            external_provider=IntegrationProvider.IMMICH.value,
            external_asset_id=str(uuid.uuid4()),
        ),
        MomentMedia(
            id=uuid.uuid4(),
            moment_id=moment_id,
            media_type=MediaType.IMAGE,
            mime_type="application/octet-stream",
            upload_status=UploadStatus.PROCESSING,
            external_provider=IntegrationProvider.IMMICH.value,
            external_asset_id=str(uuid.uuid4()),
        ),
        MomentMedia(
            id=uuid.uuid4(),
            moment_id=moment_id,
            media_type=MediaType.IMAGE,
            mime_type="image/heic",
            upload_status=UploadStatus.COMPLETED,
            file_path="user/images/x.HEIC",
            file_size=1024,
            external_provider=IntegrationProvider.IMMICH.value,
            external_asset_id=str(uuid.uuid4()),
        ),
    ]


def test_attach_signed_urls_to_delta_never_leaves_bare_media_ids():
    """An unsignable media row must still hydrate to a signed URL, not its id.

    Clients cannot render a bare id and treat the whole entry as unsupported
    (the React editor refuses to open it).
    """
    moment_id = uuid.uuid4()
    media_items = _unsignable_media(moment_id)
    delta = {
        "ops": [{"insert": {"image": str(media.id)}} for media in media_items]
        + [{"insert": "\n"}]
    }

    hydrated = attach_signed_urls_to_delta(
        delta, media_items, str(uuid.uuid4()), cache=_MemoryCache()
    )

    for op, media in zip(hydrated["ops"], media_items):
        source = op["insert"]["image"]
        assert source.startswith(f"/api/v1/media/{media.id}/signed?")
        assert "sig=" in source


def test_attach_signed_urls_video_gets_video_ttl():
    """
    Regression: `str(MediaType.VIDEO).lower()` is `"mediatype.video"`, not
    `"video"` (`MediaType` is a plain Enum, not overriding `__str__`), so the
    video check was never true and every video got the 5-minute image TTL —
    seeking after 5 minutes could 403.
    """
    media_id = uuid.uuid4()
    moment_id = uuid.uuid4()
    response = MomentMediaResponse(
        id=media_id,
        moment_id=moment_id,
        media_type=MediaType.VIDEO,
        mime_type="video/mp4",
        upload_status=UploadStatus.COMPLETED,
        file_path="/data/media/clip.mp4",
        file_size=1024,
        created_at=datetime.now(timezone.utc),
    )

    before = int(time.time())
    signed = attach_signed_urls(response, user_id=str(uuid.uuid4()))

    assert signed.signed_url_expires_at is not None
    ttl = signed.signed_url_expires_at - before
    # Within a couple of seconds of the video TTL, not the (shorter) image one.
    assert abs(ttl - settings.media_signed_url_video_ttl_seconds) <= 2
    assert ttl > settings.media_signed_url_ttl_seconds


class _RecordingCache:
    """Like `_MemoryCache`, but keeps the `ttl_seconds` each `set()` was given."""

    def __init__(self):
        self._store: dict[tuple[str, str], dict] = {}
        self.set_ttls: list[int | None] = []

    def get(self, key, namespace):
        return self._store.get((key, namespace))

    def set(self, key, namespace, value, ttl_seconds=None):
        self._store[(key, namespace)] = value
        self.set_ttls.append(ttl_seconds)


def test_resolve_signed_url_cache_ttl_matches_video_expiry():
    """
    The delta-hydration cache entry's own TTL must track the signature's
    actual expiry (longer for video), not a hard-coded image TTL — otherwise
    the cache backend evicts a still-valid video URL early and re-signs it
    four times as often as necessary.
    """
    moment_id = uuid.uuid4()
    media = MomentMedia(
        id=uuid.uuid4(),
        moment_id=moment_id,
        media_type=MediaType.VIDEO,
        mime_type="video/mp4",
        upload_status=UploadStatus.COMPLETED,
        file_path="/data/media/clip.mp4",
        file_size=1024,
    )
    delta = {"ops": [{"insert": {"video": str(media.id)}}, {"insert": "\n"}]}
    cache = _RecordingCache()

    attach_signed_urls_to_delta(delta, [media], str(uuid.uuid4()), cache=cache)

    assert len(cache.set_ttls) == 1
    ttl = cache.set_ttls[0]
    assert ttl is not None
    assert abs(ttl - settings.media_signed_url_video_ttl_seconds) <= 2
    assert ttl > settings.media_signed_url_ttl_seconds
