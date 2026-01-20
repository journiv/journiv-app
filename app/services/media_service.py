"""
Media service for file upload and processing.
"""
import asyncio
import logging
import os
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional, Tuple

import magic
from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, select, or_

from app.core.config import get_settings
from app.core.exceptions import (
    MediaNotFoundError,
    FileTooLargeError,
    InvalidFileTypeError,
    InvalidMediaTypeError,
    FileValidationError,
    EntryNotFoundError
)
from app.core.logging_config import log_error, log_file_upload, log_info, log_warning
from app.models.entry import Entry, EntryMedia
from app.models.enums import MediaType, UploadStatus
from app.models.journal import Journal
from app.models.integration import Integration, IntegrationProvider
from app.utils.import_export.media_handler import MediaHandler
from app.services.media_storage_service import MediaStorageService
from app.core.media_signing import signed_url_for_journiv, signed_url_for_immich
from app.schemas.media import (
    MediaBatchSignRequest,
    MediaBatchSignResponse,
    MediaBatchSignResult,
    MediaBatchSignError
)

try:
    from PIL import Image
except ImportError:
    Image = None

# Structured logging
logger = logging.getLogger(__name__)
settings = get_settings()


class MediaService:
    """Service class for media operations."""

    # Constants for thumbnail and media processing
    THUMBNAIL_SIZE = (300, 300)
    THUMBNAIL_QUALITY = 85
    FFMPEG_DEFAULT_TIMEOUT = 300
    FFPROBE_DEFAULT_TIMEOUT = 300
    VIDEO_THUMBNAIL_SEEK_TIME = "00:00:01"

    # Use MediaHandler constants to avoid duplication
    MIME_TYPE_MAP = MediaHandler.MIME_TYPE_MAP
    IMAGE_EXTENSIONS = MediaHandler.IMAGE_EXTENSIONS
    VIDEO_EXTENSIONS = MediaHandler.VIDEO_EXTENSIONS
    AUDIO_EXTENSIONS = MediaHandler.AUDIO_EXTENSIONS

    def __init__(self, session: Optional[Session] = None):
        self.session = session
        self.settings = settings
        # Ensure media_root is always an absolute path to avoid path resolution issues
        self.media_root = Path(self.settings.media_root).resolve()
        self.media_root.mkdir(parents=True, exist_ok=True)

        # Initialize media storage service for unified storage
        self.media_storage_service = MediaStorageService(self.media_root, session)

        # Cache libmagic detector if available; fall back to best-effort detection
        try:
            self._magic = magic.Magic(mime=True)
        except Exception as exc:
            logger.warning("libmagic unavailable: %s", exc)
            self._magic = None

        # Build allowlists for MIME types and extensions from settings for configurability
        self.allowed_mime_types = {mime.lower() for mime in (self.settings.allowed_media_types or [])}
        self.allowed_extensions = {ext.lower() for ext in (self.settings.allowed_file_extensions or [])}

    def _get_session(self, session: Optional[Session]) -> Session:
        effective = session or self.session
        if effective is None:
            raise ValueError("Database session is required for this operation")
        return effective

    def _normalize_media_type(self, media_type: MediaType | str) -> str:
        """Normalize media type to lowercase string value."""
        if isinstance(media_type, MediaType):
            return media_type.value.lower()
        return str(media_type).lower()

    def _get_entry_for_user(
        self,
        session: Session,
        entry_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Entry:
        statement = (
            select(Entry)
            .where(
                Entry.id == entry_id,
                Entry.user_id == user_id,
            )
        )
        entry = session.exec(statement).first()
        if not entry:
            log_warning(f"Entry not found for user {user_id}: {entry_id}")
            raise EntryNotFoundError("Entry not found")
        return entry

    def _get_media_path(self, filename: str, media_type: MediaType | str) -> Path:
        """Get the full path for a media file."""
        media_type_lower = self._normalize_media_type(media_type)
        if media_type_lower == "image":
            return self.media_root / "images" / filename
        elif media_type_lower == "video":
            return self.media_root / "videos" / filename
        elif media_type_lower == "audio":
            return self.media_root / "audio" / filename
        else:
            return self.media_root / filename

    def _get_thumbnail_path(
        self,
        filename: str,
        media_type: Optional[MediaType | str] = None,
        user_id: Optional[str] = None
    ) -> Optional[Path]:
        """Get the thumbnail path for a media file in standardized format.

        Returns None for media types that cannot generate thumbnails.
        """
        if media_type is None:
            return None

        media_type_lower = self._normalize_media_type(media_type)
        if user_id:
            if '/' in user_id or '\\' in user_id or '..' in user_id:
                raise ValueError("user_id contains invalid path characters")
            if media_type_lower == "image":
                return self.media_root / user_id / "images" / "thumbnails" / filename
            elif media_type_lower == "video":
                return self.media_root / user_id / "videos" / "thumbnails" / filename
            elif media_type_lower == "audio":
                return self.media_root / user_id / "audio" / "thumbnails" / filename
            else:
                return None

        if media_type_lower == "image":
            return self.media_root / "images" / "thumbnails" / filename
        elif media_type_lower == "video":
            return self.media_root / "videos" / "thumbnails" / filename
        elif media_type_lower == "audio":
            return self.media_root / "audio" / "thumbnails" / filename
        else:
            # Unknown media types cannot generate thumbnails
            return None

    def _detect_mime(self, file_content: bytes) -> str:
        try:
            return magic.from_buffer(file_content, mime=True)
        except Exception:
            if self._magic is not None:
                try:
                    return self._magic.from_buffer(file_content)
                except Exception as exc:
                    logger.warning("Failed to detect MIME type with libmagic: %s", exc)
        return "application/octet-stream"

    def _generate_filename(self, original_filename: str, user_id: str) -> str:
        """Generate a unique filename with sanitized original name."""
        safe_original = MediaHandler.sanitize_filename(original_filename)
        file_extension = Path(safe_original).suffix.lower()
        unique_id = str(uuid.uuid4())
        return f"{user_id}_{unique_id}{file_extension}"

    async def save_uploaded_file(
        self,
        original_filename: str,
        user_id: str,
        media_type: MediaType,
        file_content: Optional[bytes] = None,
        file_path: Optional[str] = None,
        file_stream: Optional[BinaryIO] = None,
        file_size_override: Optional[int] = None,
        mime_type_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save an uploaded file using unified MediaStorageService.

        Args:
            original_filename: Original filename from upload
            user_id: User UUID string
            media_type: MediaType enum
            file_content: File content as bytes (optional)
            file_path: Path to file on disk (optional, for large files)
            file_stream: File-like object for streaming uploads (optional)
            file_size_override: Optional size override for file_stream (bytes)
            mime_type_override: Optional MIME type override (used with file_stream)

        Returns:
            Dict with file metadata
        """
        if not file_content and not file_path and file_stream is None:
            raise ValueError("Either file_content, file_path, or file_stream must be provided")
        if sum(bool(value) for value in (file_content, file_path, file_stream)) > 1:
            raise ValueError("Only one of file_content, file_path, or file_stream can be provided")

        # Determine media type directory
        media_type_lower = self._normalize_media_type(media_type)
        if media_type_lower == "image":
            media_type_dir = "images"
        elif media_type_lower == "video":
            media_type_dir = "videos"
        elif media_type_lower == "audio":
            media_type_dir = "audio"
        else:
            raise InvalidMediaTypeError(
                f"Invalid or unrecognized media type: original={media_type!r}, normalized={media_type_lower!r}"
            )

        # Get file extension
        safe_original = MediaHandler.sanitize_filename(original_filename)
        extension = Path(safe_original).suffix or ".bin"

        # Prepare source stream
        source_stream = None
        should_close_stream = False

        try:
            if file_path:
                file_obj = Path(file_path)
                if not file_obj.exists():
                    raise ValueError(f"File not found: {file_path}")
                file_size = file_obj.stat().st_size
                source_stream = file_obj.open('rb')
                should_close_stream = True
                header = source_stream.read(2048)
                source_stream.seek(0)
                mime_type = self._detect_mime(header)
            elif file_stream is not None:
                source_stream = file_stream
                should_close_stream = False
                if file_size_override is not None:
                    file_size = file_size_override
                else:
                    try:
                        if source_stream.seekable():
                            source_stream.seek(0, 2)
                            file_size = source_stream.tell()
                            source_stream.seek(0)
                        else:
                            raise ValueError("file_size_override required for non-seekable streams")
                    except Exception as exc:
                        raise ValueError(f"Failed to determine stream size: {exc}") from exc
                if mime_type_override:
                    mime_type = mime_type_override
                else:
                    if not source_stream.seekable():
                        raise ValueError("mime_type_override required for non-seekable streams")
                    header = source_stream.read(2048)
                    source_stream.seek(0)
                    mime_type = self._detect_mime(header)
            else:
                source_stream = BytesIO(file_content)
                file_size = len(file_content)
                mime_type = self._detect_mime(file_content)

            # Store using storage service (per-user deduplication)
            # Run synchronously - file I/O is blocking anyway
            relative_path, checksum, was_deduplicated = await asyncio.to_thread(
                self.media_storage_service.store_media,
                source=source_stream,
                user_id=user_id,
                media_type=media_type_dir,
                extension=extension,
                checksum=None  # Will be calculated
            )

            full_file_path = self.media_storage_service.get_full_path(relative_path)

            return {
                "filename": Path(relative_path).name,
                "file_path": relative_path,
                "original_filename": safe_original,
                "file_size": file_size,
                "mime_type": mime_type,
                "thumbnail_path": None,  # Will be generated in background
                "media_type": media_type,
                "upload_status": UploadStatus.PENDING,
                "checksum": checksum,
                "full_file_path": str(full_file_path),  # For background processing
                "was_deduplicated": was_deduplicated
            }
        finally:
            if should_close_stream and source_stream:
                source_stream.close()

    async def get_media_info(self, file_path: str) -> Dict[str, Any]:
        """Get detailed information about a media file."""
        path = Path(file_path)
        if not path.exists():
            raise MediaNotFoundError("Media file not found")

        # Get file stats
        stat = path.stat()
        file_size = stat.st_size

        # Get MIME type
        try:
            mime_type = magic.from_file(str(path), mime=True)
        except Exception:
            if self._magic is not None:
                try:
                    mime_type = self._magic.from_file(str(path))
                except Exception:
                    mime_type = "application/octet-stream"
            else:
                mime_type = "application/octet-stream"

        # Get media type from MIME type, falling back to extension when needed
        suffix = path.suffix.lower()
        if mime_type.startswith('image/'):
            media_type = MediaType.IMAGE
        elif mime_type.startswith('video/'):
            media_type = MediaType.VIDEO
        elif mime_type.startswith('audio/'):
            media_type = MediaType.AUDIO
        else:
            # Fallback to extension-based detection using class constants
            if suffix in self.IMAGE_EXTENSIONS:
                media_type = MediaType.IMAGE
                mime_type = self.MIME_TYPE_MAP.get(suffix, "image/jpeg")
            elif suffix in self.VIDEO_EXTENSIONS:
                media_type = MediaType.VIDEO
                mime_type = self.MIME_TYPE_MAP.get(suffix, "video/mp4")
            elif suffix in self.AUDIO_EXTENSIONS:
                media_type = MediaType.AUDIO
                mime_type = self.MIME_TYPE_MAP.get(suffix, "audio/mpeg")
            else:
                media_type = MediaType.UNKNOWN
                mime_type = "application/octet-stream"

        # Get dimensions for images and videos
        width = None
        height = None
        duration = None

        if media_type == MediaType.IMAGE and Image is not None:
            try:
                with Image.open(path) as img:
                    width, height = img.size
            except Exception:
                pass
        elif media_type == MediaType.VIDEO:
            # Extract video dimensions using helper method
            dimensions = self._get_video_dimensions(path)
            if dimensions:
                width = dimensions.get("width")
                height = dimensions.get("height")

        return {
            "file_path": str(path),
            "file_size": file_size,
            "mime_type": mime_type,
            "media_type": media_type,
            "width": width,
            "height": height,
            "duration": duration,
            "created_at": datetime.fromtimestamp(stat.st_ctime),
            "modified_at": datetime.fromtimestamp(stat.st_mtime)
        }

    def _validate_file_internal(self, file_content: bytes, filename: str) -> Tuple[bool, str]:
        """Core validation logic shared by all validation methods.

        This centralizes file size, MIME type, and extension validation.
        """
        try:
            # Check file size using shared utility
            if not MediaHandler.validate_file_size(len(file_content), self.settings.max_file_size_mb):
                return False, f"File size exceeds maximum limit of {self.settings.max_file_size_mb}MB"

            # Get allowed types (from settings or cached)
            allowed_mime_types = {mime.lower() for mime in (self.settings.allowed_media_types or [])} or self.allowed_mime_types
            allowed_extensions = {ext.lower() for ext in (self.settings.allowed_file_extensions or [])} or self.allowed_extensions

            # Check MIME type
            mime_type = self._detect_mime(file_content)
            if allowed_mime_types and mime_type.lower() not in allowed_mime_types:
                return False, f"Mime type {mime_type} not allowed"

            # Check file extension
            file_ext = Path(filename).suffix.lower()
            if allowed_extensions and file_ext not in allowed_extensions:
                return False, f"File extension {file_ext} not allowed"

            return True, "File is valid"
        except Exception as exc:
            log_error(exc, request_id="", user_email="")
            return False, "File validation failed"

    def validate_file_sync(self, file_content: bytes, filename: str) -> Tuple[bool, str]:
        """Validate file content and extension synchronously.

        This is the core validation logic used by both sync and async methods.
        """
        return self._validate_file_internal(file_content, filename)

    async def validate_file(self, file_content: bytes, filename: str) -> Tuple[bool, str]:
        """Async wrapper for validate_file_sync."""
        return self._validate_file_internal(file_content, filename)

    def get_supported_formats(self) -> Dict[str, list]:
        """Get supported file formats from configuration."""
        # Group extensions by media type using class constants
        formats = {"images": [], "videos": [], "audio": []}

        # Map extensions to media types based on class constants
        for ext in self.allowed_extensions:
            ext_lower = ext.lower()
            if ext_lower in self.IMAGE_EXTENSIONS:
                formats["images"].append(ext)
            elif ext_lower in self.VIDEO_EXTENSIONS:
                formats["videos"].append(ext)
            elif ext_lower in self.AUDIO_EXTENSIONS:
                formats["audio"].append(ext)

        return formats

    async def _check_file_size(self, file: UploadFile) -> None:
        """Check if file size is within limits."""
        if hasattr(file, 'size') and file.size:
            if not MediaHandler.validate_file_size(file.size, self.settings.max_file_size_mb):
                raise FileTooLargeError(
                    f"File too large. Maximum size: {self.settings.max_file_size_mb}MB"
                )

    async def _read_file_content(self, file: UploadFile) -> bytes:
        """Read file content from UploadFile."""
        try:
            content = await file.read()
            return content
        except Exception as e:
            log_error(e, request_id="", user_email="")
            raise FileValidationError("Failed to read file")

    def _validate_file_content(self, file_content: bytes, filename: str) -> None:
        """Validate file content and raise appropriate exceptions if invalid.

        This method uses the centralized validation logic and converts
        the result to appropriate exceptions.
        """
        is_valid, error_message = self._validate_file_internal(file_content, filename)

        if not is_valid:
            # Convert validation message to appropriate exception
            normalized_msg = (error_message or "").lower()
            if "file size" in normalized_msg or "exceeds" in normalized_msg:
                raise FileTooLargeError(error_message)
            elif "mime type" in normalized_msg:
                raise InvalidFileTypeError(error_message)
            elif "extension" in normalized_msg:
                raise FileValidationError(error_message)
            else:
                # Generic validation error
                raise FileValidationError(error_message or "File validation failed")

    def _validate_streamed_upload(self, file_size: int, filename: str, header_bytes: bytes) -> None:
        """Validate size, MIME type, and extension for streamed uploads."""
        if not MediaHandler.validate_file_size(file_size, self.settings.max_file_size_mb):
            raise FileTooLargeError(
                f"File size exceeds maximum limit of {self.settings.max_file_size_mb}MB"
            )

        allowed_mime_types = {mime.lower() for mime in (self.settings.allowed_media_types or [])} or self.allowed_mime_types
        allowed_extensions = {ext.lower() for ext in (self.settings.allowed_file_extensions or [])} or self.allowed_extensions

        mime_type = self._detect_mime(header_bytes)
        if allowed_mime_types and mime_type.lower() not in allowed_mime_types:
            raise InvalidFileTypeError(f"Mime type {mime_type} not allowed")

        file_ext = Path(filename).suffix.lower()
        if allowed_extensions and file_ext not in allowed_extensions:
            raise FileValidationError(f"File extension {file_ext} not allowed")

    def _detect_media_type(self, file_content: bytes) -> MediaType:
        """Detect media type from file content."""
        try:
            mime_type = self._detect_mime(file_content)

            if mime_type.startswith('image/'):
                return MediaType.IMAGE
            elif mime_type.startswith('video/'):
                return MediaType.VIDEO
            elif mime_type.startswith('audio/'):
                return MediaType.AUDIO
            else:
                raise InvalidFileTypeError("Unsupported media type")
        except Exception as e:
            if isinstance(e, InvalidFileTypeError):
                raise
            log_error(e, request_id="", user_email="")
            raise FileValidationError("Failed to determine media type")

    async def upload_media(
        self,
        file: UploadFile,
        user_id: uuid.UUID,
        entry_id: uuid.UUID,
        alt_text: Optional[str] = None,
        session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Upload and process a media file.

        This is the main entry point for media upload that handles all business logic.

        Args:
            file: The uploaded file
            user_id: ID of the user uploading the file
            entry_id: ID of the entry to attach media to
            alt_text: Optional alt text for the media
            session: Optional database session for creating media record

        Returns:
            Dict containing media information or database record

        Raises:
            FileTooLargeError: If file exceeds size limit
            FileValidationError: If file validation fails
            InvalidFileTypeError: If file type is not supported
            EntryNotFoundError: If entry doesn't exist
        """
        # 1. Check file size before reading (if provided by upload implementation)
        await self._check_file_size(file)

        # 2. Prefer single-write streaming when the underlying file is seekable
        filename = file.filename or "unknown"
        source_stream = file.file
        file_size = file.size if hasattr(file, "size") and file.size else None
        header_bytes = b""
        use_temp_fallback = not source_stream.seekable()

        if not use_temp_fallback:
            try:
                if file_size is None:
                    source_stream.seek(0, 2)
                    file_size = source_stream.tell()
                    source_stream.seek(0)
                header_bytes = source_stream.read(2048)
                source_stream.seek(0)
            except Exception:
                use_temp_fallback = True

        if file_size is None:
            use_temp_fallback = True

        temp_file = None
        temp_path = None
        if use_temp_fallback:
            if source_stream.seekable():
                try:
                    source_stream.seek(0)
                except Exception:
                    pass
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_path = Path(temp_file.name)
            file_size = 0
            header_bytes = b""
            max_bytes = self.settings.max_file_size_mb * 1024 * 1024

            try:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    if not header_bytes:
                        header_bytes = chunk[:2048]
                    file_size += len(chunk)
                    if file_size > max_bytes:
                        raise FileTooLargeError(
                            f"File size exceeds maximum limit of {self.settings.max_file_size_mb}MB"
                        )
                    temp_file.write(chunk)
            finally:
                if temp_file is not None:
                    temp_file.close()

        try:
            if use_temp_fallback:
                self._validate_streamed_upload(file_size, filename, header_bytes)
                media_type = self._detect_media_type(header_bytes)
            else:
                self._validate_streamed_upload(file_size, filename, header_bytes)
                media_type = self._detect_media_type(header_bytes)

            # 5. Verify entry exists and belongs to user
            db_session = self._get_session(session)
            self._get_entry_for_user(db_session, entry_id, user_id)

            # 6. Save file
            if use_temp_fallback:
                media_info = await self.save_uploaded_file(
                    original_filename=filename,
                    user_id=str(user_id),
                    media_type=media_type,
                    file_path=str(temp_path)
                )
            else:
                media_info = await self.save_uploaded_file(
                    original_filename=filename,
                    user_id=str(user_id),
                    media_type=media_type,
                    file_stream=source_stream,
                    file_size_override=file_size,
                    mime_type_override=self._detect_mime(header_bytes)
                )
        finally:
            if use_temp_fallback and temp_path is not None and temp_path.exists():
                temp_path.unlink()

        media_record = None
        db_session = self._get_session(session)

        # Check if EntryMedia record already exists for this entry and checksum
        # This prevents duplicate media within the same entry
        checksum = media_info.get("checksum")
        if checksum and isinstance(checksum, str) and checksum.strip():
            existing_entry_media = db_session.exec(
                select(EntryMedia).where(
                    EntryMedia.entry_id == entry_id,
                    EntryMedia.checksum == checksum
                )
            ).first()

            if existing_entry_media:
                log_info(
                    "Media already associated with entry, returning existing record",
                    user_id=str(user_id),
                    entry_id=str(entry_id),
                    checksum=checksum[:16] if checksum else None,
                    media_id=str(existing_entry_media.id)
                )
                full_file_path = self.media_storage_service.get_full_path(existing_entry_media.file_path)
                return {
                    "media_record": existing_entry_media,
                    "full_file_path": str(full_file_path),
                }

        # If file was deduplicated, try to find existing media with same checksum
        existing_media = None
        if media_info.get("was_deduplicated"):
            stmt = (
                select(EntryMedia)
                .join(Entry)
                .join(Journal)
                .where(
                    EntryMedia.checksum == media_info["checksum"],
                    Journal.user_id == user_id
                )
            )
            existing_media = db_session.exec(stmt).first()

        if existing_media:
            # Reuse existing media metadata, create new record for this entry
            media_record = EntryMedia(
                entry_id=entry_id,
                media_type=existing_media.media_type,
                file_path=existing_media.file_path,
                original_filename=media_info["original_filename"],
                file_size=existing_media.file_size,
                mime_type=existing_media.mime_type,
                thumbnail_path=existing_media.thumbnail_path,
                alt_text=alt_text,
                upload_status=existing_media.upload_status,
                file_metadata=existing_media.file_metadata,
                checksum=existing_media.checksum,
                width=existing_media.width,
                height=existing_media.height,
                duration=existing_media.duration,
            )
            log_info(
                "Reused deduplicated media",
                user_id=str(user_id),
                checksum=media_info['checksum'][:16] if media_info.get('checksum') else None
            )
        else:
            # Create new media record
            media_record = EntryMedia(
                entry_id=entry_id,
                media_type=media_type,
                file_path=media_info["file_path"],
                original_filename=media_info["original_filename"],
                file_size=media_info["file_size"],
                mime_type=media_info["mime_type"],
                thumbnail_path=media_info["thumbnail_path"],
                alt_text=alt_text,
                upload_status=UploadStatus.PENDING,
                file_metadata=media_info.get("file_metadata"),
                checksum=media_info.get("checksum"),
            )

        try:
            db_session.add(media_record)
            db_session.commit()
            db_session.refresh(media_record)
        except IntegrityError as exc:
            db_session.rollback()
            # Check if this is the duplicate entry_media constraint violation
            error_str = str(exc)
            if "uq_entry_media_entry_checksum" in error_str:
                # Race condition: media was created by concurrent request
                checksum_value = media_info.get("checksum")
                if checksum_value:
                    existing = db_session.exec(
                        select(EntryMedia).where(
                            EntryMedia.entry_id == entry_id,
                            EntryMedia.checksum == checksum_value
                        )
                    ).first()
                    if existing:
                        log_info(
                            "Media already associated with entry (race condition), using existing record",
                            user_id=str(user_id),
                            entry_id=str(entry_id),
                            checksum=checksum_value[:16] if len(checksum_value) >= 16 else checksum_value,
                            media_id=str(existing.id)
                        )
                        full_file_path = self.media_storage_service.get_full_path(existing.file_path)
                        return {
                            "media_record": existing,
                            "full_file_path": str(full_file_path),
                        }
                # If checksum is missing or existing record not found, log and re-raise
                log_warning(
                    "IntegrityError for entry_media constraint but existing record not found",
                    user_id=str(user_id),
                    entry_id=str(entry_id),
                    checksum=checksum_value[:16] if checksum_value and len(checksum_value) >= 16 else None
                )
            # Re-raise if it's a different IntegrityError or existing record not found
            raise
        except SQLAlchemyError as exc:
            db_session.rollback()
            log_error(exc)
            # Only delete file if it wasn't deduplicated
            if not media_info.get("was_deduplicated"):
                # Force delete since DB record was never committed
                try:
                    self.media_storage_service.delete_media(
                        relative_path=media_info["file_path"],
                        checksum=media_info["checksum"],
                        user_id=str(user_id),
                        force=True  # Force deletion since no DB record exists
                    )
                except Exception as delete_exc:
                    log_warning(f"Failed to cleanup uploaded file after DB error: {delete_exc}")
            raise

        log_file_upload(
            media_record.original_filename or media_record.file_path,
            media_info["file_size"],
            True,
            request_id="",
            user_email=str(user_id),
        )
        return {
            "media_record": media_record,
            "full_file_path": media_info["full_file_path"],
        }

    def _commit(self) -> None:
        """Commit database changes with proper error handling."""
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    def _get_media_by_id(self, media_id: str, user_id: str) -> EntryMedia:
        """Get media record by ID with ownership validation."""
        try:
            media_uuid = uuid.UUID(media_id)
        except ValueError:
            raise MediaNotFoundError("Invalid media ID format")

        statement = select(EntryMedia).join(Entry).where(
            EntryMedia.id == media_uuid,
            Entry.user_id == uuid.UUID(user_id),
        )

        media = self.session.exec(statement).first()
        if not media:
            log_warning(f"Media not found for user {user_id}: {media_id}")
            raise MediaNotFoundError("Media not found")
        return media


    def process_uploaded_file(self, media_id: str, file_path: str, user_id: str) -> None:
        """
        Process uploaded media file with metadata extraction and thumbnail generation.

        Args:
            media_id: UUID of the media record
            file_path: Absolute or relative path to the uploaded file
            user_id: ID of the user who uploaded the file
        """
        try:
            # Validate inputs
            if not media_id or not file_path or not user_id:
                raise ValueError("media_id, file_path, and user_id are required")

            # Get media record with ownership validation
            media = self._get_media_by_id(media_id, user_id)

            # If media is already completed, skip re-processing to avoid race conditions
            # in duplicate uploads and unnecessary work
            if media.upload_status == UploadStatus.COMPLETED:
                log_info("Media already completed, skipping re-processing", media_id=media_id, user_id=user_id)
                return

            # Update status to processing with transaction isolation
            try:
                media.processing_error = None
                media.upload_status = UploadStatus.PROCESSING
                media.updated_at = datetime.now(timezone.utc)
                self.session.add(media)
                self.session.flush()  # Ensure changes are visible immediately
                self._commit()
            except Exception as e:
                self.session.rollback()
                raise

            # Resolve file path with error handling
            try:
                actual_file_path = self._resolve_file_path(file_path, media.file_path)
            except Exception as e:
                error_message = f"Failed to resolve file path: {e}"
                log_error(error_message, media_id=media_id, user_id=user_id)
                self._mark_processing_failed(media_id, error_message)
                return

            if not actual_file_path.exists():
                error_message = f"Uploaded file not found at {actual_file_path}"
                log_error(error_message, media_id=media_id, user_id=user_id)
                self._mark_processing_failed(media_id, error_message)
                return

            # Extract metadata with error handling
            try:
                metadata = self._extract_metadata_sync(actual_file_path)
            except Exception as e:
                error_message = f"Failed to extract metadata: {e}"
                log_error(error_message, media_id=media_id, user_id=user_id)
                self._mark_processing_failed(media_id, error_message)
                return

            # Generate thumbnail with error handling
            thumbnail_path = None
            media_type_value = metadata.get('media_type')
            try:
                has_existing_thumbnail = False
                if media.thumbnail_path:
                    full_thumbnail_path = (self.media_root / media.thumbnail_path).resolve()
                    try:
                        full_thumbnail_path.relative_to(self.media_root.resolve())
                        if full_thumbnail_path.exists():
                            has_existing_thumbnail = True
                    except ValueError:
                        # Path is not within media_root
                        pass

                if not has_existing_thumbnail:
                    media_type_enum = MediaType(media_type_value)
                    if media_type_enum in {MediaType.IMAGE, MediaType.VIDEO}:
                        try:
                            thumbnail_path = self._generate_thumbnail(str(actual_file_path), media_type_enum)
                        except Exception as e:
                            log_warning(f"Thumbnail generation failed for {media_id}: {e}",
                                      media_id=media_id, user_id=user_id)
                            # Continue without thumbnail - not critical
            except Exception:
                # Invalid media type - skip thumbnail generation
                pass

            # Update database with processed data in a transaction
            try:
                self.session.begin_nested()  # Create savepoint for atomic update
                self._update_media_metadata(media_id, metadata, thumbnail_path)
                self.session.commit()  # Commit the nested transaction
                log_file_upload(
                    media.original_filename or media.file_path,
                    media.file_size or 0,
                    True,
                    request_id="",
                    user_email=user_id,
                )
            except Exception as e:
                self.session.rollback()
                error_message = f"Failed to update media metadata: {e}"
                log_error(error_message, media_id=media_id, user_id=user_id)
                self._mark_processing_failed(media_id, error_message)

        except Exception as e:
            log_error(f"File processing failed for {media_id}: {e}",
                     media_id=media_id, user_id=user_id, exc_info=True)
            try:
                self._mark_processing_failed(media_id, str(e))
            except Exception as mark_error:
                log_error(f"Failed to mark processing as failed for {media_id}: {mark_error}",
                         media_id=media_id, user_id=user_id)

    def _resolve_file_path(self, passed_path: Optional[str], db_relative_path: str) -> Path:
        """
        Resolve the on-disk location of the uploaded file.

        Args:
            passed_path: Path provided by the caller (absolute or relative)
            db_relative_path: Relative path stored in the database

        Returns:
            pathlib.Path to the file location.
        """
        if passed_path:
            candidate = Path(passed_path)
            if not candidate.is_absolute():
                candidate = self.media_root / candidate
            return candidate

        return self.media_root / db_relative_path

    def _extract_metadata_sync(self, file_path: Path) -> Dict[str, Any]:
        """Synchronous metadata extraction."""
        try:
            # Get MIME type
            if self._magic:
                mime_type = self._magic.from_file(str(file_path))
            else:
                # Fallback to file extension detection
                mime_type = self._get_mime_type_from_extension(file_path)

            # Determine media type
            if mime_type.startswith('image/'):
                media_type = "image"
                dimensions = self._get_image_dimensions(file_path)
            elif mime_type.startswith('video/'):
                media_type = "video"
                dimensions = self._get_video_dimensions(file_path)
            elif mime_type.startswith('audio/'):
                media_type = "audio"
                dimensions = None
            else:
                media_type = MediaType.UNKNOWN.value  # Default to unknown for unrecognized types
                dimensions = None

            return {
                "media_type": media_type,
                "mime_type": mime_type,
                "dimensions": dimensions
            }

        except Exception as e:
            log_error(f"Failed to extract metadata from {file_path}: {e}")
            return {
                "media_type": MediaType.UNKNOWN.value,  # Default to unknown for unrecognized types
                "mime_type": "application/octet-stream",
                "dimensions": None
            }

    def _get_mime_type_from_extension(self, file_path: Path) -> str:
        """Fallback MIME type detection from file extension using class constants."""
        extension = file_path.suffix.lower()
        return self.MIME_TYPE_MAP.get(extension, 'application/octet-stream')

    def _get_image_dimensions(self, file_path: Path) -> Optional[Dict[str, int]]:
        """Get image dimensions."""
        if not Image:
            return None

        try:
            with Image.open(file_path) as img:
                return {"width": img.width, "height": img.height}
        except Exception as e:
            log_error(f"Failed to get image dimensions: {e}")
            return None

    def _get_video_dimensions(self, file_path: Path) -> Optional[Dict[str, int]]:
        """Get video dimensions using FFprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", "-select_streams", "v:0",
                str(file_path)
            ]

            # Use configurable timeout from settings or class constant
            timeout = getattr(self.settings, 'ffprobe_timeout', self.FFPROBE_DEFAULT_TIMEOUT)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                if data.get('streams'):
                    stream = data['streams'][0]
                    return {
                        "width": stream.get('width', 0),
                        "height": stream.get('height', 0)
                    }
        except subprocess.TimeoutExpired:
            log_error(f"FFprobe timeout for {file_path}")
        except Exception as e:
            log_error(f"Failed to get video dimensions: {e}")

        return None

    def _generate_thumbnail(self, file_path: str, media_type: MediaType | str) -> Optional[str]:
        """Generate thumbnail synchronously."""
        file_path_obj = Path(file_path)

        # Determine thumbnail directory based on media type
        media_type_value = media_type.value if isinstance(media_type, MediaType) else media_type

        if media_type_value == "image":
            thumbnail_dir = file_path_obj.parent / "thumbnails"
            thumbnail_path = thumbnail_dir / f"thumb_{file_path_obj.name}"
            self._generate_image_thumbnail(file_path_obj, thumbnail_path)
        elif media_type_value == "video":
            thumbnail_dir = file_path_obj.parent / "thumbnails"
            thumbnail_name = file_path_obj.stem
            thumbnail_path = thumbnail_dir / f"thumb_{thumbnail_name}.jpg"
            self._generate_video_thumbnail(file_path_obj, thumbnail_path)
        else:
            return None

        return str(thumbnail_path)

    def _generate_image_thumbnail(self, image_path: Path, thumbnail_path: Path):
        """Generate image thumbnail using PIL."""
        if not Image:
            raise Exception("PIL not available for image thumbnail generation")

        try:
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')

                # Create thumbnail using class constants
                img.thumbnail(self.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                img.save(thumbnail_path, "JPEG", quality=self.THUMBNAIL_QUALITY, optimize=True)
        except Exception as e:
            log_error(f"Failed to generate image thumbnail: {e}")
            raise

    def _generate_video_thumbnail(self, video_path: Path, thumbnail_path: Path):
        """Generate video thumbnail using FFmpeg."""
        try:
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

            cmd = [
                "ffmpeg",
                "-threads", "1",           # Use single thread to minimize memory usage
                "-hide_banner",            # Suppress banner
                "-loglevel", "error",      # Suppress warnings
                "-nostats",                # Suppress stats
                "-ss", self.VIDEO_THUMBNAIL_SEEK_TIME, # Seek BEFORE input (fast seek / input seeking)
                "-i", str(video_path),
                "-vframes", "1",
                "-vf", f"scale={self.THUMBNAIL_SIZE[0]}:{self.THUMBNAIL_SIZE[1]}",
                "-f", "image2",
                "-y",
                str(thumbnail_path)
            ]

            # Use configurable timeout from settings or class constant
            timeout = getattr(self.settings, 'ffmpeg_timeout', self.FFMPEG_DEFAULT_TIMEOUT)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

            if result.returncode != 0:
                # If we still fail, log the stderr but truncate if too long
                err_msg = result.stderr[:1000] + "..." if len(result.stderr) > 1000 else result.stderr
                log_error(f"FFmpeg failed: {err_msg}")
                raise Exception(f"FFmpeg failed with return code {result.returncode}")

        except subprocess.TimeoutExpired:
            log_error(f"FFmpeg timeout for {video_path}")
            raise Exception("FFmpeg timeout")
        except Exception as e:
            log_error(f"Failed to generate video thumbnail: {e}")
            raise

    def _update_media_metadata(self, media_id: str, metadata: Dict[str, Any], thumbnail_path: Optional[str]):
        """Update media record with processed metadata."""
        try:
            media_uuid = uuid.UUID(media_id)
            media = self.session.get(EntryMedia, media_uuid)
            if not media:
                log_error(f"Media record not found: {media_id}")
                return

            # Update metadata
            media_type_value = metadata["media_type"]
            try:
                media.media_type = MediaType(media_type_value)
            except Exception:
                media.media_type = media_type_value
            media.mime_type = metadata["mime_type"]
            media.upload_status = UploadStatus.COMPLETED
            media.processing_error = None
            media.updated_at = datetime.now(timezone.utc)

            # Update dimensions if available
            if metadata.get("dimensions"):
                media.width = metadata["dimensions"].get("width")
                media.height = metadata["dimensions"].get("height")

            # Update thumbnail path if generated
            if thumbnail_path:
                media.thumbnail_path = self._relative_thumbnail_path(Path(thumbnail_path))

            self.session.add(media)
            self._commit()

        except Exception as e:
            log_error(f"Failed to update media metadata for {media_id}: {e}")
            raise

    def _mark_processing_failed(self, media_id: str, error_message: str):
        """Mark media processing as failed."""
        try:
            media_uuid = uuid.UUID(media_id)
            media = self.session.get(EntryMedia, media_uuid)
            if media:
                media.upload_status = UploadStatus.FAILED
                media.processing_error = error_message
                media.updated_at = datetime.now(timezone.utc)
                self.session.add(media)
                self._commit()
        except Exception as e:
            log_error(f"Failed to mark processing as failed for {media_id}: {e}")

    def _relative_thumbnail_path(self, path: Path) -> str:
        """Convert absolute thumbnail path to a path relative to the media root."""
        try:
            resolved_path = path.resolve()
            resolved_root = self.media_root.resolve()
            return str(resolved_path.relative_to(resolved_root))
        except ValueError as e:
            # Path is not relative to media_root - log warning and return absolute path
            log_warning(f"Thumbnail path {path} is not within media_root {self.media_root}: {e}")
            return str(path)
        except Exception as e:
            # Unexpected error - log and return original path
            log_error(f"Failed to resolve thumbnail path {path}: {e}")
            return str(path)

    def get_media_by_id(self, media_id: uuid.UUID, user_id: uuid.UUID, session: Session) -> EntryMedia:
        """Get media record by ID with ownership validation.

        Args:
            media_id: UUID of the media record
            user_id: UUID of the user requesting the media
            session: Database session

        Returns:
            EntryMedia record

        Raises:
            MediaNotFoundError: If media not found or user doesn't have access
        """
        statement = select(EntryMedia).join(Entry).where(
            EntryMedia.id == media_id,
            Entry.user_id == user_id,
        )
        media = session.exec(statement).first()
        if not media:
            raise MediaNotFoundError("Media not found")
        return media

    def get_media_file_path(self, media: EntryMedia) -> Path:
        """Get the full file path for a media record with validation.

        Args:
            media: EntryMedia record

        Returns:
            Path object to the media file

        Raises:
            MediaNotFoundError: If file doesn't exist
        """
        if not media.file_path:
            raise MediaNotFoundError("Media file not available")

        root = self.media_root.resolve()
        full_path = (root / media.file_path).resolve()

        # Validate path to prevent directory traversal
        try:
            full_path.relative_to(root)
        except ValueError:
            raise MediaNotFoundError("Invalid file path")

        if not full_path.exists():
            raise MediaNotFoundError("Media file not found")

        return full_path

    def get_media_thumbnail_path(self, media: EntryMedia) -> Path:
        """Get the full thumbnail path for a media record with validation.

        Args:
            media: EntryMedia record

        Returns:
            Path object to the thumbnail file

        Raises:
            MediaNotFoundError: If thumbnail doesn't exist
        """
        if not media.thumbnail_path:
            raise MediaNotFoundError("Thumbnail not found")

        root = self.media_root.resolve()
        full_path = (root / media.thumbnail_path).resolve()

        # Validate path to prevent directory traversal
        try:
            full_path.relative_to(root)
        except ValueError:
            raise MediaNotFoundError("Invalid thumbnail path")

        if not full_path.exists():
            raise MediaNotFoundError("Thumbnail not found")

        return full_path

    async def delete_media_by_id(self, media_id: uuid.UUID, user_id: uuid.UUID, session: Session) -> None:
        """Delete media by ID including database record and filesystem file.

        Args:
            media_id: UUID of the media to delete
            user_id: UUID of the user requesting deletion
            session: Database session

        Raises:
            MediaNotFoundError: If media not found or user doesn't have access
        """
        from app.services import entry_service as entry_service_module

        # Get media record first to get file path, checksum, and thumbnail path
        media = self.get_media_by_id(media_id, user_id, session)
        file_path = media.file_path
        checksum = media.checksum
        thumbnail_path = media.thumbnail_path

        # Delete database record using entry service
        entry_service = entry_service_module.EntryService(session)
        entry_service.delete_entry_media(media_id, user_id)

        # Delete thumbnail file if it exists (thumbnails are not deduplicated)
        if thumbnail_path:
            try:
                full_thumbnail_path = (self.media_root / thumbnail_path).resolve()
                if full_thumbnail_path.exists() and str(full_thumbnail_path).startswith(str(self.media_root.resolve())):
                    full_thumbnail_path.unlink(missing_ok=True)
            except Exception as e:
                log_error(f"Failed to delete thumbnail file: {e}")

        # Delete file from filesystem using reference counting
        # Create storage service with fresh session AFTER commit to get accurate reference counts
        if checksum:
            try:
                from app.core.database import get_session_context

                # Create a new session for reference counting (after DB records are deleted)
                with get_session_context() as fresh_session:
                    media_storage_service = MediaStorageService(self.media_root, fresh_session)
                    media_storage_service.delete_media(
                        relative_path=file_path,
                        checksum=checksum,
                        user_id=str(user_id),
                        force=False
                    )
            except Exception as e:
                # Log error but don't fail since DB record is already deleted
                log_error(f"Failed to delete media file: {e}")

    async def get_media_file_for_serving(self, media_id: uuid.UUID, user_id: uuid.UUID, session: Session, range_header: Optional[str] = None) -> Dict[str, Any]:
        """Get media file information for serving with optional range support.

        Args:
            media_id: UUID of the media record
            user_id: UUID of the user requesting the media
            session: Database session
            range_header: Optional Range header value

        Returns:
            Dict with file_path, file_size, content_type, and optional range info

        Raises:
            MediaNotFoundError: If media not found or user doesn't have access
        """
        import mimetypes

        media = self.get_media_by_id(media_id, user_id, session)
        full_path = self.get_media_file_path(media)

        # Use async stat to avoid blocking event loop for file system access
        try:
            stat_result = await asyncio.to_thread(os.stat, full_path)
            file_size = stat_result.st_size
        except FileNotFoundError:
            raise MediaNotFoundError("Media file not found on disk")

        content_type, _ = mimetypes.guess_type(str(full_path))
        content_type = content_type or media.mime_type or "application/octet-stream"

        result = {
            "file_path": full_path,
            "file_size": file_size,
            "content_type": content_type,
            "filename": media.original_filename or full_path.name,
            "range_info": None,
        }

        # Parse range header if provided
        if range_header:
            try:
                if not range_header.strip().startswith("bytes="):
                    raise ValueError("Invalid range unit")

                range_val = range_header.strip().split("=")[1]
                start_str, end_str = range_val.split("-")

                if not start_str:
                    suffix_len = int(end_str)
                    if suffix_len <= 0:
                        raise ValueError("Invalid Range header")
                    start = max(file_size - suffix_len, 0)
                    end = file_size - 1
                elif not end_str:
                    start = int(start_str)
                    end = file_size - 1
                else:
                    start = int(start_str)
                    end = int(end_str)

                if start >= file_size or end >= file_size or start > end:
                    raise ValueError("Range not satisfiable")

                result["range_info"] = {
                    "start": start,
                    "end": end,
                    "length": end - start + 1,
                }
            except Exception:
                raise ValueError("Invalid Range header")

        return result

    async def process_entry_media(self, entry_id: uuid.UUID, user_id: uuid.UUID, session: Session) -> int:
        """Process all media files for an entry, generating thumbnails.

        Args:
            entry_id: UUID of the entry
            user_id: UUID of the user
            session: Database session

        Returns:
            Number of media files processed

        Raises:
            EntryNotFoundError: If entry not found or user doesn't have access
        """
        from app.services import entry_service as entry_service_module

        entry_service = entry_service_module.EntryService(session)

        # Verify entry belongs to user
        entry = entry_service.get_entry_by_id(entry_id, user_id)

        # Get entry media
        media_list = entry_service.get_entry_media(entry_id, user_id)

        processed_count = 0

        # Process media files concurrently
        async def process_single_media(media: EntryMedia) -> bool:
            """Process a single media file and return True if successful."""
            if not media.thumbnail_path:
                try:
                    full_path = self.get_media_file_path(media)

                    # Run thumbnail generation in thread pool since it involves file I/O and subprocess calls
                    loop = asyncio.get_event_loop()
                    thumbnail_path = None
                    if media.media_type == MediaType.IMAGE:
                        thumbnail_path = await loop.run_in_executor(
                            None, self._generate_thumbnail, str(full_path), MediaType.IMAGE
                        )
                    elif media.media_type == MediaType.VIDEO:
                        thumbnail_path = await loop.run_in_executor(
                            None, self._generate_thumbnail, str(full_path), MediaType.VIDEO
                        )

                    if thumbnail_path:
                        media.thumbnail_path = self._relative_thumbnail_path(Path(thumbnail_path))
                        session.add(media)
                        return True
                except Exception as e:
                    log_error(f"Error processing media {media.id}: {e}",
                             media_id=str(media.id), user_id=str(user_id))
            return False

        # Process all media concurrently
        results = await asyncio.gather(
            *[process_single_media(media) for media in media_list],
            return_exceptions=True
        )

        # Count successful processing
        for result in results:
            if result is True:
                processed_count += 1

        # Commit all changes
        session.commit()
        return processed_count


    async def batch_sign_media(
        self,
        request: MediaBatchSignRequest,
        current_user_id: uuid.UUID,
        session: Session
    ) -> MediaBatchSignResponse:
        """
        Batch sign media URLs for Journiv and Immich assets.

        Optimized to fetch all necessary data in bulk and generate signatures.
        """
        if len(request.items) > 200:
            raise ValueError("Too many items to sign in one request (limit 200)")

        results: list[MediaBatchSignResult] = []
        errors: dict[tuple[str, str], str] = {}

        item_ids_to_query: list[uuid.UUID] = []

        # 1. Validate basic format and gather IDs
        for item in request.items:
            item_key = (item.id, item.variant)

            if item.variant not in ("original", "thumbnail"):
                errors[item_key] = "Unsupported variant"
                continue

            try:
                uid_obj = uuid.UUID(item.id)
            except ValueError:
                errors[item_key] = "Invalid media id format"
                continue

            item_ids_to_query.append(uid_obj)

        # 2. Fetch minimal data for validation
        valid_media_map: dict[str, dict[str, object]] = {}
        if item_ids_to_query:
            query_ids_str = [str(uid) for uid in item_ids_to_query]

            logger.info(f"Batch sign querying for {len(item_ids_to_query)} IDs for user {current_user_id}")
            logger.debug(f"Batch sign querying for IDs: {item_ids_to_query}")
            rows = session.exec(
                select(
                    EntryMedia.id,
                    EntryMedia.upload_status,
                    EntryMedia.external_provider,
                    EntryMedia.external_asset_id,
                    EntryMedia.file_path,
                    EntryMedia.thumbnail_path,
                    EntryMedia.media_type,
                )
                .join(Entry)
                .where(
                    or_(
                        EntryMedia.id.in_(item_ids_to_query),
                        EntryMedia.external_asset_id.in_(query_ids_str)
                    )
                )
                .where(Entry.user_id == current_user_id)
            ).all()
            logger.info(f"Batch sign found {len(rows)} matching rows")
            logger.debug(f"Batch sign found matching rows: {rows}")

            # Build map indexed by both internal ID and external asset ID
            for media_id, upload_status, external_provider, external_asset_id, file_path, thumbnail_path, media_type in rows:
                media_data = {
                    "id": str(media_id),
                    "upload_status": upload_status,
                    "external_provider": external_provider,
                    "external_asset_id": external_asset_id,
                    "file_path": file_path,
                    "thumbnail_path": thumbnail_path,
                    "media_type": media_type,
                }

                # Index by internal ID
                valid_media_map[str(media_id)] = media_data

                # Index by external ID if present
                if external_asset_id:
                    valid_media_map[external_asset_id] = media_data

        # 3. Validate Immich integration once if needed
        needs_immich = any(
            meta.get("external_provider") == "immich"
            for meta in valid_media_map.values()
        )
        immich_active = True
        if needs_immich:
            integration = session.exec(
                select(Integration)
                .where(Integration.user_id == current_user_id)
                .where(Integration.provider == IntegrationProvider.IMMICH)
            ).first()
            immich_active = bool(integration and integration.is_active)

        # 4. Generate signatures
        now = int(time.time())
        signed_url_ttl = self.settings.media_signed_url_ttl_seconds
        video_signed_url_ttl = self.settings.media_signed_url_video_ttl_seconds
        thumb_signed_url_ttl = self.settings.media_thumbnail_signed_url_ttl_seconds
        user_id_str = str(current_user_id)

        for item in request.items:
            item_key = (item.id, item.variant)
            if item_key in errors:
                continue

            media_meta = valid_media_map.get(item.id)
            if not media_meta:
                errors[item_key] = "Media not found"
                continue

            # Always use the Journiv internal ID for signing
            internal_media_id = media_meta["id"]
            upload_status = media_meta["upload_status"]
            external_provider = media_meta["external_provider"]
            external_asset_id = media_meta["external_asset_id"]
            file_path = media_meta["file_path"]
            thumbnail_path = media_meta["thumbnail_path"]
            media_type = media_meta["media_type"]

            if upload_status == UploadStatus.FAILED:
                errors[item_key] = "Media failed"
                continue

            if external_provider == "immich":
                if not immich_active:
                    errors[item_key] = "Immich integration not active"
                    continue
                if not external_asset_id:
                    errors[item_key] = "Missing external asset id"
                    continue

                # Enforce COMPLETED status for all Immich assets
                # This handles:
                # 1. Copy-mode placeholders (PROCESSING) -> Not ready
                # 2. Link-only placeholders (PROCESSING) -> Not ready
                # 3. Copy-mode downloaded (COMPLETED) -> Ready
                # 4. Link-only processed (COMPLETED) -> Ready
                if upload_status != UploadStatus.COMPLETED:
                    errors[item_key] = "Media not ready"
                    continue

                # For copy-mode (local file), ensure thumbnail exists if requested
                if file_path and item.variant == "thumbnail" and not thumbnail_path:
                    errors[item_key] = "Thumbnail not available"
                    continue

                # Generate signed URL (works for both LINK_ONLY and COPY mode once ready)
                if item.variant == "thumbnail":
                    ttl_seconds = thumb_signed_url_ttl
                elif media_type == MediaType.VIDEO:
                    ttl_seconds = video_signed_url_ttl
                else:
                    ttl_seconds = signed_url_ttl
                expires_at = now + ttl_seconds
                signed_url = signed_url_for_journiv(
                    internal_media_id,
                    user_id_str,
                    item.variant,
                    expires_at,
                )
            elif external_provider is None:
                if upload_status != UploadStatus.COMPLETED:
                    errors[item_key] = "Media not ready"
                    continue
                if item.variant == "thumbnail" and not thumbnail_path:
                    errors[item_key] = "Thumbnail not available"
                    continue
                if item.variant == "original" and not file_path:
                    errors[item_key] = "Media file not available"
                    continue
                if item.variant == "thumbnail":
                    ttl_seconds = thumb_signed_url_ttl
                elif media_type == MediaType.VIDEO:
                    ttl_seconds = video_signed_url_ttl
                else:
                    ttl_seconds = signed_url_ttl
                expires_at = now + ttl_seconds
                signed_url = signed_url_for_journiv(
                    internal_media_id,
                    user_id_str,
                    item.variant,
                    expires_at,
                )
            else:
                errors[item_key] = "Unsupported external provider"
                continue

            results.append(
                MediaBatchSignResult(
                    id=item.id,
                    variant=item.variant,
                    signed_url=signed_url,
                    expires_at=expires_at,
                )
            )

        error_items = [
            MediaBatchSignError(
                id=item_id,
                variant=item_variant,
                error=error,
            )
            for (item_id, item_variant), error in errors.items()
        ]

        return MediaBatchSignResponse(results=results, errors=error_items)
