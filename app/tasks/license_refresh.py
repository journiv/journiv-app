"""
Celery task for periodic license refresh.
"""
import asyncio

from app.core.celery_app import celery_app
from app.core.database import get_session_context
from app.core.instance import get_instance_strict
from app.core.logging_config import log_debug, log_error, log_info, log_warning
from app.plus.plus_client import PlusServerClient
from app.services.license_service import LicenseService


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        # If we're already in an async context, we cannot use asyncio.run()
        # or create a new loop. This should not happen in Celery tasks.
        raise RuntimeError(
            "Cannot run async coroutine: an event loop is already running. "
            "This should not occur in Celery tasks."
        )


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
)
def refresh_license(self):
    """Refresh signed license and license info from Plus server."""
    log_info(
        "License refresh task started",
        task_id=self.request.id,
        attempt=self.request.retries + 1,
    )

    try:
        with get_session_context() as db:
            instance = get_instance_strict(db)

            if not instance.signed_license:
                log_debug(
                    "No signed license to refresh",
                    task_id=self.request.id,
                    install_id=instance.install_id
                )
                return {"status": "skipped", "reason": "no_license"}

            service = LicenseService(db)
            client = PlusServerClient(db)

            # Refresh signed license (critical - failures will trigger retry)
            refresh_result = _run_async(
                client.refresh_license(
                    signed_license=instance.signed_license,
                    install_id=instance.install_id
                )
            )

            new_signed_license = refresh_result.get("signed_license")
            if new_signed_license:
                instance.signed_license = new_signed_license
                db.commit()
                db.refresh(instance)

                log_info(
                    "Signed license refreshed successfully",
                    task_id=self.request.id,
                    install_id=instance.install_id
                )
            else:
                log_warning(
                    "Refresh returned no signed_license",
                    task_id=self.request.id,
                    install_id=instance.install_id
                )

            # Refresh license info (best-effort - failures are logged but don't trigger retry)
            try:
                info = _run_async(
                    service.get_license_info(refresh=True)
                )
                if info:
                    log_info(
                        "License info refreshed successfully",
                        task_id=self.request.id,
                        install_id=instance.install_id
                    )
            except Exception as e:
                log_error(
                    e,
                    task_id=self.request.id,
                    install_id=instance.install_id,
                    context="refresh_license_info"
                )
                # License info cache refresh is best-effort, continue on failure

        return {"status": "success", "task_id": self.request.id}

    except Exception as exc:
        log_error(
            exc,
            task_id=self.request.id,
            retries=self.request.retries,
            context="refresh_license",
        )
        raise

