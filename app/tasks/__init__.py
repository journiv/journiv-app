"""
Background tasks for Journiv.
"""

# Ensure Celery registers task modules on worker startup.
from app.tasks import (
    export_tasks,  # noqa: F401
    immich_import_tasks,  # noqa: F401
    import_tasks,  # noqa: F401
    license_refresh,  # noqa: F401
    media_processing_tasks,  # noqa: F401
    version_check,  # noqa: F401
)
