"""
Celery tasks for media processing.
"""
import contextlib

from redis import Redis
from sqlmodel import Session

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import engine
from app.core.logging_config import log_error, log_info
from app.services.media_service import MediaService


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
        except Exception as exc:
            log_error(exc, media_id=media_id, user_id=user_id)
            raise
