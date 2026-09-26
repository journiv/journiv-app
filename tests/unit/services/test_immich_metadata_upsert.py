"""
Regression tests: width, height, duration and title fallback are never
stored on the existing-row update branch of `_upsert_entry_media`.

Every Immich import (link-only or copy) updates an EXISTING placeholder row
(created before the real Immich data arrives), so `_upsert_entry_media`'s
"update existing record" branch is the one that actually runs — and it never
copied `width`/`height`/`duration` from the extracted metadata, leaving them
null in both modes. Separately, the placeholder's `original_filename` ignored
the client's `title` (`ImmichImportAsset.title`), only reading
`originalFileName`/`originalPath` from Immich's own response shape.
"""
import uuid
from unittest.mock import patch

import pytest
from sqlmodel import Session, create_engine

from app.models.base import BaseModel
from app.models.enums import MediaType, UploadStatus
from app.models.moment import Moment, MomentMedia
from app.models.user import User
from app.services.import_job_service import ImportJobService


@pytest.fixture(autouse=True)
def _no_real_celery_dispatch():
    """The code under test queues album tasks via send_task, which ignores
    task_always_eager and would try to reach a real broker."""
    from app.core.celery_app import celery_app

    with patch.object(celery_app, "send_task") as send_task:
        yield send_task


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


def _create_placeholder(session: Session, moment_id: uuid.UUID, asset_id: str) -> MomentMedia:
    media = MomentMedia(
        moment_id=moment_id,
        media_type=MediaType.UNKNOWN,
        mime_type="application/octet-stream",
        upload_status=UploadStatus.PROCESSING,
        external_provider="immich",
        external_asset_id=asset_id,
        original_filename="Asset placeholder",
    )
    session.add(media)
    session.commit()
    session.refresh(media)
    return media


def test_upsert_existing_row_copies_dimensions_and_duration():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    asset_id = "asset-1"
    _create_placeholder(session, moment.id, asset_id)

    service = ImportJobService(session)
    asset_data = {
        "id": asset_id,
        "type": "VIDEO",
        "originalFileName": "clip.mp4",
        "mimeType": "video/mp4",
        "duration": "00:00:12.500",
        "exifInfo": {"exifImageWidth": 1920, "exifImageHeight": 1080},
    }

    updated = service._upsert_entry_media(
        moment_id=moment.id,
        user_id=user.id,
        asset_id=asset_id,
        asset_data=asset_data,
        upload_status=UploadStatus.COMPLETED,
        session=session,
    )

    assert updated.width == 1920
    assert updated.height == 1080
    assert updated.duration == 12.5


def test_upsert_existing_row_does_not_overwrite_with_none():
    """A later update with no exif/duration data must not clobber values a
    previous update already stored (metadata.get(...) is None -> skip)."""
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    asset_id = "asset-2"
    placeholder = _create_placeholder(session, moment.id, asset_id)
    placeholder.width = 800
    placeholder.height = 600
    placeholder.duration = 5.0
    session.add(placeholder)
    session.commit()

    service = ImportJobService(session)
    updated = service._upsert_entry_media(
        moment_id=moment.id,
        user_id=user.id,
        asset_id=asset_id,
        asset_data={"id": asset_id, "type": "IMAGE", "originalFileName": "photo.jpg"},
        upload_status=UploadStatus.COMPLETED,
        session=session,
    )

    assert updated.width == 800
    assert updated.height == 600
    assert updated.duration == 5.0


def test_upsert_uses_client_title_when_immich_gives_no_filename():
    """The placeholder step runs before Immich's own metadata arrives, so its
    asset_data is the client's picker payload (ImmichImportAsset), which has
    `title` but neither `originalFileName` nor `originalPath`."""
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    asset_id = "asset-3"

    service = ImportJobService(session)
    created = service._upsert_entry_media(
        moment_id=moment.id,
        user_id=user.id,
        asset_id=asset_id,
        asset_data={"id": asset_id, "type": "IMAGE", "title": "Sunset at the pier.jpg"},
        upload_status=UploadStatus.PROCESSING,
        session=session,
    )

    assert created.original_filename == "Sunset at the pier.jpg"

    # And the same fallback applies when updating an existing row.
    updated = service._upsert_entry_media(
        moment_id=moment.id,
        user_id=user.id,
        asset_id=asset_id,
        asset_data={"id": asset_id, "type": "IMAGE", "title": "Renamed at pier.jpg"},
        upload_status=UploadStatus.COMPLETED,
        session=session,
    )
    assert updated.id == created.id
    assert updated.original_filename == "Renamed at pier.jpg"


def test_extract_immich_metadata_prefers_original_filename_over_title():
    session = _setup_session()
    service = ImportJobService(session)

    metadata = service._extract_immich_metadata(
        {"id": "x", "originalFileName": "IMG_0001.HEIC", "title": "My vacation photo"}
    )

    assert metadata["original_filename"] == "IMG_0001.HEIC"
