"""
Regression tests for stale Immich import job dedupe (issue #367).

`get_active_immich_job_for_assets` used to return any PENDING/RUNNING job for
the same asset set with no age limit, so a job whose worker crashed (or was
cancelled after the Celery hard timeout, which used to inject an uncaught
`asyncio.CancelledError`) blocked re-importing forever: the user deletes the
stuck placeholder and re-adds the photo, and the endpoint returns the old
job with zero media. These tests cover: a stale job being ignored (and
marked failed), a reused active job still recreating a missing placeholder,
`create_and_process_job_async` reporting whether it created a new job (so
the caller does not dispatch Celery twice for a reused job), and a
cancelled/timed-out job ending FAILED with its still-processing placeholders
FAILED without disturbing placeholders that already reached a real outcome.
"""
import asyncio
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app.core.encryption import encrypt_token
from app.core.time_utils import utc_now
from app.models.base import BaseModel
from app.models.enums import ImportSourceType, JobStatus, MediaType, UploadStatus
from app.models.import_job import ImportJob
from app.models.integration import ImportMode, Integration, IntegrationProvider
from app.models.moment import Moment, MomentMedia
from app.models.user import User
from app.services.import_job_service import (
    IMMICH_JOB_STALE_MARGIN_SECONDS,
    IMMICH_LINK_JOB_TIMEOUT_SECONDS,
    IMMICH_PENDING_JOB_STALE_SECONDS,
    ImportJobService,
    immich_copy_job_timeout_seconds,
)


def _setup_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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


def _create_integration(session: Session, user_id: uuid.UUID, import_mode: ImportMode) -> Integration:
    integration = Integration(
        user_id=user_id,
        provider=IntegrationProvider.IMMICH,
        base_url="http://immich.test",
        access_token_encrypted=encrypt_token("fake-api-key"),
        external_user_id="immich-user-1",
        is_active=True,
        import_mode=import_mode,
    )
    session.add(integration)
    session.commit()
    session.refresh(integration)
    return integration


def _create_import_job(
    session: Session,
    user_id: uuid.UUID,
    moment_id: uuid.UUID,
    asset_ids: list[str],
    status: JobStatus = JobStatus.PENDING,
    created_at=None,
) -> ImportJob:
    job = ImportJob(
        user_id=user_id,
        moment_id=moment_id,
        source_type=ImportSourceType.IMMICH,
        status=status,
        result_data={"asset_ids": asset_ids},
        total_items=len(asset_ids),
    )
    if created_at is not None:
        job.created_at = created_at
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _create_placeholder(
    session: Session,
    moment_id: uuid.UUID,
    asset_id: str,
    status: UploadStatus = UploadStatus.PROCESSING,
) -> MomentMedia:
    media = MomentMedia(
        moment_id=moment_id,
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=status,
        external_provider="immich",
        external_asset_id=asset_id,
    )
    session.add(media)
    session.commit()
    session.refresh(media)
    return media


def test_stale_active_job_is_ignored_and_marked_failed():
    """A PENDING job far older than its Celery timeout + margin is stale."""
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)

    stale_bound = immich_copy_job_timeout_seconds(1) + IMMICH_JOB_STALE_MARGIN_SECONDS
    old_job = _create_import_job(
        session, user.id, moment.id, ["a1"],
        status=JobStatus.RUNNING,
        created_at=utc_now() - timedelta(seconds=stale_bound + 60),
    )

    service = ImportJobService(session)
    result = service.get_active_immich_job_for_assets(user.id, moment.id, ["a1"])

    assert result is None
    session.refresh(old_job)
    assert old_job.status == JobStatus.FAILED


def test_recent_active_job_is_returned_as_active():
    """A job well within its timeout window is still treated as active."""
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)

    job = _create_import_job(session, user.id, moment.id, ["a1"], status=JobStatus.PENDING)

    service = ImportJobService(session)
    result = service.get_active_immich_job_for_assets(user.id, moment.id, ["a1"])

    assert result is not None
    assert result.id == job.id
    assert result.status == JobStatus.PENDING


def test_queued_job_does_not_use_the_running_timeout():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    job = _create_import_job(
        session, user.id, moment.id, ["a1"], status=JobStatus.PENDING,
        created_at=utc_now() - timedelta(minutes=10),
    )

    result = ImportJobService(session).get_active_immich_job_for_assets(
        user.id, moment.id, ["a1"]
    )

    assert result is not None and result.id == job.id
    assert result.status == JobStatus.PENDING


