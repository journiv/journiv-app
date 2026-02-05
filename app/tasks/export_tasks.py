"""
Celery tasks for export operations.
"""
from uuid import UUID

from sqlmodel import Session

from app.core.celery_app import celery_app
from app.core.database import engine
from app.core.logging_config import log_error, log_info, log_warning
from app.models.export_job import ExportJob
from app.services.export_service import ExportService
from app.utils.import_export.constants import ProgressStages
from app.utils.import_export.progress_utils import create_throttled_progress_callback


@celery_app.task(name="app.tasks.export.process_export_job")
def process_export_job(job_id: str):
    """
    Process an export job asynchronously.

    Args:
        job_id: Export job ID (UUID string)

    Returns:
        Dictionary with export results
    """
    job_uuid = UUID(job_id)

    with Session(engine) as db:
        try:
            # Get job
            job = db.get(ExportJob, job_uuid)
            if not job:
                log_error(f"Export job not found: {job_id}", job_id=job_id)
                return {
                    "status": "not_found",
                    "error": "Job not found"
                }

            log_info(f"Processing export job {job_id}", job_id=job_id, user_id=str(job.user_id))

            # Mark as running
            job.mark_running()
            db.commit()

            # Create export service
            export_service = ExportService(db)
            total_entries = export_service.count_entries(
                user_id=job.user_id,
                export_type=job.export_type,
                journal_ids=job.journal_ids,
            )
            job.total_items = total_entries
            job.processed_items = 0
            db.commit()

            # Update progress: Building export data (set minimum)
            job.set_progress(ProgressStages.EXPORT_BUILDING_DATA)
            db.commit()

            # Create throttled progress callback for data building stage
            # Progress range: 10% (BUILDING_DATA) to 50% (CREATING_ZIP)
            handle_progress = create_throttled_progress_callback(
                job=job,
                db=db,
                start_progress=ProgressStages.EXPORT_BUILDING_DATA,
                end_progress=ProgressStages.EXPORT_CREATING_ZIP,
                commit_interval=10,
                percentage_threshold=5,
            )

            # Build export data
            export_data = export_service.build_export_data(
                user_id=job.user_id,
                export_type=job.export_type,
                journal_ids=job.journal_ids,
                total_entries=total_entries,
                progress_callback=handle_progress,
            )

            # Update progress: Creating ZIP (ensure minimum, but don't regress)
            current_progress = job.progress or ProgressStages.EXPORT_CREATING_ZIP
            job.set_progress(max(current_progress, ProgressStages.EXPORT_CREATING_ZIP))
            db.commit()

            # Create ZIP archive
            zip_path, file_size, stats = export_service.create_export_zip(
                export_data=export_data,
                user_id=job.user_id,
                include_media=job.include_media,
            )

            # Update progress: Finalizing (ensure minimum, but don't regress)
            current_progress = job.progress or ProgressStages.EXPORT_FINALIZING
            job.set_progress(max(current_progress, ProgressStages.EXPORT_FINALIZING))
            db.commit()

            # Mark as completed
            job.total_items = job.total_items or stats.get("entry_count", 0)
            job.processed_items = job.total_items
            job.mark_completed(
                file_path=str(zip_path),
                file_size=file_size,
                result_data=stats,
            )
            db.commit()

            log_info(
                f"Export job {job_id} completed successfully",
                job_id=job_id,
                user_id=str(job.user_id),
                file_size=file_size,
                entry_count=stats.get("entry_count", 0),
                media_count=stats.get("media_count", 0)
            )

            return {
                "status": "completed",
                "file_path": str(zip_path),
                "file_size": file_size,
                "stats": stats,
            }

        except Exception as e:
            # Mark as failed
            user_id = None
            try:
                job = db.get(ExportJob, job_uuid)
                if job:
                    user_id = str(job.user_id)
                    job.mark_failed(str(e))
                    db.commit()
            except Exception as cleanup_error:
                # Log secondary failure but still return main error
                log_error(cleanup_error, job_id=job_id, context="failed_to_mark_job_failed")

            log_error(e, job_id=job_id, user_id=user_id)

            return {
                "status": "failed",
                "error": str(e),
            }
        finally:
            if "export_service" in locals():
                try:
                    export_service.cleanup_old_exports()
                except Exception as cleanup_error:
                    log_warning(f"Export cleanup failed: {cleanup_error}", job_id=job_id)
