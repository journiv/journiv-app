"""
Celery tasks for import operations.
"""
from pathlib import Path
from uuid import UUID

from sqlmodel import Session

from app.core.celery_app import celery_app
from app.core.database import engine
from app.core.logging_config import log_error, log_info
from app.models.enums import ImportSourceType
from app.models.import_job import ImportJob
from app.services.import_service import ImportService
from app.utils.import_export import validate_import_data
from app.utils.import_export.constants import ProgressStages
from app.utils.import_export.progress_utils import create_throttled_progress_callback


@celery_app.task(name="app.tasks.import.process_import_job", bind=True)
def process_import_job(self, job_id: str):
    """
    Process an import job asynchronously.

    Args:
        job_id: Import job ID (UUID string)

    Returns:
        Dictionary with import results
    """
    job_uuid = UUID(job_id)

    with Session(engine) as db:
        try:
            # Get job
            job = db.get(ImportJob, job_uuid)
            if not job:
                log_error(f"Import job not found: {job_id}", job_id=job_id)
                return {
                    "status": "not_found",
                    "error": "Job not found"
                }

            log_info(f"Processing import job {job_id}", job_id=job_id, user_id=str(job.user_id), source_type=job.source_type.value)

            # Mark as running
            job.mark_running()
            db.commit()

            # Create import service
            import_service = ImportService(db)

            # Update progress: Extracting (set minimum)
            job.set_progress(ProgressStages.IMPORT_EXTRACTING)
            db.commit()

            # Extract import data (skip for Day One - has custom extraction)
            if not job.file_path:
                raise ValueError("Import job must have a file_path")
            file_path = Path(job.file_path)

            if job.source_type == ImportSourceType.DAYONE:
                # Day One has custom parsing; import_dayone_data computes totals
                total_entries = None
                data = None
                media_dir = None
            else:
                # Generic extraction for Journiv and other formats
                data, media_dir = import_service.extract_import_data(file_path)
                validation = validate_import_data(data, job.source_type.value)
                if not validation.valid:
                    raise ValueError(f"Invalid import file: {validation.errors}")

                total_entries = import_service.count_entries_in_data(data)

            job.total_items = total_entries or 0
            job.processed_items = 0

            # Update progress: Processing (ensure minimum, but don't regress from extracting)
            current_progress = job.progress or ProgressStages.IMPORT_PROCESSING
            job.set_progress(max(current_progress, ProgressStages.IMPORT_PROCESSING))
            db.commit()

            # Create throttled progress callback for processing stage
            # Progress range: 30% (PROCESSING) to 90% (FINALIZING)
            handle_progress = create_throttled_progress_callback(
                job=job,
                db=db,
                start_progress=ProgressStages.IMPORT_PROCESSING,
                end_progress=ProgressStages.IMPORT_FINALIZING,
                commit_interval=10,
                percentage_threshold=5,
            )

            # Import based on source type
            if job.source_type == ImportSourceType.JOURNIV:
                if data is None:
                    raise ValueError("Import data must be present for Journiv import")
                summary = import_service.import_journiv_data(
                    user_id=job.user_id,
                    data=data,
                    media_dir=media_dir,
                    total_entries=total_entries,
                    progress_callback=handle_progress,
                )
            elif job.source_type == ImportSourceType.DAYONE:
                # Day One import doesn't use the generic extract_import_data
                # because it has a different ZIP structure
                summary = import_service.import_dayone_data(
                    user_id=job.user_id,
                    file_path=file_path,
                    total_entries=total_entries,
                    progress_callback=handle_progress,
                )
            else:
                raise NotImplementedError(
                    f"Import from {job.source_type} not yet implemented"
                )

            # Update progress: Finalizing (ensure minimum, but don't regress)
            current_progress = job.progress or ProgressStages.IMPORT_FINALIZING
            job.set_progress(max(current_progress, ProgressStages.IMPORT_FINALIZING))
            db.commit()

            # Build result data
            result_data = summary.model_dump()

            # Mark as completed
            job.total_items = job.total_items or summary.entries_created
            job.processed_items = job.total_items
            job.mark_completed(result_data=result_data)
            db.commit()

            # Clean up temp files
            import_service.cleanup_temp_files(file_path)

            log_info(
                f"Import job {job_id} completed successfully",
                job_id=job_id,
                user_id=str(job.user_id),
                journals_created=summary.journals_created,
                entries_created=summary.entries_created,
                media_files_imported=summary.media_files_imported,
                warning_count=len(summary.warnings)
            )

            return {
                "status": "completed",
                "summary": result_data,
            }

        except Exception as e:
            # Mark as failed
            user_id = None
            try:
                db.rollback()
                job = db.get(ImportJob, job_uuid)
                if job:
                    user_id = str(job.user_id)
                    job.mark_failed(str(e))
                    db.commit()

                    # Try to clean up temp files even on failure
                    if job.file_path:
                        file_p = Path(str(job.file_path))
                        import_service = ImportService(db)
                        import_service.cleanup_temp_files(file_p)
                        log_info(f"Cleaned up temp files for job {job_id}")
            except Exception as cleanup_error:
                log_error(cleanup_error, job_id=job_id, user_id=user_id, context="cleanup")

            log_error(e, job_id=job_id, user_id=user_id)

            return {
                "status": "failed",
                "error": str(e),
            }
