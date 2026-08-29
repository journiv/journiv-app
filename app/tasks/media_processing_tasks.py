"""
Celery tasks for media processing.
"""
import contextlib
import uuid

from celery.exceptions import MaxRetriesExceededError
from redis import Redis
from sqlmodel import Session

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import engine, get_session_context
from app.core.exceptions import MediaNotFoundError
from app.core.logging_config import log_error, log_info, log_warning
from app.services.media_service import MediaService

# The upload request commits the MomentMedia row, then enqueues this task. A worker
# with a separate DB connection (or a separate process sharing a SQLite file over a
# volume) can briefly fail to see that row. Retry with backoff before giving up so a
# transient visibility lag never leaves media silently stuck in PENDING.
_MEDIA_VISIBILITY_MAX_RETRIES = 8


@celery_app.task(name="app.tasks.media.process_media_upload", bind=True)
def process_media_upload(self, media_id: str, file_path: str, user_id: str):
    """Process uploaded media files asynchronously."""



    @contextlib.contextmanager
    def file_lock(lock_name):
        """Redis-backed distributed lock."""
        if not settings.redis_url:
            raise RuntimeError("Redis URL not configured - distributed locking unavailable")
        redis_client = Redis.from_url(str(settings.redis_url))
        try:
            lock = redis_client.lock(lock_name, timeout=300)

            log_info(f"Waiting for lock {lock_name}...", media_id=media_id, user_id=user_id)
            if lock.acquire(blocking=True, blocking_timeout=30):
                try:
                    log_info(f"Acquired lock {lock_name}", media_id=media_id, user_id=user_id)
                    yield
                finally:
                    try:
                        lock.release()
                    except Exception as e:
                        log_error(e, message="Failed to release lock", media_id=media_id)
            else:
                raise RuntimeError(f"Failed to acquire lock {lock_name} within timeout")
        finally:
            try:
                redis_client.close()
            except Exception as e:
                log_error(e, message="Failed to close Redis client", media_id=media_id)

    with Session(engine) as session:
        service = MediaService(session)
        try:
            # Use redis lock to prevent concurrent FFmpeg processes
            with file_lock(f"media-lock:{media_id}"):
                log_info("Processing uploaded media", media_id=media_id, user_id=user_id)
                service.process_uploaded_file(media_id, file_path, user_id)
                log_info("Processed uploaded media", media_id=media_id, user_id=user_id)
        except MediaNotFoundError as exc:
            # Row not visible to this worker yet — retry with capped exponential
            # backoff (1, 2, 4, 8, 16, 30, 30, 30s). Only after the row is still
            # missing minutes later do we give up and record a hard failure so the
            # client can surface it, instead of an eternal PENDING.
            retries = self.request.retries
            countdown = min(2 ** retries, 30)
            log_warning(
                f"Media {media_id} not visible yet (attempt {retries + 1}), "
                f"retrying in {countdown}s",
                media_id=media_id, user_id=user_id,
            )
            try:
                raise self.retry(
                    exc=exc,
                    countdown=countdown,
                    max_retries=_MEDIA_VISIBILITY_MAX_RETRIES,
                ) from exc
            except MaxRetriesExceededError:
                log_error(
                    f"Media {media_id} never became visible after "
                    f"{_MEDIA_VISIBILITY_MAX_RETRIES} retries; marking failed",
                    media_id=media_id, user_id=user_id,
                )
                try:
                    service._mark_processing_failed(
                        media_id,
                        "Media processing could not start: the upload record was "
                        "not found. Please try attaching the file again.",
                    )
                except Exception as mark_exc:
                    log_error(mark_exc, media_id=media_id, user_id=user_id)
                return
        except Exception as exc:
            log_error(exc, media_id=media_id, user_id=user_id)
            raise


@celery_app.task(name="app.tasks.media.cleanup_moment_media_files", bind=True)
def cleanup_moment_media_files(
    self,
    user_id: str,
    media_files: list[dict] | None = None,
    immich_assets: list[str] | None = None,
):
    """Delete orphaned files and remove assets from external album after moment deletion."""
    media_files = media_files or []
    immich_assets = [asset_id for asset_id in (immich_assets or []) if asset_id]
    if not media_files and not immich_assets:
        return

    try:
        user_uuid = uuid.UUID(user_id)
    except Exception:
        log_warning(f"Invalid user_id for cleanup task: {user_id}")
        return

    with get_session_context() as session:
        media_service = MediaService(session)
        try:
            media_service.delete_media_files_post_commit(user_uuid, media_files, immich_assets)
        except Exception as exc:
            log_warning(f"Failed to run media cleanup task: {exc}")
