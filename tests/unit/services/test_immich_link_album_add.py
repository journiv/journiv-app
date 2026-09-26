"""
Regression test: the Immich "Journiv" album is never updated on import.

`_upsert_entry_media`'s album-add trigger only fires for a newly-INSERTED
MomentMedia row committed in the same call. The link-only import flow never
hits it: `create_and_process_job_async` creates the placeholder row first
(commit=False), so by the time `process_link_only_job_async` calls
`_upsert_entry_media` for that asset, the row already exists and the update
branch returns before the album-add code. `process_link_only_job_async` now
sends `add_assets_to_album_task` itself, once per job, for exactly the
assets that finished processing (not the failed ones).
"""
import uuid
from unittest.mock import patch

import pytest
from sqlmodel import Session, create_engine, select

from app.core.encryption import encrypt_token
from app.integrations import immich
from app.models.base import BaseModel
from app.models.enums import ImportSourceType, JobStatus, MediaType, UploadStatus
from app.models.import_job import ImportJob
from app.models.integration import ImportMode, Integration, IntegrationProvider
from app.models.moment import Moment, MomentMedia
from app.models.user import User
from app.services.import_job_service import ImportJobService


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


def _create_integration(session: Session, user_id: uuid.UUID) -> Integration:
    integration = Integration(
        user_id=user_id,
        provider=IntegrationProvider.IMMICH,
        base_url="http://immich.test",
        access_token_encrypted=encrypt_token("fake-api-key"),
        external_user_id="immich-user-1",
        is_active=True,
        import_mode=ImportMode.LINK_ONLY,
    )
    session.add(integration)
    session.commit()
    session.refresh(integration)
    return integration


def _create_import_job(session: Session, user_id: uuid.UUID, moment_id: uuid.UUID, asset_ids: list[str]) -> ImportJob:
    job = ImportJob(
        user_id=user_id,
        moment_id=moment_id,
        source_type=ImportSourceType.IMMICH,
        status=JobStatus.PENDING,
        result_data={"asset_ids": asset_ids},
        total_items=len(asset_ids),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _create_placeholder(session: Session, moment_id: uuid.UUID, asset_id: str) -> MomentMedia:
    media = MomentMedia(
        moment_id=moment_id,
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
        external_provider="immich",
        external_asset_id=asset_id,
    )
    session.add(media)
    session.commit()
    session.refresh(media)
    return media


@pytest.mark.asyncio
async def test_link_only_job_sends_one_album_add_with_processed_assets_only():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id)
    job = _create_import_job(session, user.id, moment.id, ["a1", "a2"])
    # Placeholders already exist (created with commit=False by
    # create_and_process_job_async before the job was dispatched), so
    # _upsert_entry_media hits its "update existing row" branch.
    _create_placeholder(session, moment.id, "a1")
    _create_placeholder(session, moment.id, "a2")

    asset_info_by_id = {
        "a1": {"id": "a1", "type": "IMAGE", "originalFileName": "a1.jpg", "mimeType": "image/jpeg"},
    }

    async def fake_get_asset_info(base_url, api_key, asset_id):
        if asset_id not in asset_info_by_id:
            # Confirmed gone (not a transient failure) -> failed, not added
            # to the album.
            raise immich.ImmichAssetNotFoundError(asset_id)
        return asset_info_by_id[asset_id]

    with patch("app.core.database.engine", session.get_bind()), \
         patch("app.integrations.immich.get_asset_info", side_effect=fake_get_asset_info), \
         patch("app.core.celery_app.celery_app") as mock_celery:
        await ImportJobService(session).process_link_only_job_async(job.id)

    mock_celery.send_task.assert_called_once()
    call_args = mock_celery.send_task.call_args
    assert call_args[0][0] == "app.integrations.tasks.add_assets_to_album_task"
    task_args = call_args[1]["args"]
    assert task_args[0] == str(user.id)
    assert task_args[1] == "immich"
    assert task_args[2] == ["a1"]

    session.expire_all()
    a1 = session.exec(select(MomentMedia).where(MomentMedia.external_asset_id == "a1")).first()
    a2 = session.exec(select(MomentMedia).where(MomentMedia.external_asset_id == "a2")).first()
    assert a1.upload_status == UploadStatus.COMPLETED
    assert a2.upload_status == UploadStatus.FAILED


@pytest.mark.asyncio
async def test_link_only_job_skips_album_add_when_nothing_processed():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id)
    job = _create_import_job(session, user.id, moment.id, ["a1"])
    _create_placeholder(session, moment.id, "a1")

    async def fake_get_asset_info(base_url, api_key, asset_id):
        raise immich.ImmichAssetNotFoundError(asset_id)

    with patch("app.core.database.engine", session.get_bind()), \
         patch("app.integrations.immich.get_asset_info", side_effect=fake_get_asset_info), \
         patch("app.core.celery_app.celery_app") as mock_celery:
        await ImportJobService(session).process_link_only_job_async(job.id)

    mock_celery.send_task.assert_not_called()
