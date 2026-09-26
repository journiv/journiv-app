"""
Regression test: draft recovery drops media the server can't sign.

`GET /moments/{id}/media` (`MediaService.get_signed_moment_media`) used to
call `attach_signed_urls` with `include_incomplete=False`, which returns
`signed_url: None` for a copy import still processing, a failed import, or
a HEIC copy with no display file yet. The frontend's draft recovery treats a
null URL as "this attachment did not survive" and drops it from the
recovered delta, and saving that recovered draft then makes the backend
orphan-delete the still-processing media.

The endpoint now applies the same fallback `_resolve_signed_url` already
uses for entry delta hydration: sign the media endpoint directly whenever
`attach_signed_urls` yields no URL for an existing row, so every row the
moment actually has gets a resolvable URL. `upload_status` is untouched, so
the gallery still shows "Processing"/"unavailable" from status.
"""
import uuid
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, create_engine

from app.models.base import BaseModel
from app.models.enums import MediaType, UploadStatus
from app.models.moment import Moment, MomentMedia
from app.models.user import User
from app.services import media_service as media_service_module
from app.services.media_service import MediaService
from app.services.media_storage_service import MediaStorageService


def _build_service(tmp_path: Path) -> MediaService:
    media_root = tmp_path / "media"
    media_root.mkdir()
    with patch.object(media_service_module.settings, "media_root", str(media_root)):
        service = MediaService()
        service.media_root = media_root
        service.media_storage_service = MediaStorageService(media_root, None)
        return service


def _setup_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    return Session(engine)


def _create_user(session: Session) -> User:
    user = User(email=f"test_{uuid.uuid4().hex[:8]}@example.com", password="hashed", name="Test User")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _create_moment(session: Session, user_id: uuid.UUID) -> Moment:
    moment = Moment(user_id=user_id)
    session.add(moment)
    session.commit()
    session.refresh(moment)
    return moment


def test_processing_and_failed_media_still_get_a_signed_url(tmp_path):
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)

    processing_copy = MomentMedia(
        moment_id=moment.id,
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=UploadStatus.PROCESSING,
        external_provider="immich",
        external_asset_id="asset-processing",
    )
    failed_copy = MomentMedia(
        moment_id=moment.id,
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=UploadStatus.FAILED,
        external_provider="immich",
        external_asset_id="asset-failed",
    )
    session.add(processing_copy)
    session.add(failed_copy)
    session.commit()

    service = _build_service(tmp_path)
    with patch("app.services.media_service.signed_url_for_journiv", return_value="https://signed.example/media"):
        results = service.get_signed_moment_media(session, user.id, moment.id)

    by_asset = {r.external_asset_id: r for r in results}
    assert by_asset["asset-processing"].signed_url is not None
    assert by_asset["asset-processing"].upload_status == UploadStatus.PROCESSING
    assert by_asset["asset-failed"].signed_url is not None
    assert by_asset["asset-failed"].upload_status == UploadStatus.FAILED
