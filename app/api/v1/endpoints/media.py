"""
Media upload and management endpoints.
"""
import inspect
import logging
import uuid
from pathlib import Path
from typing import Annotated, Optional, AsyncGenerator

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Header, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlmodel import Session

from app.api.dependencies import get_current_user, get_current_user_detached
from app.core import database as database_module
from app.core.config import settings
from app.core.media_signing import (
    attach_signed_urls,
    is_signature_expired,
)
from app.core.exceptions import (
    MediaNotFoundError,
    EntryNotFoundError,
    FileTooLargeError,
    InvalidFileTypeError,
    FileValidationError
)
from app.core.signing import verify_media_signature
from app.core.logging_config import LogCategory
from app.models.enums import UploadStatus
from app.models.user import User
from app.schemas.entry import EntryMediaResponse
from app.services import entry_service as entry_service_module
from app.services import media_service as media_service_module
from app.services.import_job_service import ImportJobService
from app.schemas.media import (
    ImmichImportRequest,
    ImmichImportStartResponse,
    ImmichImportJobResponse,
    MediaSignedUrlResponse,
    MediaBatchSignRequest,
    MediaBatchSignResponse,
    MediaBatchSignItem,
)
from app.core.celery_app import celery_app
from app.integrations.service import fetch_proxy_asset
import httpx
from starlette.background import BackgroundTask

async def _close_httpx_stream(response: httpx.Response) -> None:
    """Ensure streamed HTTP responses release network resources."""
    await response.aclose()

file_logger = logging.getLogger(LogCategory.FILE_UPLOADS.value)
error_logger = logging.getLogger(LogCategory.ERRORS.value)

router = APIRouter(prefix="/media", tags=["media"])


def _get_media_service():
    return media_service_module.MediaService()


def _get_db_session():
    """Wrapper around database.get_session to allow easy patching in tests."""
    session_or_generator = database_module.get_session()
    if inspect.isgenerator(session_or_generator):
        yield from session_or_generator
    else:
        yield session_or_generator


def _get_entry_service(session: Session):
    """Get entry service instance."""
    return entry_service_module.EntryService(session)


def _handle_batch_sign_errors(batch_response: MediaBatchSignResponse) -> None:
    """
    Handle errors from batch_sign_media response.

    Raises appropriate HTTPException based on error type.
    Used by both sign_media_url and batch_sign_media endpoints.
    """
    if batch_response.errors:
        error = batch_response.errors[0]
        error_msg = error.error.lower()

        # Map specific error messages to appropriate status codes
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error.error
            )
        elif "not active" in error_msg or "integration" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error.error
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error.error
            )

    # Additional check for empty results
    if not batch_response.results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )


async def _send_bytes_range_requests(file_path: Path, start: int, end: int) -> AsyncGenerator[bytes, None]:
    """Async generator function to send file bytes in range for streaming."""
    async with aiofiles.open(file_path, "rb") as f:
        await f.seek(start)
        remaining = end - start + 1
        while remaining:
            chunk_size = min(8192, remaining)  # 8KB chunks
            chunk = await f.read(chunk_size)
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


class SignedMediaRequest:
    """Dependency for verifying signed media requests."""

    def __init__(
        self,
        media_id: uuid.UUID,
        uid: uuid.UUID,
        exp: int,
        sig: str,
        media_type: str,
        variant: str,
    ):
        self.media_id = media_id
        self.uid = uid
        self.exp = exp
        self.sig = sig
        self.media_type = media_type  # "journiv" or "immich"
        self.variant = variant  # "original" or "thumbnail"


def verify_signed_media_request(
    media_id: uuid.UUID,
    uid: uuid.UUID = Query(..., alias="uid"),
    exp: int = Query(..., alias="exp"),
    sig: str = Query(..., alias="sig"),
    media_type: str = "journiv",
    variant: str = "original",
) -> SignedMediaRequest:
    """
    Dependency to verify signed media request parameters.

    Validates signature and expiration for media access.

    Raises:
        HTTPException: If signature is invalid or expired
    """
    if is_signature_expired(exp, settings.media_signed_url_grace_seconds):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Signed URL expired"
        )

    if not verify_media_signature(
        media_type,
        variant,
        str(media_id),
        str(uid),
        exp,
        sig,
        settings.secret_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid signature"
        )

    return SignedMediaRequest(media_id, uid, exp, sig, media_type, variant)



