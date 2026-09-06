import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import Request
from sqlmodel import Session, create_engine

from app.api.v1.endpoints.export_data import cancel_export_job
from app.api.v1.endpoints.import_data import cancel_import_job
from app.models.base import BaseModel
from app.models.enums import ExportType, ImportSourceType, JobStatus
from app.models.export_job import ExportJob
from app.models.import_job import ImportJob
from app.models.user import User
from app.tasks.export_tasks import process_export_job
from app.tasks.import_tasks import process_import_job
from app.utils.import_export.cancellation import (
    JobCancelledError,
    raise_if_cancelled,
)
from app.utils.import_export.zip_handler import ZipHandler


def test_raise_if_cancelled_detects_cancelled_job() -> None:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)

    with Session(engine) as db:
        running = ExportJob(
            user_id=uuid.uuid4(),
            export_type=ExportType.FULL,
            status=JobStatus.RUNNING,
        )
        cancelled = ExportJob(
            user_id=uuid.uuid4(),
            export_type=ExportType.FULL,
            status=JobStatus.CANCELLED,
        )
        db.add(running)
        db.add(cancelled)
        db.commit()

        raise_if_cancelled(db, ExportJob, running.id)
        with pytest.raises(JobCancelledError):
            raise_if_cancelled(db, ExportJob, cancelled.id)


@pytest.mark.asyncio
async def test_cancel_export_endpoint_marks_pending_job_cancelled() -> None:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)

    with Session(engine) as db:
        user = User(
            email="cancel-export@example.com",
            password="hashed-password",
            name="Cancel Export",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        job = ExportJob(user_id=user.id, export_type=ExportType.FULL)
        db.add(job)
        db.commit()

        response = await cancel_export_job(
            job.id,
            MagicMock(spec=Request),
            user,
            db,
        )

        assert response.status == JobStatus.CANCELLED
        assert response.completed_at is not None
        assert db.get(ExportJob, job.id).status == JobStatus.CANCELLED


def test_cancel_import_endpoint_marks_pending_job_cancelled() -> None:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)

    with Session(engine) as db:
        user = User(
            email="cancel-import@example.com",
            password="hashed-password",
            name="Cancel Import",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        job = ImportJob(
            user_id=user.id,
            source_type=ImportSourceType.JOURNIV,
        )
        db.add(job)
        db.commit()

        response = cancel_import_job(
            job.id,
            MagicMock(spec=Request),
            user,
            db,
        )

        assert response.status == JobStatus.CANCELLED
        assert response.completed_at is not None
        assert db.get(ImportJob, job.id).status == JobStatus.CANCELLED


@pytest.mark.parametrize("model_cls", [ExportJob, ImportJob])
def test_mark_completed_and_failed_never_override_cancelled(model_cls) -> None:
    """A cancellation that lands while the worker is finishing must stick."""
    kwargs = (
        {"export_type": ExportType.FULL}
        if model_cls is ExportJob
        else {"source_type": ImportSourceType.JOURNIV}
    )
    job = model_cls(user_id=uuid.uuid4(), status=JobStatus.CANCELLED, **kwargs)

    if model_cls is ExportJob:
        job.mark_completed(file_path="x.zip", file_size=1, result_data={})
    else:
        job.mark_completed(result_data={})
    assert job.status == JobStatus.CANCELLED

    job.mark_failed("boom")
    assert job.status == JobStatus.CANCELLED
    assert job.errors is None


def test_create_export_zip_propagates_cancellation_and_drops_partial(
    tmp_path: Path,
) -> None:
    media_source = tmp_path / "photo.jpg"
    media_source.write_bytes(b"binary")
    output_path = tmp_path / "export.zip"

    def cancel_now() -> None:
        raise JobCancelledError()

    with pytest.raises(JobCancelledError):
        ZipHandler.create_export_zip(
            output_path=output_path,
            data={"hello": "world"},
            media_files={"m/photo.jpg": media_source},
            cancellation_check=cancel_now,
        )

    # Not surfaced as an IOError, and no half-written archive is left behind.
    assert not output_path.exists()


def test_export_worker_exits_when_job_was_cancelled_while_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    with Session(engine) as db:
        job = ExportJob(
            user_id=uuid.uuid4(),
            export_type=ExportType.FULL,
            status=JobStatus.CANCELLED,
        )
        db.add(job)
        db.commit()
        job_id = str(job.id)

    monkeypatch.setattr("app.tasks.export_tasks.engine", engine)
    assert process_export_job.run(job_id) == {"status": "cancelled"}


def test_import_worker_exits_when_job_was_cancelled_while_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    with Session(engine) as db:
        job = ImportJob(
            user_id=uuid.uuid4(),
            source_type=ImportSourceType.JOURNIV,
            status=JobStatus.CANCELLED,
        )
        db.add(job)
        db.commit()
        job_id = str(job.id)

    monkeypatch.setattr("app.tasks.import_tasks.engine", engine)
    assert process_import_job.run(job_id) == {"status": "cancelled"}
