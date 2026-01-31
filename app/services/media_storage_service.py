"""
Unified media storage service using content-addressable storage.

This service handles all media file operations with:
- Checksum-based deduplication (per-user)
- Atomic file writes
- User isolation
- Reference counting for safe deletion
"""
import hashlib
import uuid
from pathlib import Path
from typing import Optional, Tuple, BinaryIO, Union
import shutil

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.logging_config import log_info, log_error, log_warning
from app.utils.import_export.media_handler import MediaHandler
from app.models.entry import EntryMedia, Entry
from app.models.journal import Journal


class MediaStorageService:
    """
    Unified media storage service with per-user deduplication.

    Storage path format: media/{user_id}/{type}/{checksum}.ext

    Examples:
        - media/550e8400-e29b-41d4-a716-446655440000/images/a1b2c3...xyz.jpg
        - media/550e8400-e29b-41d4-a716-446655440000/videos/d4e5f6...abc.mp4
    """

    def __init__(self, media_root: Path, db: Optional[Session] = None):
        """
        Initialize storage service.

        Args:
            media_root: Root directory for media storage (e.g., /data/media)
            db: Database session for reference counting (optional)
        """
        self.media_root = Path(media_root).resolve()
        self.media_handler = MediaHandler()
        self.db = db

    def store_media(
        self,
        source: Union[BinaryIO, Path],
        user_id: str,
        media_type: str,
        extension: str,
        checksum: Optional[str] = None
    ) -> Tuple[str, str, bool]:
        """
        Store media file with per-user deduplication.

        Args:
            source: File-like object or Path to source file
            user_id: User UUID string
            media_type: Type directory (images, videos, audio)
            extension: File extension (with or without dot, e.g., '.jpg' or 'jpg')
            checksum: Pre-calculated checksum (optional, will calculate if None)

        Returns:
            Tuple of (relative_path, checksum, was_deduplicated)
            - relative_path: Path relative to media root
            - checksum: SHA256 checksum hex string
            - was_deduplicated: True if file already existed

        Raises:
            IOError: If file operations fail
            ValueError: If parameters are invalid
        """
        # Validate inputs
        if not user_id or not media_type or not extension:
            raise ValueError("user_id, media_type, and extension are required")

        # Prevent path traversal
        if '/' in user_id or '\\' in user_id or '..' in user_id:
            raise ValueError("user_id contains invalid path characters")
        if '/' in media_type or '\\' in media_type or '..' in media_type:
            raise ValueError("media_type contains invalid path characters")
        if '/' in extension or '\\' in extension or '..' in extension:
            raise ValueError("extension contains invalid path characters")

        # Calculate checksum if not provided
        if checksum is None:
            if isinstance(source, Path):
                checksum = self.media_handler.calculate_checksum(source)
            else:
                # Single-pass: stream to temp while computing checksum
                tmp_dir = self.media_root / "_tmp" / user_id / media_type
                tmp_dir.mkdir(parents=True, exist_ok=True)
                tmp_path = tmp_dir / f"{uuid.uuid4().hex}{extension}.tmp"
                hasher = hashlib.sha256()

                try:
                    if hasattr(source, "seek"):
                        try:
                            source.seek(0)
                        except Exception:
                            pass
                    with open(tmp_path, "wb") as dst:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            hasher.update(chunk)
                            dst.write(chunk)
                    checksum = hasher.hexdigest()
                except Exception as e:
                    if tmp_path.exists():
                        tmp_path.unlink()
                    log_error(e, user_id=user_id)
                    raise IOError(f"Failed to store media: {e}") from e

                # Build target path
                relative_path = self._build_storage_path(
                    user_id, media_type, checksum, extension
                )
                target_path = self.media_root / relative_path

                # Check if file already exists (per-user deduplication)
                if target_path.exists():
                    tmp_path.unlink(missing_ok=True)
                    log_info(
                        f"Media file already exists (deduplicated): {relative_path}",
                        checksum=checksum,
                        user_id=user_id
                    )
                    return str(relative_path), checksum, True

                # Ensure parent directory exists
                target_path.parent.mkdir(parents=True, exist_ok=True)

                try:
                    tmp_path.rename(target_path)
                except Exception as e:
                    if tmp_path.exists():
                        tmp_path.unlink()
                    log_error(e, relative_path=str(relative_path), user_id=user_id)
                    raise IOError(f"Failed to store media: {e}") from e

                log_info(
                    f"Media file stored: {relative_path}",
                    checksum=checksum,
                    user_id=user_id,
                    size=target_path.stat().st_size
                )

                return str(relative_path), checksum, False

        # Build target path
        relative_path = self._build_storage_path(
            user_id, media_type, checksum, extension
        )
        target_path = self.media_root / relative_path

        # Check if file already exists (per-user deduplication)
        if target_path.exists():
            log_info(
                f"Media file already exists (deduplicated): {relative_path}",
                checksum=checksum,
                user_id=user_id
            )
            return str(relative_path), checksum, True

        # Ensure parent directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file atomically using .tmp suffix
        tmp_path = target_path.with_suffix(target_path.suffix + '.tmp')

        try:
            if isinstance(source, Path):
                # Copy from file path
                shutil.copy2(source, tmp_path)
            else:
                # Copy from stream
                source.seek(0)
                with open(tmp_path, 'wb') as dst:
                    shutil.copyfileobj(source, dst)

            # Atomic rename
            tmp_path.rename(target_path)

            log_info(
                f"Media file stored: {relative_path}",
                checksum=checksum,
                user_id=user_id,
                size=target_path.stat().st_size
            )

            return str(relative_path), checksum, False

        except Exception as e:
            # Clean up temp file on error
            if tmp_path.exists():
                tmp_path.unlink()
            log_error(e, relative_path=str(relative_path), user_id=user_id)
            raise IOError(f"Failed to store media: {e}") from e

    def _build_storage_path(
        self,
        user_id: str,
        media_type: str,
        checksum: str,
        extension: str
    ) -> str:
        """
        Build storage path for media file.

        Format: {user_id}/{media_type}/{checksum}{extension}

        Args:
            user_id: User UUID string
            media_type: Type directory (images, videos, audio)
            checksum: SHA256 checksum
            extension: File extension (with or without dot)

        Returns:
            Relative path string
        """
        # Ensure extension starts with dot
        if not extension.startswith('.'):
            extension = f'.{extension}'

        # Validate extension doesn't contain path traversal
        if '/' in extension or '\\' in extension or '..' in extension:
            raise ValueError("extension contains invalid path characters")

        return f"{user_id}/{media_type}/{checksum}{extension}"

    def get_full_path(self, relative_path: str) -> Path:
        """
        Get absolute path from relative path.

        Args:
            relative_path: Path relative to media root

        Returns:
            Absolute Path object
        """
        return self.media_root / relative_path

    def file_exists(self, relative_path: str) -> bool:
        """
        Check if media file exists.

        Args:
            relative_path: Path relative to media root

        Returns:
            True if file exists
        """
        return self.get_full_path(relative_path).exists()

    def delete_media(
        self,
        relative_path: str,
        checksum: Optional[str],
        user_id: str,
        force: bool = False
    ) -> bool:
        """
        Delete media file with reference counting.

        Checks if the file is referenced by other EntryMedia records before deletion.
        Only deletes the physical file if no other references exist, or if force=True.
        When checksum is None, force deletion is required (reference counting not possible).

        Args:
            relative_path: Path relative to media root
            checksum: SHA256 checksum of the file (None for files without checksums)
            user_id: User UUID string
            force: If True, delete even if referenced elsewhere. Required when checksum is None.

        Returns:
            True if file was deleted, False otherwise

        Raises:
            RuntimeError: If force=False and database session is not available, or if checksum is None and force=False
            IOError: If deletion fails
        """
        full_path = self.get_full_path(relative_path)

        if not full_path.exists():
            log_warning(f"Media file not found for deletion: {relative_path}")
            return False

        # If checksum is None, we must force delete (can't do reference counting)
        if checksum is None and not force:
            log_warning(
                f"Media file has no checksum, forcing deletion: {relative_path}",
                relative_path=relative_path,
                user_id=user_id
            )
            force = True

        if not force and self.db is None:
            raise RuntimeError(
                "Cannot perform safe deletion: database session is required when force=False. "
                "Provide a database session via __init__ or use force=True to bypass reference counting."
            )

        # Reference counting check (only if we have a checksum)
        if not force and self.db and checksum is not None:
            reference_count = self._count_references(checksum, user_id)

            if reference_count > 0:
                log_info(
                    f"Media file has {reference_count} references, not deleting physical file",
                    checksum=checksum,
                    user_id=user_id,
                    relative_path=relative_path
                )
                return False

        try:
            full_path.unlink()
            log_info(f"Media file deleted: {relative_path}", checksum=checksum, user_id=user_id)

            # Clean up empty parent directories
            self._cleanup_empty_dirs(full_path.parent)

            return True

        except Exception as e:
            log_error(e, relative_path=str(relative_path), checksum=checksum, user_id=user_id)
            raise IOError(f"Failed to delete media: {e}") from e

    def _count_references(self, checksum: str, user_id: Union[str, uuid.UUID]) -> int:
        """
        Count how many EntryMedia records reference this file for the user.

        Args:
            checksum: SHA256 checksum
            user_id: User UUID string or UUID instance

        Returns:
            Number of EntryMedia records with this checksum for this user

        Raises:
            ValueError: If user_id is not a valid UUID string or UUID instance
        """
        if not self.db:
            return 0

        if isinstance(user_id, uuid.UUID):
            user_uuid = user_id
        else:
            try:
                user_uuid = uuid.UUID(user_id)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"Invalid user_id format: expected UUID string or UUID instance, got {type(user_id).__name__} with value '{user_id}'"
                ) from e

        stmt = (
            select(func.count(EntryMedia.id))
            .join(Entry)
            .join(Journal)
            .where(
                EntryMedia.checksum == checksum,
                Journal.user_id == user_uuid
            )
        )

        result = self.db.execute(stmt)
        count = result.scalar()

        return count if count else 0

    def _cleanup_empty_dirs(self, directory: Path) -> None:
        """
        Remove empty parent directories up to media root.

        Args:
            directory: Directory to start cleanup from
        """
        try:
            # Don't delete media root itself
            while directory != self.media_root and directory.exists():
                # Check if directory is empty
                if not any(directory.iterdir()):
                    directory.rmdir()
                    log_info(f"Removed empty directory: {directory}")
                    directory = directory.parent
                else:
                    # Directory not empty, stop climbing
                    break
        except Exception as e:
            log_warning(f"Failed to cleanup empty directories: {e}")