@router.post(
    "/upload",
    response_model=EntryMediaResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid file or validation failed"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Entry not found"},
        413: {"description": "File too large"},
        500: {"description": "Internal server error"},
    }
)
async def upload_media(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(_get_db_session)],
    file: UploadFile = File(...),
    entry_id: uuid.UUID = Form(...),
    alt_text: Optional[str] = Form(None),
):
    """
    Upload a media file.

    Supports images, videos, and audio. Files are validated and processed in background.
    """
    media_service = _get_media_service()

    try:
        result = await media_service.upload_media(
            file=file,
            user_id=current_user.id,
            entry_id=entry_id,
            alt_text=alt_text,
            session=session
        )

        media_record = result["media_record"]
        full_file_path = result["full_file_path"]

        if media_record and hasattr(media_record, 'id') and full_file_path:
            try:
                celery_app.send_task(
                    "app.tasks.media.process_media_upload",
                    args=[str(media_record.id), full_file_path, str(current_user.id)]
                )
            except Exception as e:
                error_logger.warning(
                    "Failed to queue media processing task",
                    extra={"user_id": str(current_user.id), "media_id": str(media_record.id), "error": str(e)}
                )

        response = EntryMediaResponse.model_validate(media_record)
        return attach_signed_urls(
            response,
            str(current_user.id),
            include_incomplete=True,
        )

    except FileTooLargeError as e:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(e)
        )
    except FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except InvalidFileTypeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except EntryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found"
        )
    except Exception as e:
        error_logger.error(
            "Unexpected error uploading media",
            extra={"user_id": str(current_user.id), "error": str(e), "error_type": type(e).__name__},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while uploading file"
        )


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive or permission denied"},
        404: {"description": "Media not found"},
        500: {"description": "Failed to delete media"},
    }
)
async def delete_media(
    media_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(_get_db_session)]
):
    """Delete a media file by ID."""
    media_service = _get_media_service()

    try:
        await media_service.delete_media_by_id(media_id, current_user.id, session)

        file_logger.info(
            "Media deleted successfully ",
            extra={"user_id": str(current_user.id), "media_id": str(media_id)}
        )
        return {
            "message": "Media deleted successfully",
            "media_id": str(media_id)
        }
    except MediaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        error_logger.error(
            "Unexpected error deleting media ",
            extra={"user_id": str(current_user.id), "media_id": str(media_id), "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting media"
        )


@router.get(
    "/{media_id}/sign",
    response_model=MediaSignedUrlResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive or forbidden"},
        404: {"description": "Media not found"},
    }
)
async def sign_media_url(
    media_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(_get_db_session)],
):
    """Generate a short-lived signed URL for media playback."""
    media_service = _get_media_service()

    # Use batch_sign_media for consistent signing logic
    batch_request = MediaBatchSignRequest(
        items=[MediaBatchSignItem(id=str(media_id), variant="original")]
    )

    batch_response = await media_service.batch_sign_media(
        batch_request, current_user.id, session
    )

    _handle_batch_sign_errors(batch_response)

    result = batch_response.results[0]
    return MediaSignedUrlResponse(
        signed_url=result.signed_url,
        expires_at=result.expires_at
    )


