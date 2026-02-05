"""
Celery task for periodic version checking.
"""
import asyncio

import httpx
from sqlalchemy.exc import OperationalError

from app.core.celery_app import celery_app
from app.core.config import VERSION_CHECK_ENABLED
from app.core.database import get_session_context
from app.core.logging_config import log_error, log_info, log_warning
from app.services.version_checker import VersionChecker


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    return asyncio.run(coro)


@celery_app.task(
    bind=True,
    autoretry_for=(
        httpx.RequestError,
        ConnectionError,
        TimeoutError,
        OperationalError,
    ),
    retry_kwargs={"max_retries": 5, "countdown": 60},
    retry_backoff=True,
)
def check_journiv_version(self):
    """Check for Journiv updates and persist the result."""
    if not VERSION_CHECK_ENABLED:
        log_info("Version check disabled; skipping task", task_id=self.request.id)
        return {"status": "skipped", "reason": "disabled"}

    log_info(
        "Version check task started by celery",
        task_id=self.request.id,
        attempt=self.request.retries + 1,
    )

    try:
        with get_session_context() as db:
            checker = VersionChecker(db)
            result = _run_async(checker.check_for_updates())
    except (httpx.RequestError, ConnectionError, TimeoutError, OperationalError) as exc:
        log_error(
            exc,
            task_id=self.request.id,
            retries=self.request.retries,
            context="check_journiv_version",
        )
        raise

    if result.get("success"):
        if result.get("update_available"):
            log_info(
                "Version check completed - update available",
                task_id=self.request.id,
                latest_version=result.get("latest_version"),
            )
        else:
            log_info("Version check completed - no updates", task_id=self.request.id)
    elif result.get("rate_limited"):
        log_warning(
            "Version check rate limited",
            task_id=self.request.id,
            retry_after_seconds=result.get("retry_after_seconds"),
        )
    else:
        log_warning(
            "Version check failed",
            task_id=self.request.id,
            error_message=result.get("error_message"),
        )

    if "checked_at" in result:
        log_info("Version check used cached metadata", task_id=self.request.id)
    else:
        log_info("Version check metadata updated", task_id=self.request.id)

    return result

