"""
Export endpoints for creating data exports.
"""
import os
import uuid
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlmodel import Session, col, select

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_session
from app.core.logging_config import log_error, log_user_action
from app.models.enums import ExportType, JobStatus
from app.models.export_job import ExportJob
from app.models.user import User
from app.schemas.dto import (
    ExportJobCreateRequest,
    ExportJobStatusResponse,
)
from app.schemas.media import MediaSignedUrlResponse
from app.services.export_service import ExportService
from app.tasks.export_tasks import process_export_job

router = APIRouter(prefix="/export", tags=["import-export"])


def _get_download_url(request: Request, job_id: uuid.UUID) -> Optional[str]:
    """
    Generate download URL for export job.

    Returns None if URL generation fails or job is not completed.
    """
    try:
        return str(request.url_for("download_export", job_id=str(job_id)))
    except Exception:
        return None


@router.post(
    "/",
    response_model=ExportJobStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Export job created and queued"},
        400: {"description": "Invalid export request"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
        501: {"description": "Not implemented"},
        500: {"description": "Internal server error"},
    }
)
async def create_export(
    export_request: ExportJobCreateRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Create a new export job.

    The export will be processed asynchronously. Use the job ID to check status
    and download the file when completed.

    **Export Types:**
    - `full`: Export all user data (journals, entries, media, settings)
    - `journal`: Export specific journals (requires journal_ids)
    """
    # Pydantic already validates export_type as ExportType enum
    export_type = export_request.export_type

    # Validate journal export has journal IDs
    if export_type == ExportType.JOURNAL:
        if not export_request.journal_ids or len(export_request.journal_ids) == 0:
            raise HTTPException(
                status_code=400,
                detail="journal_ids required for journal export"
            )

    try:
        export_service = ExportService(session)

        # Create export job
        job = export_service.create_export(
            user_id=current_user.id,
            export_type=export_type,
            journal_ids=[uuid.UUID(jid) for jid in export_request.journal_ids] if export_request.journal_ids else None,
            include_media=export_request.include_media,
        )

        # Queue Celery task
        if settings.environment == "test" or os.getenv("PYTEST_CURRENT_TEST"):
            process_export_job(str(job.id))
        elif settings.celery_broker_url:
            process_export_job.delay(str(job.id))
        else:
            process_export_job(str(job.id))

        log_user_action(
            current_user.email,
            f"created export job {job.id} (type: {export_type})",
            request_id=None
        )

        # Return job status
        return ExportJobStatusResponse(
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
            export_type=job.export_type.value,
            include_media=job.include_media,
            file_path=None,  # Don't expose internal path
            file_size=job.file_size,
            download_url=_get_download_url(request, job.id) if job.status == JobStatus.COMPLETED else None,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while creating export job"
        ) from None


@router.get(
    "/{job_id}",
    response_model=ExportJobStatusResponse,
    responses={
        200: {"description": "Export job status"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
        404: {"description": "Export job not found"},
        500: {"description": "Internal server error"},
    }
)
async def get_export_status(
    job_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Get export job status.

    Check the progress and status of an export job. When status is 'completed',
    use the download endpoint to retrieve the file.
    """
    try:
        job = session.exec(select(ExportJob).where(ExportJob.id == job_id)).first()

        if not job:
            raise HTTPException(status_code=404, detail="Export job not found")

        # Check authorization (user can only access their own jobs)
        if job.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this export job")

        return ExportJobStatusResponse(
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
            export_type=job.export_type.value,
            include_media=job.include_media,
            file_path=None,  # Don't expose internal path
            file_size=job.file_size,
            download_url=_get_download_url(request, job.id) if job.status == JobStatus.COMPLETED else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while retrieving export status") from None


@router.get(
    "/{job_id}/download",
    name="download_export",
    responses={
        200: {"description": "Export file", "content": {"application/zip": {}}},
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
        404: {"description": "Export job not found or file not ready"},
        500: {"description": "Internal server error"},
    }
)
async def download_export(
    job_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Download completed export file.

    Returns the ZIP archive containing the exported data and media files.
    The file will be named `journiv_export_{timestamp}.zip`.
    """
    try:
        job = session.exec(select(ExportJob).where(ExportJob.id == job_id)).first()

        if not job:
            raise HTTPException(status_code=404, detail="Export job not found")

        # Check authorization
        if job.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this export")

        # Check job is completed
        if job.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=404,
                detail=f"Export not ready (status: {job.status.value})"
            )

        # Check file exists
        if not job.file_path:
            raise HTTPException(status_code=404, detail="Export file path not found")

        # Validate file path is within export directory (prevent directory traversal)
        export_root = Path(settings.export_dir).resolve()
        file_path = Path(job.file_path).resolve()

        try:
            file_path.relative_to(export_root)
        except ValueError:
            raise HTTPException(status_code=404, detail="Invalid export file path") from None

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Export file not found on disk")

        log_user_action(
            current_user.email,
            f"downloaded export {job.id}",
            request_id=None
        )

        # Return file
        return FileResponse(
            path=file_path,
            filename=file_path.name,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{file_path.name}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while downloading export") from None


@router.get(
    "/{job_id}/sign",
    response_model=MediaSignedUrlResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
        404: {"description": "Export job not found"},
    }
)
async def sign_export_url(
    job_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Generate a short-lived signed URL for export download.
    Useful for browser-native downloads where Authorization header cannot be added.
    """
    from app.core.signing import generate_export_signature
    from app.core.time_utils import utc_now

    # Expiration
    expires_at = int(utc_now().timestamp()) + settings.export_signed_url_expiration_seconds

    # Generate signature
    signature = generate_export_signature(
        job_id=str(job_id),
        user_id=str(current_user.id),
        expires_at=expires_at,
        secret=settings.secret_key
    )

    # Construct URL
    base_url = str(request.url_for("download_export_signed", job_id=str(job_id)))
    signed_url = f"{base_url}?uid={current_user.id}&exp={expires_at}&sig={signature}"

    return MediaSignedUrlResponse(
        signed_url=signed_url,
        expires_at=expires_at
    )


@router.get(
    "/{job_id}/download/signed",
    name="download_export_signed",
    responses={
        200: {"description": "Export file", "content": {"application/zip": {}}},
        403: {"description": "Invalid signature or expired"},
        404: {"description": "Export job not found or file not ready"},
        500: {"description": "Internal server error"},
    }
)
async def download_export_signed(
    job_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    uid: Annotated[uuid.UUID, Query(alias="uid")],
    exp: Annotated[int, Query(alias="exp")],
    sig: Annotated[str, Query(alias="sig")],
):
    """
    Download completed export file using a signed URL.
    Does not require Authorization header if signature is valid.
    """
    from app.core.media_signing import is_signature_expired
    from app.core.signing import verify_export_signature

    # 1. Verify Signature
    if is_signature_expired(exp, settings.media_signed_url_grace_seconds):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signed URL expired")

    if not verify_export_signature(
        job_id=str(job_id),
        user_id=str(uid),
        expires_at=exp,
        signature=sig,
        secret=settings.secret_key,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    # 2. Proceed with download logic (duplicated from download_export but safely authenticated)
    try:
        job = session.exec(select(ExportJob).where(ExportJob.id == job_id)).first()

        if not job:
            raise HTTPException(status_code=404, detail="Export job not found")

        # Verify user matches signature
        if job.user_id != uid:
            raise HTTPException(status_code=403, detail="Not authorized for this export")

        if job.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=404,
                detail=f"Export not ready (status: {job.status.value})"
            )

        if not job.file_path:
            raise HTTPException(status_code=404, detail="Export file path not found")

        export_root = Path(settings.export_dir).resolve()
        file_path = Path(job.file_path).resolve()

        try:
            file_path.relative_to(export_root)
        except ValueError:
            raise HTTPException(status_code=404, detail="Invalid export file path") from None

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Export file not found on disk")

        # Return file
        return FileResponse(
            path=file_path,
            filename=file_path.name,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{file_path.name}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id=None, user_email=f"signed:{uid}")
        raise HTTPException(status_code=500, detail="An error occurred while downloading export") from None
@router.get(
    "/",
    response_model=List[ExportJobStatusResponse],
    responses={
        200: {"description": "List of export jobs"},
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"},
    }
)
async def list_exports(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """
    List export jobs for current user.

    Returns recent export jobs ordered by creation date (newest first).
    """
    try:

        jobs = list(
            session.exec(
                select(ExportJob)
                .where(ExportJob.user_id == current_user.id)
                .order_by(col(ExportJob.created_at).desc())
                .offset(offset)
                .limit(limit)
            )
        )

        return [
            ExportJobStatusResponse(
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
                export_type=job.export_type.value,
                include_media=job.include_media,
                file_path=None,
                file_size=job.file_size,
                download_url=_get_download_url(request, job.id) if job.status == JobStatus.COMPLETED else None,
            )
            for job in jobs
        ]

    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while listing exports") from None


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Export job deleted"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized"},
        404: {"description": "Export job not found"},
        409: {"description": "Cannot delete running job"},
        500: {"description": "Internal server error"},
    }
)
async def delete_export_job(
    job_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Delete an export job record.

    This deletes the job record and the associated export file if it exists.
    Cannot delete a job that is currently running.
    """
    try:
        job = session.exec(select(ExportJob).where(ExportJob.id == job_id)).first()

        if not job:
            raise HTTPException(status_code=404, detail="Export job not found")

        # Check authorization (user can only delete their own jobs)
        if job.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this export job")

        if job.status == JobStatus.RUNNING:
            raise HTTPException(status_code=409, detail="Cannot delete running job")

        # Delete export file if it exists
        if job.file_path:
            # Validate file path is within export directory (prevent directory traversal)
            export_root = Path(settings.export_dir).resolve()
            file_path = Path(job.file_path).resolve()

            try:
                file_path.relative_to(export_root)
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except Exception as e:
                        # Log but don't fail if file deletion fails
                        log_error(e, request_id=None, user_email=current_user.email)
            except ValueError:
                # Invalid path - log warning but don't fail deletion
                log_error(
                    Exception("Invalid export file path detected during deletion"),
                    request_id=None,
                    user_email=current_user.email,
                    context="export_file_deletion_path_validation"
                )

        # Delete job record
        session.delete(job)
        session.commit()

        log_user_action(
            current_user.email,
            f"deleted export job {job.id}",
            request_id=None
        )

        return None

    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while deleting export job") from None