@router.post(
    "/batch-sign",
    response_model=MediaBatchSignResponse,
    responses={
        400: {"description": "Invalid request"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive or forbidden"},
    }
)
async def batch_sign_media(
    request: MediaBatchSignRequest,
    current_user: Annotated[User, Depends(get_current_user_detached)],
):
    """Batch sign media URLs for entry media IDs."""
    media_service = _get_media_service()

    try:
        # Use database session context since we're called with get_current_user_detached
        # batch_sign_media handles its own queries
        with database_module.get_session_context() as session:
            batch_response = await media_service.batch_sign_media(
                request, current_user.id, session
            )

            # For batch endpoint, return the response with both results and errors
            # This allows partial success - some items may succeed while others fail
            return batch_response

    except ValueError as e:
        # Handle validation errors from the service layer
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None
    except Exception as e:
        # Handle unexpected errors
        error_logger.error(
            "Unexpected error batch signing media",
            extra={"user_id": str(current_user.id), "error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sign media URLs"
        )


@router.get(
    "/{media_id}/signed",
    name="get_media_signed",
    responses={
        403: {"description": "Invalid or expired signature"},
        404: {"description": "Media not found"},
        416: {"description": "Range Not Satisfiable"},
    }
)
async def get_media_signed(
    media_id: uuid.UUID,
    uid: uuid.UUID = Query(..., alias="uid"),
    exp: int = Query(..., alias="exp"),
    sig: str = Query(..., alias="sig"),
    range_header: Optional[str] = Header(None, alias="range")
):
    """Get media file by ID using a short-lived signed URL."""
    if is_signature_expired(exp, settings.media_signed_url_grace_seconds):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signed URL expired")
    if not verify_media_signature(
        "journiv",
        "original",
        str(media_id),
        str(uid),
        exp,
        sig,
        settings.secret_key,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    media_service = _get_media_service()
    try:
        # Fetch metadata in SHORT-LIVED session, then release DB connection
        # before starting the long-running streaming operation
        external_provider = None
        external_asset_id = None
        file_info = None

        with database_module.get_session_context() as session:
            # Fetch media record and extract required metadata
            media = media_service.get_media_by_id(media_id, uid, session)
            external_provider = media.external_provider
            external_asset_id = media.external_asset_id

            # For internal media, fetch file info while we have the session
            if external_provider != "immich":
                file_info = await media_service.get_media_file_for_serving(
                    media_id, uid, session, range_header
                )
        # Session is now closed - DB connection released

        # Handle Immich proxy (Outside DB Session)
        if external_provider == "immich":
            if not external_asset_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

            from app.models.integration import IntegrationProvider

            try:
                # Create a new short-lived session just for credential lookup
                # fetch_proxy_asset uses cache to minimize DB hits
                with database_module.get_session_context() as proxy_session:
                    response = await fetch_proxy_asset(
                        session=proxy_session,
                        user_id=uid,
                        provider=IntegrationProvider.IMMICH,
                        asset_id=external_asset_id,
                        variant="original",
                        range_header=range_header,
                    )
                # Session closed, but streaming response is still open
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
            except Exception as e:
                error_logger.exception(f"Proxy original failed: {e}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch original file") from e

            if response.status_code in (401, 403, 404, 416):
                await _close_httpx_stream(response)
                # Map proxied status codes
                if response.status_code == 404:
                     raise HTTPException(status_code=404, detail="Media not found")
                raise HTTPException(status_code=response.status_code, detail="Provider error")

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                await _close_httpx_stream(response)
                raise HTTPException(status_code=e.response.status_code, detail="Provider error")

            # Forward headers
            response_headers = {
                "Cache-Control": "public, max-age=3600",
                "X-Provider": "immich",
            }
            for header in ["Content-Range", "Accept-Ranges", "Content-Length"]:
                if header.lower() in response.headers:
                    response_headers[header] = response.headers[header.lower()]

            status_code = status.HTTP_206_PARTIAL_CONTENT if response.status_code == 206 else status.HTTP_200_OK

            return StreamingResponse(
                response.aiter_bytes(),
                status_code=status_code,
                media_type=response.headers.get("content-type", "application/octet-stream"),
                headers=response_headers,
                background=BackgroundTask(_close_httpx_stream, response)
            )

        # Handle Internal Media (file_info was fetched above)
        if not file_info:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

        if file_info["range_info"]:
            range_info = file_info["range_info"]
            headers = {
                "Content-Range": f"bytes {range_info['start']}-{range_info['end']}/{file_info['file_size']}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(range_info['length']),
                "Cache-Control": "public, max-age=3600",
            }

            return StreamingResponse(
                _send_bytes_range_requests(
                    file_info["file_path"],
                    range_info["start"],
                    range_info["end"]
                ),
                status_code=status.HTTP_206_PARTIAL_CONTENT,
                headers=headers,
                media_type=file_info["content_type"],
            )

        return FileResponse(
            path=file_info["file_path"],
            media_type=file_info["content_type"],
            filename=file_info["filename"],
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600",
            },
        )
    except MediaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )
    except ValueError as e:
        if "Range" in str(e):
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        error_logger.error(
            f"Error serving signed media file: {e}",
            extra={"media_id": str(media_id)},
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to serve file")


@router.get(
    "/{media_id}/thumbnail/signed",
    name="get_media_thumbnail_signed",
    responses={
        403: {"description": "Invalid or expired signature"},
        404: {"description": "Thumbnail not found"},
    }
)
async def get_media_thumbnail_signed(
    media_id: uuid.UUID,
    uid: uuid.UUID = Query(..., alias="uid"),
    exp: int = Query(..., alias="exp"),
    sig: str = Query(..., alias="sig"),
):
    """Get media thumbnail by ID using a short-lived signed URL."""
    if is_signature_expired(exp, settings.media_signed_url_grace_seconds):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signed URL expired")
    if not verify_media_signature(
        "journiv",
        "thumbnail",
        str(media_id),
        str(uid),
        exp,
        sig,
        settings.secret_key,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    media_service = _get_media_service()
    try:
        # Fetch metadata in SHORT-LIVED session, then release DB connection
        external_provider = None
        external_asset_id = None
        thumbnail_path = None

        with database_module.get_session_context() as session:
            media = media_service.get_media_by_id(media_id, uid, session)
            external_provider = media.external_provider
            external_asset_id = media.external_asset_id

            # For internal media, fetch thumbnail path while we have the session
            if external_provider != "immich":
                thumbnail_path = media_service.get_media_thumbnail_path(media)
        # Session is now closed - DB connection released

        # Handle Immich proxy for thumbnails (Outside DB Session)
        if external_provider == "immich":
            if not external_asset_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found")

            from app.models.integration import IntegrationProvider

            try:
                # Create a new short-lived session just for credential lookup
                with database_module.get_session_context() as proxy_session:
                    response = await fetch_proxy_asset(
                        session=proxy_session,
                        user_id=uid,
                        provider=IntegrationProvider.IMMICH,
                        asset_id=external_asset_id,
                        variant="thumbnail",
                    )
                # Session closed, but streaming response is still open
            except Exception as e:
                 error_logger.exception(f"Proxy thumbnail failed: {e}")
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch thumbnail") from e

            if response.status_code != 200:
                await _close_httpx_stream(response)
                # If 404/401, we might want to try refreshing or just fail
                raise HTTPException(status_code=response.status_code, detail="Thumbnail not found in provider")

            return StreamingResponse(
                response.aiter_bytes(),
                media_type=response.headers.get("content-type", "image/jpeg"),
                headers={
                    "Cache-Control": "public, max-age=3600",
                    "X-Provider": "immich"
                },
                background=BackgroundTask(_close_httpx_stream, response)
            )

        # Handle Internal (thumbnail_path was fetched above)
        if not thumbnail_path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found")

        return FileResponse(thumbnail_path)
    except MediaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        error_logger.error(
            "Error serving signed thumbnail",
            extra={"media_id": str(media_id), "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to serve thumbnail"
        )


@router.get(
    "/{media_id}/info",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive or forbidden"},
        404: {"description": "Media not found"},
    }
)
async def get_media_info(
    media_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(_get_db_session)]
):
    """Get media information and metadata by ID."""
    media_service = _get_media_service()

    try:
        media = media_service.get_media_by_id(media_id, current_user.id, session)
        full_path = media_service.get_media_file_path(media)

        info = await media_service.get_media_info(str(full_path))
        return info
    except MediaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        error_logger.error(
            "Error getting media info",
            extra={"user_id": str(current_user.id), "media_id": str(media_id), "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get media information"
        )


@router.get(
    "/formats",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_supported_formats(
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Get supported file formats.

    Returns lists of supported image, video, and audio formats.
    """
    try:
        media_service = _get_media_service()
        return media_service.get_supported_formats()
    except Exception as e:
        error_logger.error(
            "Error getting supported formats",
            extra={"user_id": str(current_user.id), "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get supported formats"
        )





@router.post(
    "/import-from-immich-async",
    response_model=ImmichImportStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"description": "Invalid request or Immich not connected"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Entry not found"},
    }
)
async def import_from_immich_async(
    request: ImmichImportRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(_get_db_session)],
):
    """
    Start an import job for Immich assets (supports both link-only and copy modes).

    Behavior depends on integration.import_mode:
    - LINK_ONLY: Creates placeholder media and processes metadata asynchronously
    - COPY: Creates placeholder media and processes downloads asynchronously
    """
    from app.models.integration import Integration, IntegrationProvider, ImportMode
    from app.services.import_job_service import ImportJobService
    from sqlmodel import select

    try:
        # 1. Verify Immich integration exists and is active
        immich_integration = session.exec(
            select(Integration)
            .where(Integration.user_id == current_user.id)
            .where(Integration.provider == IntegrationProvider.IMMICH)
        ).first()

        if not immich_integration:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Immich integration not connected. Please connect in Settings."
            )

        if not immich_integration.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Immich integration is inactive. Please reconnect in Settings."
            )

        # 2. Verify entry exists
        entry_service = _get_entry_service(session)
        entry = entry_service.get_entry_by_id(request.entry_id, current_user.id)
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entry not found"
            )

        # 3. Create job and process asynchronously via Celery
        import_service = ImportJobService(session)

        file_logger.info(
            f"[IMMICH_IMPORT] Creating job for {len(request.asset_ids)} assets",
            extra={"user_id": str(current_user.id), "entry_id": str(request.entry_id), "asset_ids": request.asset_ids}
        )

        job = await import_service.create_and_process_job_async(
            user_id=current_user.id,
            entry_id=request.entry_id,
            asset_ids=request.asset_ids,
            assets=request.assets
        )

        file_logger.info(
            f"[IMMICH_IMPORT] Job created: {job.id}",
            extra={"job_id": str(job.id)}
        )

        # Ensure placeholders are committed before querying
        session.commit()

        # Re-fetch placeholders for response
        from app.models.entry import EntryMedia

        placeholder_media = session.exec(
             select(EntryMedia)
             .where(EntryMedia.entry_id == request.entry_id)
             .where(EntryMedia.external_provider == "immich")
             .where(EntryMedia.external_asset_id.in_(request.asset_ids))
        ).all()

        if immich_integration.import_mode == ImportMode.LINK_ONLY:
            try:
                celery_app.send_task(
                    "app.tasks.immich.process_link_only_import",
                    args=[str(job.id)]
                )
                file_logger.info(
                    f"Starting Immich import job (link-only): {len(request.asset_ids)} assets",
                    extra={"user_id": str(current_user.id), "asset_count": len(request.asset_ids)}
                )
            except Exception as e:
                file_logger.error(
                    "Failed to dispatch Immich link-only import job",
                    extra={"user_id": str(current_user.id), "job_id": str(job.id), "error": str(e)},
                    exc_info=True
                )
                try:
                    job.mark_failed(f"Celery dispatch failed: {e}")
                    session.add(job)
                    session.commit()
                except Exception:
                    file_logger.error("Failed to update job status after dispatch failure", extra={"job_id": str(job.id)})
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to queue Immich import job"
                )
        else:
            try:
                celery_app.send_task(
                    "app.tasks.immich.process_copy_import",
                    args=[str(job.id)]
                )
                file_logger.info(
                    f"Starting Immich import job (copy mode): {len(request.asset_ids)} assets",
                    extra={"user_id": str(current_user.id), "asset_count": len(request.asset_ids)}
                )
            except Exception as e:
                file_logger.error(
                    "Failed to dispatch Immich copy import job",
                    extra={"user_id": str(current_user.id), "job_id": str(job.id), "error": str(e)},
                    exc_info=True
                )
                job.mark_failed(f"Celery dispatch failed: {e}")
                session.add(job)
                try:
                    session.commit()
                except Exception:
                    file_logger.error(
                        "Failed to update job status after dispatch failure",
                        extra={"user_id": str(current_user.id), "job_id": str(job.id)},
                        exc_info=True
                    )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to queue Immich import job"
                )

        file_logger.info(
            f"Created async import job {job.id}: processing in background",
            extra={"user_id": str(current_user.id), "job_id": str(job.id)}
        )

        signed_media = [
            attach_signed_urls(
                EntryMediaResponse.model_validate(record),
                str(current_user.id),
                include_incomplete=True,
                external_base_url=immich_integration.base_url,
            )
            for record in placeholder_media
        ]

        file_logger.info(
            f"[IMMICH_IMPORT] Returning {len(signed_media)} signed media to frontend",
            extra={"count": len(signed_media)}
        )

        return ImmichImportStartResponse(
            job_id=job.id,
            status="processing",
            message=f"Import job started. Processing {len(request.asset_ids)} assets in background.",
            total_assets=len(request.asset_ids),
            media=signed_media,
        )

    except HTTPException:
        raise
    except Exception as e:
        error_logger.error(
            f"Failed to start async import: {e}",
            extra={"user_id": str(current_user.id)},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start import job"
        )


@router.get(
    "/import-jobs/{job_id}",
    response_model=ImmichImportJobResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Job not found"},
    }
)
async def get_import_job_status(
    job_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(_get_db_session)],
):
    """
    Get the status of an import job.

    Poll this endpoint to track progress of an async import.
    """
    import_service = ImportJobService(session)
    job = import_service.get_job(job_id, current_user.id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import job not found"
        )

    return ImmichImportJobResponse.model_validate(job)


@router.post(
    "/immich/repair-thumbnails",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Repair missing thumbnails for Immich media",
    description="""
    Manually trigger a background job to repair missing thumbnails for Immich media.

    **Purpose:**
    - Downloads thumbnails for EntryMedia records that have external_asset_id
      but missing thumbnail_path (e.g., from failed copy-mode imports)

    **Behavior:**
    - Processes all Immich media for the current user
    - Only repairs media with external_provider='immich' and missing thumbnail_path
    - Runs in background (returns immediately)
    - Updates EntryMedia records with thumbnail_path on success

    **Use Cases:**
    - Repair thumbnails after copy-mode import failures
    - Manual thumbnail refresh for existing Immich media
    - Recovery after thumbnail storage issues

    **Response:**
    - Returns immediately with job status
    - Check logs for repair progress
    """
)
async def repair_immich_thumbnails(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(_get_db_session)],
):
    """
    Repair missing thumbnails for Immich media.
    """
    from app.models.integration import Integration, IntegrationProvider
    from app.models.entry import Entry, EntryMedia
    from sqlmodel import select

    try:
        # Verify Immich integration exists and is active
        immich_integration = session.exec(
            select(Integration)
            .where(Integration.user_id == current_user.id)
            .where(Integration.provider == IntegrationProvider.IMMICH)
        ).first()

        if not immich_integration or not immich_integration.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Immich integration not connected or inactive"
            )

        # Find EntryMedia records that need thumbnail repair
        media_to_repair = session.exec(
            select(EntryMedia)
            .join(Entry, Entry.id == EntryMedia.entry_id)
            .where(Entry.user_id == current_user.id)
            .where(EntryMedia.external_provider == "immich")
            .where(EntryMedia.external_asset_id.isnot(None))
            .where(
                (EntryMedia.thumbnail_path.is_(None)) |
                (EntryMedia.thumbnail_path == "")
            )
        ).all()

        if not media_to_repair:
            return {
                "status": "completed",
                "message": "No media found that needs thumbnail repair",
                "scheduled_count": 0
            }

        # Schedule background task
        # Schedule background task using Celery to ensure fresh DB session
        try:
            celery_app.send_task(
                "app.tasks.immich.repair_thumbnails",
                args=[str(current_user.id), [str(m.external_asset_id) for m in media_to_repair if m.external_asset_id]]
            )
        except Exception as e:
            file_logger.error(
                "Failed to dispatch Immich thumbnail repair job",
                extra={"user_id": str(current_user.id), "error": str(e)},
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to start thumbnail repair"
            )

        file_logger.info(
            f"Scheduled thumbnail repair for {len(media_to_repair)} Immich media",
            extra={"user_id": str(current_user.id), "count": len(media_to_repair)}
        )

        return {
            "status": "accepted",
            "message": f"Thumbnail repair scheduled for {len(media_to_repair)} media items",
            "scheduled_count": len(media_to_repair)
        }

    except HTTPException:
        raise
    except Exception as e:
        error_logger.error(
            f"Failed to start thumbnail repair: {e}",
            extra={"user_id": str(current_user.id)},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start thumbnail repair"
        )


@router.post(
    "/process/{entry_id}",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Entry not found"},
        500: {"description": "Processing failed"},
    }
)
async def process_entry_media(
    entry_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(_get_db_session)]
):
    """
    Trigger media processing for an entry.

    Generates thumbnails for images and videos that don't have them yet.
    """
    media_service = _get_media_service()

    try:
        processed_count = await media_service.process_entry_media(
            entry_id, current_user.id, session
        )

        file_logger.info(
            f"Processed {processed_count} media files for entry",
            extra={"user_id": str(current_user.id), "entry_id": str(entry_id), "processed_count": processed_count}
        )

        return {
            "message": f"Processed {processed_count} media files",
            "entry_id": str(entry_id)
        }
    except EntryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        error_logger.error(
            "Unexpected error processing entry media",
            extra={"user_id": str(current_user.id), "entry_id": str(entry_id), "error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing media"
        )
