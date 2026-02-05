"""
Celery tasks for Immich import jobs.
"""
import asyncio
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError
from uuid import UUID

from celery.signals import worker_process_init
from sqlmodel import Session

from app.core.celery_app import celery_app
from app.core.database import engine
from app.core.logging_config import log_error, log_info
from app.services.import_job_service import ImportJobService

_shared_loop: asyncio.AbstractEventLoop | None = None
_shared_loop_thread: threading.Thread | None = None
_shared_loop_lock = threading.Lock()


def _start_shared_loop() -> None:
    global _shared_loop, _shared_loop_thread
    with _shared_loop_lock:
        if _shared_loop and _shared_loop.is_running():
            return

        loop = asyncio.new_event_loop()
        started_event = threading.Event()

        def _run_loop() -> None:
            asyncio.set_event_loop(loop)
            started_event.set()
            loop.run_forever()

        thread = threading.Thread(target=_run_loop, name="immich-import-loop", daemon=True)
        thread.start()
        if not started_event.wait(timeout=1.0):
            error = RuntimeError("Immich import event loop did not start within timeout")
            log_error(error, message="Failed to start Immich import event loop")
            raise error
        if _shared_loop and _shared_loop.is_running():
            return
        _shared_loop = loop
        _shared_loop_thread = thread


@worker_process_init.connect
def _init_worker_loop(**_kwargs) -> None:
    _start_shared_loop()


def _get_shared_loop() -> asyncio.AbstractEventLoop:
    if _shared_loop is None or not _shared_loop.is_running():
        _start_shared_loop()
    assert _shared_loop is not None
    return _shared_loop


@celery_app.task(name="app.tasks.immich.process_link_only_import", bind=True)
def process_link_only_import(self, job_id: str):
    """Process link-only Immich import jobs in Celery."""
    job_uuid = UUID(job_id)
    async def _run_link_only_job() -> None:
        with Session(engine) as session:
            service = ImportJobService(session)
            await service.process_link_only_job_async(job_uuid)

    log_info("Processing Immich link-only import job", job_id=job_id)
    future = None
    try:
        future = asyncio.run_coroutine_threadsafe(
            _run_link_only_job(),
            _get_shared_loop()
        )
        future.result(timeout=300)
        log_info("Immich link-only import job completed", job_id=job_id)
    except FutureTimeoutError as exc:
        if future:
            future.cancel()
        log_error(exc, message="Immich link-only import job timed out", job_id=job_id)
        raise
    except Exception as exc:
        log_error(exc, job_id=job_id)
        raise


@celery_app.task(name="app.tasks.immich.process_copy_import", bind=True)
def process_copy_import(self, job_id: str):
    """Process copy-mode Immich import jobs in Celery."""
    job_uuid = UUID(job_id)
    async def _run_copy_job() -> None:
        with Session(engine) as session:
            service = ImportJobService(session)
            await service.process_copy_job_async(job_uuid)

    log_info("Processing Immich copy import job", job_id=job_id)
    future = None
    try:
        future = asyncio.run_coroutine_threadsafe(
            _run_copy_job(),
            _get_shared_loop()
        )
        future.result(timeout=300)
        log_info("Immich copy import job completed", job_id=job_id)
    except FutureTimeoutError as exc:
        if future:
            future.cancel()
        log_error(exc, message="Immich copy import job timed out", job_id=job_id)
        raise
    except Exception as exc:
        log_error(exc, job_id=job_id)
        raise


@celery_app.task(name="app.tasks.immich.repair_thumbnails", bind=True)
def repair_thumbnails(self, user_id: str, asset_ids: list[str]):
    """Repair Immich thumbnails in background."""
    user_uuid = UUID(user_id)
    with Session(engine) as session:
        service = ImportJobService(session)
        try:
            log_info("Repairing thumbnails for user", user_id=user_id)
            future = None
            try:
                future = asyncio.run_coroutine_threadsafe(
                    service.repair_thumbnails_async(user_uuid, asset_ids),
                    _get_shared_loop()
                )
                future.result(timeout=300)
                log_info("Thumbnail repair completed", user_id=user_id)
            except FutureTimeoutError as exc_timeout:
                if future:
                    future.cancel()
                log_error(exc_timeout, message="Thumbnail repair timed out", user_id=user_id)
                raise
        except Exception as exc:
            if isinstance(exc, FutureTimeoutError):
                raise
            log_error(exc, user_id=user_id)
            raise