def test_running_timeout_starts_when_worker_starts():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    job = _create_import_job(
        session, user.id, moment.id, ["a1"], status=JobStatus.RUNNING,
        created_at=utc_now() - timedelta(hours=1),
    )
    job.started_at = utc_now() - timedelta(seconds=10)
    session.add(job)
    session.commit()

    result = ImportJobService(session).get_active_immich_job_for_assets(
        user.id, moment.id, ["a1"]
    )

    assert result is not None and result.id == job.id


@pytest.mark.parametrize(
    ("import_mode", "is_stale"),
    [
        (ImportMode.LINK_ONLY, True),
        (ImportMode.COPY, False),
        (None, False),  # Existing jobs without recorded mode keep the copy timeout.
    ],
)
def test_running_job_timeout_uses_import_mode(import_mode, is_stale):
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    asset_ids = [f"a{i}" for i in range(20)]
    job = _create_import_job(
        session, user.id, moment.id, asset_ids, status=JobStatus.RUNNING
    )
    if import_mode is not None:
        job.result_data = {"asset_ids": asset_ids, "import_mode": import_mode.value}
    job.started_at = utc_now() - timedelta(
        seconds=IMMICH_LINK_JOB_TIMEOUT_SECONDS + IMMICH_JOB_STALE_MARGIN_SECONDS + 30
    )
    session.add(job)
    session.commit()

    result = ImportJobService(session).get_active_immich_job_for_assets(
        user.id, moment.id, asset_ids
    )

    assert (result is None) is is_stale
    session.refresh(job)
    assert job.status == (JobStatus.FAILED if is_stale else JobStatus.RUNNING)


def test_dropped_pending_job_eventually_expires():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    job = _create_import_job(
        session, user.id, moment.id, ["a1"], status=JobStatus.PENDING,
        created_at=utc_now() - timedelta(seconds=IMMICH_PENDING_JOB_STALE_SECONDS + 60),
    )

    result = ImportJobService(session).get_active_immich_job_for_assets(
        user.id, moment.id, ["a1"]
    )

    assert result is None
    session.refresh(job)
    assert job.status == JobStatus.FAILED


@pytest.mark.asyncio
async def test_reused_job_recreates_missing_placeholder_and_reports_not_created():
    """
    Deleting the placeholder for an asset with a still-active job (the
    exact repro from the bug report) must not leave the asset with zero
    media on re-import, and must not double-dispatch Celery.
    """
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id, ImportMode.COPY)
    existing_job = _create_import_job(session, user.id, moment.id, ["a1"], status=JobStatus.PENDING)

    # No MomentMedia row exists for "a1" - simulates the user deleting it
    # while the job was stuck.
    assert session.exec(select(MomentMedia)).all() == []

    with patch("app.core.database.engine", session.get_bind()):
        job, created = await ImportJobService(session).create_and_process_job_async(
            user_id=user.id, moment_id=moment.id, asset_ids=["a1"]
        )

    assert created is False
    assert job.id == existing_job.id

    placeholders = session.exec(
        select(MomentMedia).where(MomentMedia.external_asset_id == "a1")
    ).all()
    assert len(placeholders) == 1
    assert placeholders[0].upload_status == UploadStatus.PROCESSING


@pytest.mark.asyncio
async def test_reused_job_leaves_rows_it_already_owns_untouched():
    """
    A repeat request while a copy job is running (a double submit, or the
    editor's Retry re-importing) must not push an asset the job already
    downloaded back to PROCESSING: the job never revisits it, so it would be
    stuck processing forever.
    """
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id, ImportMode.COPY)
    existing_job = _create_import_job(
        session, user.id, moment.id, ["done", "busy"], status=JobStatus.RUNNING
    )
    done = _create_placeholder(session, moment.id, "done", status=UploadStatus.COMPLETED)
    busy = _create_placeholder(session, moment.id, "busy", status=UploadStatus.PROCESSING)

    with patch("app.core.database.engine", session.get_bind()):
        job, created = await ImportJobService(session).create_and_process_job_async(
            user_id=user.id, moment_id=moment.id, asset_ids=["done", "busy"]
        )

    assert created is False
    assert job.id == existing_job.id
    session.expire_all()
    assert session.get(MomentMedia, done.id).upload_status == UploadStatus.COMPLETED
    assert session.get(MomentMedia, busy.id).upload_status == UploadStatus.PROCESSING
    assert len(session.exec(select(MomentMedia)).all()) == 2


