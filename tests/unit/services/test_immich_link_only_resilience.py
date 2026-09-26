"""
Regression tests: link-only failures were permanent and too strict.

`process_link_only_job_async` used to mark a placeholder FAILED whenever
`get_asset_info` returned `{}` — which happened for a timeout or a 5xx with
no retry, even though the asset is still viewable through the proxy. Now
`get_asset_info` itself retries transient failures and only signals a
confirmed absence (404 from both lookups) via `ImmichAssetNotFoundError`;
the job processor fails the row only for that, and otherwise leaves an
already-COMPLETED placeholder exactly as it is.
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
async def test_transient_metadata_failure_keeps_placeholder_completed():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id)
    job = _create_import_job(session, user.id, moment.id, ["a1"])
    _create_placeholder(session, moment.id, "a1")

    async def fake_get_asset_info(base_url, api_key, asset_id):
        return {}  # get_asset_info's own retries already exhausted

    with patch("app.core.database.engine", session.get_bind()), \
         patch("app.integrations.immich.get_asset_info", side_effect=fake_get_asset_info):
        await ImportJobService(session).process_link_only_job_async(job.id)

    session.expire_all()
    refreshed_job = session.get(ImportJob, job.id)
    media = session.exec(
        select(MomentMedia).where(MomentMedia.external_asset_id == "a1")
    ).first()

    # Not failed: the asset is still viewable through the proxy.
    assert media.upload_status == UploadStatus.COMPLETED
    assert media.processing_error is None
    assert refreshed_job.status == JobStatus.COMPLETED
    assert refreshed_job.failed_items == 0


@pytest.mark.asyncio
async def test_confirmed_404_fails_the_placeholder():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id)
    job = _create_import_job(session, user.id, moment.id, ["a1"])
    _create_placeholder(session, moment.id, "a1")

    async def fake_get_asset_info(base_url, api_key, asset_id):
        raise immich.ImmichAssetNotFoundError(asset_id)

    with patch("app.core.database.engine", session.get_bind()), \
         patch("app.integrations.immich.get_asset_info", side_effect=fake_get_asset_info):
        await ImportJobService(session).process_link_only_job_async(job.id)

    session.expire_all()
    refreshed_job = session.get(ImportJob, job.id)
    media = session.exec(
        select(MomentMedia).where(MomentMedia.external_asset_id == "a1")
    ).first()

    assert media.upload_status == UploadStatus.FAILED
    assert media.processing_error is not None
    assert refreshed_job.failed_items == 1


@pytest.mark.asyncio
async def test_mixed_transient_and_confirmed_404_in_one_job():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id)
    job = _create_import_job(session, user.id, moment.id, ["ok", "gone"])
    _create_placeholder(session, moment.id, "ok")
    _create_placeholder(session, moment.id, "gone")

    async def fake_get_asset_info(base_url, api_key, asset_id):
        if asset_id == "gone":
            raise immich.ImmichAssetNotFoundError(asset_id)
        return {}

    with patch("app.core.database.engine", session.get_bind()), \
         patch("app.integrations.immich.get_asset_info", side_effect=fake_get_asset_info):
        await ImportJobService(session).process_link_only_job_async(job.id)

    session.expire_all()
    ok_media = session.exec(
        select(MomentMedia).where(MomentMedia.external_asset_id == "ok")
    ).first()
    gone_media = session.exec(
        select(MomentMedia).where(MomentMedia.external_asset_id == "gone")
    ).first()

    assert ok_media.upload_status == UploadStatus.COMPLETED
    assert gone_media.upload_status == UploadStatus.FAILED

    refreshed_job = session.get(ImportJob, job.id)
    assert refreshed_job.status == JobStatus.PARTIAL
    assert refreshed_job.processed_items == 1
    assert refreshed_job.failed_items == 1
