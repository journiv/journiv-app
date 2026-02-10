"""
Celery application configuration for async tasks.
"""
from datetime import timedelta

from celery import Celery

from app.core.config import (
    LICENSE_REFRESH_INTERVAL_HOURS,
    VERSION_CHECK_INTERVAL_HOURS,
    settings,
)

# Create Celery app instance
celery_app = Celery(
    "journiv",
    include=[
        "app.tasks.import_tasks",
        "app.tasks.export_tasks",
        "app.tasks.goal_tasks",
        "app.tasks.version_check",
        "app.tasks.license_refresh",
        "app.tasks.immich_import_tasks",
        "app.tasks.media_processing_tasks",
        "app.integrations.tasks",
    ],
)

# Configure Celery from settings
celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_serializer=settings.celery_task_serializer,
    result_serializer=settings.celery_result_serializer,
    accept_content=settings.celery_accept_content,
    timezone=settings.celery_timezone,
    enable_utc=settings.celery_enable_utc,
    beat_schedule={
        "check-journiv-version-interval": {
            "task": "app.tasks.version_check.check_journiv_version",
            "schedule": timedelta(hours=VERSION_CHECK_INTERVAL_HOURS),
        },
        "refresh-license-interval": {
            "task": "app.tasks.license_refresh.refresh_license",
            "schedule": timedelta(hours=LICENSE_REFRESH_INTERVAL_HOURS),
        },
        "sync-integrations-interval": {
            "task": "app.integrations.tasks.sync_all_providers_task",
            "schedule": timedelta(hours=settings.integration_sync_interval_hours),
        },
        "close-goal-periods-interval": {
            "task": "app.tasks.goal_tasks.close_goal_periods",
            "schedule": timedelta(hours=1),
        },
    },
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit for tasks
    task_soft_time_limit=3300,  # 55 minutes soft limit
    worker_prefetch_multiplier=1,  # One task at a time
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    task_acks_late=True,  # Acknowledge tasks after completion
    task_reject_on_worker_lost=True,  # Requeue tasks if worker dies
    broker_connection_retry_on_startup=True,  # Retry broker connection on startup
)

# Auto-discover tasks from app.tasks module
celery_app.autodiscover_tasks(["app.tasks", "app.integrations"])


def get_celery_app() -> Celery:
    """Get Celery app instance."""
    return celery_app