@pytest.mark.asyncio
async def test_deleted_asset_already_finished_by_active_job_gets_new_job():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id, ImportMode.COPY)
    original_job = _create_import_job(
        session, user.id, moment.id, ["done", "busy"], status=JobStatus.RUNNING
    )
    original_job.result_data = {
        "asset_ids": ["done", "busy"], "finished_asset_ids": ["done"]
    }
    original_job.processed_items = 1
    session.add(original_job)
    session.commit()
    _create_placeholder(session, moment.id, "busy")

    with patch("app.core.database.engine", session.get_bind()):
        retry_job, created = await ImportJobService(session).create_and_process_job_async(
            user_id=user.id, moment_id=moment.id, asset_ids=["done", "busy"]
        )
        reused_job, created_again = await ImportJobService(session).create_and_process_job_async(
            user_id=user.id, moment_id=moment.id, asset_ids=["done", "busy"]
        )

    assert created is True
    assert created_again is False
    assert retry_job.id == reused_job.id
    assert retry_job.id != original_job.id
    assert retry_job.result_data["asset_ids"] == ["done"]
    assert retry_job.result_data["import_mode"] == ImportMode.COPY.value
    assert len(session.exec(select(ImportJob)).all()) == 2
    rows = session.exec(select(MomentMedia)).all()
    assert {row.external_asset_id for row in rows} == {"done", "busy"}


@pytest.mark.asyncio
async def test_copy_batch_records_finished_asset_ids():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    integration = _create_integration(session, user.id, ImportMode.COPY)
    job = _create_import_job(session, user.id, moment.id, ["a1", "a2"], status=JobStatus.RUNNING)
    release_slow_asset = asyncio.Event()

    async def download_asset(self, *, asset_id, **_kwargs):
        if asset_id == "a2":
            await release_slow_asset.wait()
            return None
        return {"id": asset_id}

    with patch("app.core.database.engine", session.get_bind()), patch.object(
        ImportJobService, "_download_and_save_original",
        new=download_asset,
    ):
        processing = asyncio.create_task(
            ImportJobService(session)._process_original_phase(
                job=job, asset_ids=["a1", "a2"], base_url="http://immich.test",
                api_key="key", integration=integration, session=session,
                thumbnail_cache={},
            )
        )
        try:
            for _ in range(50):
                session.refresh(job)
                if job.processed_items == 1:
                    break
                await asyncio.sleep(0)
            assert job.processed_items == 1
            assert job.result_data["finished_asset_ids"] == ["a1"]
        finally:
            release_slow_asset.set()
            await processing

    session.refresh(job)
    assert job.result_data["finished_asset_ids"] == ["a1", "a2"]
    assert job.processed_items == 1
    assert job.failed_items == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("import_mode", [ImportMode.COPY, ImportMode.LINK_ONLY])
async def test_create_and_process_job_async_creates_new_job_when_none_active(import_mode):
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id, import_mode)

    with patch("app.core.database.engine", session.get_bind()):
        job, created = await ImportJobService(session).create_and_process_job_async(
            user_id=user.id, moment_id=moment.id, asset_ids=["a1"]
        )

    assert created is True
    assert job.status == JobStatus.PENDING
    assert job.result_data["import_mode"] == import_mode.value


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["copy", "link_only"])
@pytest.mark.parametrize("status", [JobStatus.RUNNING, JobStatus.COMPLETED, JobStatus.FAILED])
async def test_redelivered_immich_job_does_not_restart(mode, status):
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    job = _create_import_job(session, user.id, moment.id, ["a1"], status=status)
    job.started_at = utc_now()
    job.progress = 37
    session.add(job)
    session.commit()

    with (
        patch("app.core.database.engine", session.get_bind()),
        patch.object(ImportJobService, "_process_thumbnail_phase", new_callable=AsyncMock) as thumbnails,
        patch("app.integrations.immich.get_asset_info", new_callable=AsyncMock) as asset_info,
    ):
        service = ImportJobService(session)
        if mode == "copy":
            await service.process_copy_job_async(job.id)
        else:
            await service.process_link_only_job_async(job.id)

    session.refresh(job)
    assert job.status == status
    assert job.progress == 37
    assert job.started_at is not None
    thumbnails.assert_not_awaited()
    asset_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_copy_job_cancellation_marks_job_and_placeholders_failed():
    """
    future.cancel() after the Celery hard timeout injects CancelledError.
    The job must end FAILED (not stuck RUNNING forever) with its
    still-processing placeholders FAILED.
    """
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id, ImportMode.COPY)
    job = _create_import_job(session, user.id, moment.id, ["a1", "a2"], status=JobStatus.PENDING)
    _create_placeholder(session, moment.id, "a1", UploadStatus.PROCESSING)
    _create_placeholder(session, moment.id, "a2", UploadStatus.PROCESSING)

    with patch("app.core.database.engine", session.get_bind()), \
         patch.object(
             ImportJobService, "_process_thumbnail_phase",
             new=AsyncMock(side_effect=asyncio.CancelledError()),
         ):
        with pytest.raises(asyncio.CancelledError):
            await ImportJobService(session).process_copy_job_async(job.id)

    session.expire_all()
    refreshed_job = session.get(ImportJob, job.id)
    assert refreshed_job.status == JobStatus.FAILED

    media = session.exec(
        select(MomentMedia).where(MomentMedia.moment_id == moment.id)
    ).all()
    assert len(media) == 2
    assert all(m.upload_status == UploadStatus.FAILED for m in media)


