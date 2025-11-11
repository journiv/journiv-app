"""
Media upload and management endpoints.
"""
import inspect
import logging
import uuid
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Header, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core import database as database_module
from app.core.exceptions import (
    MediaNotFoundError,
    EntryNotFoundError,
    FileTooLargeError,
    InvalidFileTypeError,
    FileValidationError
)
from app.core.logging_config import LogCategory
from app.models.user import User
from app.schemas.entry import EntryMediaResponse
from app.services import media_service as media_service_module
from app.services.file_processing_service import FileProcessingService

file_logger = logging.getLogger(LogCategory.FILE_UPLOADS.value)
error_logger = logging.getLogger(LogCategory.ERRORS.value)
security_logger = logging.getLogger(LogCategory.SECURITY.value)

router = APIRouter()


def _get_media_service():
    return media_service_module.MediaService()


def _get_db_session():
    """Wrapper around database.get_session to allow easy patching in tests."""
    session_or_generator = database_module.get_session()
    if inspect.isgenerator(session_or_generator):
        yield from session_or_generator
    else:
        yield session_or_generator


def _send_bytes_range_requests(file_path: Path, start: int, end: int):
    """Generator function to send file bytes in range for streaming."""
    with open(file_path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining:
            chunk_size = min(8192, remaining)  # 8KB chunks
            chunk = f.read(chunk_size)
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk



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
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(_get_db_session)],
    file: UploadFile = File(...),
    entry_id: Optional[uuid.UUID] = Form(None),
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

        # Queue background processing if we have a real media record
        if media_record and hasattr(media_record, 'id') and full_file_path:
            try:
                processing_service = FileProcessingService(session)
                background_tasks.add_task(
                    processing_service.process_uploaded_file_async,
                    str(media_record.id),
                    full_file_path,
                    str(current_user.id)
                )
            except Exception as e:
                error_logger.warning(
                    "Failed to queue background processing task",
                    extra={"user_id": str(current_user.id), "media_id": str(media_record.id), "error": str(e)}
                )

        return EntryMediaResponse.model_validate(media_record)

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
    "/{media_id}",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive or forbidden"},
        404: {"description": "Media not found"},
        416: {"description": "Range Not Satisfiable"},
    }
)
async def get_media(
    media_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(_get_db_session)],
    range_header: Optional[str] = Header(None, alias="range")
):
    """Get media file by ID with proper Range request support for video streaming."""
    media_service = _get_media_service()

    try:
        file_info = media_service.get_media_file_for_serving(
            media_id, current_user.id, session, range_header
        )

        # Handle Range request
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

        # Return full file
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
            f"Error serving media file: {e}",
            extra={"user_id": str(current_user.id), "media_id": str(media_id)},
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to serve file")


@router.get(
    "/{media_id}/thumbnail",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive or forbidden"},
        404: {"description": "Thumbnail not found"},
    }
)
async def get_media_thumbnail(
    media_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(_get_db_session)]
):
    """Get media thumbnail by ID."""
    media_service = _get_media_service()

    try:
        media = media_service.get_media_by_id(media_id, current_user.id, session)
        thumbnail_path = media_service.get_media_thumbnail_path(media)

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
            "Error serving thumbnail",
            extra={"user_id": str(current_user.id), "media_id": str(media_id), "error": str(e)}
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
