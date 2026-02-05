"""
Import endpoints for importing data into Journiv.
"""
import uuid
from typing import Annotated, List

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlmodel import Session, col, select

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.logging_config import log_error, log_user_action
from app.models.enums import ImportSourceType
from app.models.import_job import ImportJob
from app.models.user import User
from app.schemas.dto import ImportJobStatusResponse
from app.services.import_service import ImportService
from app.tasks.import_tasks import process_import_job

router = APIRouter(prefix="/import", tags=["import-export"])


@router.post(
    "/upload",
    response_model=ImportJobStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Import job created and queued"},
        400: {"description": "Invalid import file or request"},
        401: {"description": "Not authenticated"},
        413: {"description": "File too large"},
        500: {"description": "Internal server error"},
    }
)
async def upload_import(
    file: Annotated[UploadFile, File(description="Import file (ZIP archive)")],
    source_type: Annotated[str, Form(description="Source type: journiv, markdown, dayone")],
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Upload a file for import.

    **Supported source types:**
    - `journiv`: Journiv export ZIP file
    - `dayone`: Day One JSON export ZIP file
    - `markdown`: Markdown files export (coming soon)

    **File requirements:**
    - Must be a ZIP archive
    - Maximum size: configured in IMPORT_EXPORT_MAX_FILE_SIZE_MB
    - For Journiv: Must contain data.json file
    - For Day One: Must contain Journal.json files and photos/ directory

    The import will be processed asynchronously. Use the job ID to check status.
    """
    # Validate source type
    try:
        source_type_enum = ImportSourceType(source_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source type: {source_type}. Must be one of: journiv, markdown, dayone"
        ) from None

    # Day One and Journiv imports are now supported
    if source_type_enum not in [ImportSourceType.JOURNIV, ImportSourceType.DAYONE]:
        raise HTTPException(
            status_code=400,
            detail=f"Import source '{source_type}' not yet supported. Currently supported: journiv, dayone"
        )

    # Process upload using UploadManager
    from app.utils.import_export import UploadManager

    upload_path = None
    try:
        upload_path = await UploadManager.process_upload(
            file=file,
            source_type=source_type.lower()
        )
    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email, context="import_upload_processing")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the uploaded file"
        ) from e

    try:
        # Create import job
        import_service = ImportService(session)
        job = import_service.create_import_job(
            user_id=current_user.id,
            source_type=source_type_enum,
            file_path=str(upload_path),
        )

        # Queue Celery task
        process_import_job.delay(str(job.id))

        log_user_action(
            current_user.email,
            f"created import job {job.id} (type: {source_type})",
            request_id=None
        )

        # Return job status
        return ImportJobStatusResponse(
            id=str(job.id),
            status=job.status.value,
            progress=job.progress,
            total_items=job.total_items,
            processed_items=job.processed_items,
            created_at=job.created_at,
            completed_at=job.completed_at,
            result_data=job.result_data,
            errors=job.errors,
            warnings=job.warnings,
            source_type=job.source_type.value,
        )

    except Exception as e:
        # Clean up if job creation failed
        if upload_path and upload_path.exists():
            upload_path.unlink(missing_ok=True)

        log_error(e, request_id=None, user_email=current_user.email, context="import_job_creation")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while creating the import job"
        ) from e


@router.get(
    "/{job_id}",
    response_model=ImportJobStatusResponse,
    responses={
        200: {"description": "Import job status"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
        404: {"description": "Import job not found"},
        500: {"description": "Internal server error"},
    }
)
def get_import_status(
    job_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Get import job status.

    Check the progress and status of an import job. When status is 'completed',
    the data has been successfully imported into your account.
    """
    try:
        job = session.exec(select(ImportJob).where(ImportJob.id == job_id)).first()

        if not job:
            raise HTTPException(status_code=404, detail="Import job not found")

        # Check authorization (user can only access their own jobs)
        if job.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this import job")

        return ImportJobStatusResponse(
            id=str(job.id),
            status=job.status.value,
            progress=job.progress,
            total_items=job.total_items,
            processed_items=job.processed_items,
            created_at=job.created_at,
            completed_at=job.completed_at,
            result_data=job.result_data,
            errors=job.errors,
            warnings=job.warnings,
            source_type=job.source_type.value,
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email, context="get_import_status")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while retrieving import status"
        ) from e


@router.get(
    "/",
    response_model=List[ImportJobStatusResponse],
    responses={
        200: {"description": "List of import jobs"},
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"},
    }
)
def list_imports(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List import jobs for current user.

    Returns recent import jobs ordered by creation date (newest first).
    """
    try:

        jobs = list(
            session.exec(
                select(ImportJob)
                .where(ImportJob.user_id == current_user.id)
                .order_by(col(ImportJob.created_at).desc())
                .offset(offset)
                .limit(limit)
            )
        )

        return [
            ImportJobStatusResponse(
                id=str(job.id),
                status=job.status.value,
                progress=job.progress,
                total_items=job.total_items,
                processed_items=job.processed_items,
                created_at=job.created_at,
                completed_at=job.completed_at,
                result_data=job.result_data,
                errors=job.errors,
                warnings=job.warnings,
                source_type=job.source_type.value,
            )
            for job in jobs
        ]

    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email, context="list_imports")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while listing imports"
        ) from e


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Import job deleted"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
        404: {"description": "Import job not found"},
        409: {"description": "Cannot delete running job"},
        500: {"description": "Internal server error"},
    }
)
def delete_import_job(
    job_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Delete an import job record.

    This only deletes the job record, not the imported data.
    Cannot delete a job that is currently running.
    """
    try:
        job = session.exec(select(ImportJob).where(ImportJob.id == job_id)).first()

        if not job:
            raise HTTPException(status_code=404, detail="Import job not found")

        # Check authorization
        if job.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this import job")

        # Check if job is running
        from app.models.enums import JobStatus
        if job.status == JobStatus.RUNNING:
            raise HTTPException(status_code=409, detail="Cannot delete running job")

        # Clean up uploaded file if it exists
        if job.file_path:
            try:
                from pathlib import Path
                import_service = ImportService(session)
                import_service.cleanup_temp_files(Path(job.file_path))
            except Exception as cleanup_error:
                # Log but don't fail deletion if cleanup fails
                log_error(cleanup_error, request_id=None, user_email=current_user.email, context="import_job_cleanup")

        # Delete job
        session.delete(job)
        session.commit()

        log_user_action(
            current_user.email,
            f"deleted import job {job.id}",
            request_id=None
        )

        return None

    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email, context="delete_import_job")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while deleting import job"
        ) from e