@pytest.mark.asyncio
async def test_link_only_job_cancellation_preserves_already_completed_asset():
    """
    Cancellation mid-loop must fail only the still-processing placeholder,
    not one that already finished earlier in the same loop.
    """
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id, ImportMode.LINK_ONLY)
    job = _create_import_job(session, user.id, moment.id, ["a1", "a2"], status=JobStatus.PENDING)
    _create_placeholder(session, moment.id, "a1", UploadStatus.PROCESSING)
    _create_placeholder(session, moment.id, "a2", UploadStatus.PROCESSING)

    asset_info = AsyncMock(side_effect=[
        {"id": "a1", "type": "IMAGE", "originalFileName": "a1.jpg", "mimeType": "image/jpeg"},
        asyncio.CancelledError(),
    ])

    with patch("app.core.database.engine", session.get_bind()), \
         patch("app.integrations.immich.get_asset_info", asset_info):
        with pytest.raises(asyncio.CancelledError):
            await ImportJobService(session).process_link_only_job_async(job.id)

    session.expire_all()
    refreshed_job = session.get(ImportJob, job.id)
    assert refreshed_job.status == JobStatus.FAILED

    a1 = session.exec(
        select(MomentMedia).where(MomentMedia.external_asset_id == "a1")
    ).first()
    a2 = session.exec(
        select(MomentMedia).where(MomentMedia.external_asset_id == "a2")
    ).first()
    assert a1.upload_status == UploadStatus.COMPLETED
    assert a2.upload_status == UploadStatus.FAILED


@pytest.mark.asyncio
async def test_copy_job_level_failure_does_not_leave_placeholders_processing():
    """
    A job-level failure before per-asset processing starts (for example the
    integration was deactivated between request and worker pickup) must not
    leave placeholders stuck PROCESSING forever.
    """
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    integration = _create_integration(session, user.id, ImportMode.COPY)
    integration.is_active = False
    session.add(integration)
    session.commit()

    job = _create_import_job(session, user.id, moment.id, ["a1"], status=JobStatus.PENDING)
    _create_placeholder(session, moment.id, "a1", UploadStatus.PROCESSING)

    with patch("app.core.database.engine", session.get_bind()):
        await ImportJobService(session).process_copy_job_async(job.id)

    session.expire_all()
    refreshed_job = session.get(ImportJob, job.id)
    assert refreshed_job.status == JobStatus.FAILED

    media = session.exec(
        select(MomentMedia).where(MomentMedia.external_asset_id == "a1")
    ).first()
    assert media.upload_status == UploadStatus.FAILED


def test_copy_job_timeout_scales_but_stays_under_celery_soft_limit():
    """A large batch gets more time, but never enough that Celery's soft time
    limit interrupts the task before the job's own timeout and cleanup run."""
    from app.core.celery_app import TASK_SOFT_TIME_LIMIT_SECONDS

    assert immich_copy_job_timeout_seconds(1) == 300
    assert immich_copy_job_timeout_seconds(20) == 1200
    assert immich_copy_job_timeout_seconds(100) < TASK_SOFT_TIME_LIMIT_SECONDS


def test_concurrent_requests_create_only_one_job(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'immich-jobs.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    BaseModel.metadata.create_all(engine)
    with Session(engine) as seed_session:
        user = _create_user(seed_session)
        moment = _create_moment(seed_session, user.id)
        _create_integration(seed_session, user.id, ImportMode.COPY)
        user_id, moment_id = user.id, moment.id

    first_inside = threading.Event()
    second_at_lock = threading.Event()
    release_first = threading.Event()
    gate = threading.Lock()
    first_call = True
    lock_calls = 0
    original_ensure = ImportJobService._ensure_placeholders
    original_lock = ImportJobService._lock_moment_for_job_creation

    def record_lock_attempt(self, session, moment_id, user_id):
        nonlocal lock_calls
        with gate:
            lock_calls += 1
            if lock_calls == 2:
                second_at_lock.set()
        return original_lock(session, moment_id, user_id)

    def pause_first_creation(self, *args, **kwargs):
        nonlocal first_call
        with gate:
            should_pause = first_call
            first_call = False
        if should_pause:
            first_inside.set()
            assert release_first.wait(timeout=5)
        return original_ensure(self, *args, **kwargs)

    def create_request():
        with Session(engine) as request_session:
            return asyncio.run(
                ImportJobService(request_session).create_and_process_job_async(
                    user_id=user_id, moment_id=moment_id, asset_ids=["a1"]
                )
            )

    with patch("app.core.database.engine", engine), patch.object(
        ImportJobService, "_ensure_placeholders", pause_first_creation
    ), patch.object(
        ImportJobService, "_lock_moment_for_job_creation", record_lock_attempt
    ), ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(create_request)
        assert first_inside.wait(timeout=5)
        second = pool.submit(create_request)
        assert second_at_lock.wait(timeout=5)
        release_first.set()
        first_job, first_created = first.result(timeout=10)
        second_job, second_created = second.result(timeout=10)

    assert first_job.id == second_job.id
    assert [first_created, second_created] == [True, False]
    with Session(engine) as check_session:
        assert len(check_session.exec(select(ImportJob)).all()) == 1
        assert len(check_session.exec(select(MomentMedia)).all()) == 1


@pytest.mark.asyncio
async def test_reimport_after_dropped_pending_job_creates_new_dispatchable_job():
    """A PENDING job whose task was lost must not swallow a re-import."""
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id, ImportMode.COPY)
    dropped = _create_import_job(
        session, user.id, moment.id, ["a1"], status=JobStatus.PENDING,
        created_at=utc_now() - timedelta(seconds=IMMICH_PENDING_JOB_STALE_SECONDS + 60),
    )
    _create_placeholder(session, moment.id, "a1", UploadStatus.PROCESSING)

    with patch("app.core.database.engine", session.get_bind()):
        job, created = await ImportJobService(session).create_and_process_job_async(
            user_id=user.id, moment_id=moment.id, asset_ids=["a1"]
        )

    assert created is True
    assert job.id != dropped.id
    session.expire_all()
    assert session.get(ImportJob, dropped.id).status == JobStatus.FAILED
    assert session.get(ImportJob, job.id).status == JobStatus.PENDING


@pytest.mark.asyncio
async def test_link_only_batch_records_finished_asset_ids():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    _create_integration(session, user.id, ImportMode.LINK_ONLY)
    job = _create_import_job(session, user.id, moment.id, ["a1", "a2"], status=JobStatus.PENDING)
    _create_placeholder(session, moment.id, "a1", UploadStatus.COMPLETED)
    _create_placeholder(session, moment.id, "a2", UploadStatus.COMPLETED)

    async def asset_info(base_url, api_key, asset_id):
        return {"id": asset_id, "type": "IMAGE", "originalFileName": f"{asset_id}.jpg",
                "mimeType": "image/jpeg"}

    with patch("app.core.database.engine", session.get_bind()), \
         patch("app.integrations.immich.get_asset_info", side_effect=asset_info), \
         patch("app.core.celery_app.celery_app"):
        await ImportJobService(session).process_link_only_job_async(job.id)

    session.expire_all()
    assert session.get(ImportJob, job.id).result_data["finished_asset_ids"] == ["a1", "a2"]


@pytest.mark.asyncio
async def test_job_creation_for_missing_moment_raises_value_error():
    session = _setup_session()
    user = _create_user(session)
    _create_integration(session, user.id, ImportMode.COPY)

    with patch("app.core.database.engine", session.get_bind()):
        with pytest.raises(ValueError, match="Moment not found"):
            await ImportJobService(session).create_and_process_job_async(
                user_id=user.id, moment_id=uuid.uuid4(), asset_ids=["a1"]
            )
