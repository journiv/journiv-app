"""
Media file handling utilities for import/export.

Handles file validation, checksum calculation, and media deduplication.
"""
import hashlib
import mimetypes
import logging
from pathlib import Path
from typing import Optional, Tuple, BinaryIO, ClassVar, Union


class MediaHandler:
    """
    Handles media file operations for import/export.

    Provides:
    - Checksum calculation for deduplication
    - File type validation
    - Size validation
    """

    # Extension to MIME type mapping
    MIME_TYPE_MAP: ClassVar[dict[str, str]] = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
        '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
        '.tiff': 'image/tiff', '.svg': 'image/svg+xml', '.heic': 'image/heic',
        '.mp4': 'video/mp4', '.avi': 'video/x-msvideo', '.mov': 'video/quicktime',
        '.webm': 'video/webm', '.mkv': 'video/x-matroska', '.flv': 'video/x-flv',
        '.m4v': 'video/x-m4v', '.wmv': 'video/x-ms-wmv',
        '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg',
        '.m4a': 'audio/mp4', '.aac': 'audio/aac', '.flac': 'audio/flac',
        '.wma': 'audio/x-ms-wma'
    }

    # Media type categorization by extension
    IMAGE_EXTENSIONS: ClassVar[set[str]] = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg", ".heic"}
    VIDEO_EXTENSIONS: ClassVar[set[str]] = {".mp4", ".avi", ".mov", ".wmv", ".webm", ".mkv", ".flv", ".m4v"}
    AUDIO_EXTENSIONS: ClassVar[set[str]] = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".wma"}

    @staticmethod
    def sha256_hasher() -> "hashlib._Hash":
        """Return a new sha256 hasher (helper to enable injection/testing)."""
        return hashlib.sha256()

    @staticmethod
    def calculate_checksum(file_path: Path) -> str:
        """
        Calculate SHA256 checksum of a file.

        Args:
            file_path: Path to file

        Returns:
            Hex string of SHA256 checksum

        Raises:
            FileNotFoundError: If file doesn't exist
            IOError: If file can't be read
        """
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)

        return sha256_hash.hexdigest()

    @staticmethod
    def calculate_checksum_from_bytes(data: bytes) -> str:
        """
        Calculate SHA256 checksum from bytes.

        Args:
            data: File data as bytes

        Returns:
            Hex string of SHA256 checksum
        """
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def calculate_checksum_from_stream(stream: BinaryIO) -> str:
        """
        Calculate SHA256 checksum from a file stream.

        Args:
            stream: File-like object in binary mode

        Returns:
            Hex string of SHA256 checksum
        """
        sha256_hash = hashlib.sha256()

        # Save current position
        original_position = stream.tell()

        # Read from beginning
        stream.seek(0)

        # Read in chunks
        for chunk in iter(lambda: stream.read(8192), b""):
            sha256_hash.update(chunk)

        # Restore position
        stream.seek(original_position)

        return sha256_hash.hexdigest()

    @staticmethod
    def guess_media_type(filename: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Guess media type from filename.

        Args:
            filename: Original filename with extension

        Returns:
            Tuple of (mime_type, extension) where each element may independently be None.
            mime_type is None if the MIME type cannot be guessed.
            extension is None if the filename has no extension.
        """
        # Initialize mimetypes if needed
        if not mimetypes.inited:
            mimetypes.init()

        mime_type, _ = mimetypes.guess_type(filename)
        extension = Path(filename).suffix.lower()

        return mime_type, extension if extension else None

    @staticmethod
    def validate_media_type(mime_type: str, allowed_types: list[str]) -> bool:
        """
        Check if media type is in allowed list.

        Args:
            mime_type: MIME type to validate
            allowed_types: List of allowed MIME types

        Returns:
            True if valid, False otherwise
        """
        if not mime_type:
            return False

        # Exact match
        if mime_type in allowed_types:
            return True

        # Wildcard match (e.g., "image/*")
        category = mime_type.split("/")[0]
        wildcard = f"{category}/*"
        return wildcard in allowed_types

    @staticmethod
    def validate_file_size(file_size: int, max_size_mb: int) -> bool:
        """
        Validate file size against maximum.

        Args:
            file_size: File size in bytes
            max_size_mb: Maximum allowed size in megabytes

        Returns:
            True if valid, False if too large
        """
        max_bytes = max_size_mb * 1024 * 1024
        return file_size <= max_bytes

    @classmethod
    def get_supported_mime_types(cls) -> set[str]:
        """
        Get set of all supported MIME types from MIME_TYPE_MAP.

        Returns:
            Set of supported MIME type strings
        """
        return set(cls.MIME_TYPE_MAP.values())

    @staticmethod
    def is_supported_media_type(mime_type: Optional[str]) -> bool:
        """
        Check if media type is supported by Journiv.

        Args:
            mime_type: MIME type to check

        Returns:
            True if supported, False otherwise
        """
        if not mime_type:
            return False

        supported_types = MediaHandler.get_supported_mime_types()
        return mime_type.lower() in supported_types

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize a filename to make it safe for filesystem.

        Removes dangerous characters and path traversal attempts.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        # Remove path components
        filename = Path(filename).name

        # Remove dangerous characters
        dangerous_chars = '<>:"|?*\\/\x00'
        for char in dangerous_chars:
            filename = filename.replace(char, "_")

        # Remove leading/trailing dots and spaces
        filename = filename.strip(". ")

        # Ensure filename is not empty
        if not filename:
            filename = "unnamed"

        # Limit length
        max_length = 255
        if len(filename) > max_length:
            # Preserve extension
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            max_stem_length = max_length - len(suffix)
            filename = stem[:max_stem_length] + suffix

        return filename

    @staticmethod
    def detect_mime(file_path: Path) -> str:
        """
        Detect MIME type of a file using libmagic with fallback.

        Args:
            file_path: Path to the file

        Returns:
            Detected MIME type string
        """
        try:
            import magic
            return magic.from_file(str(file_path), mime=True)
        except (ImportError, Exception):
            # Fallback to mimetypes guess if magic is not available or fails
            mime_type, _ = mimetypes.guess_type(str(file_path))
            return mime_type or "application/octet-stream"

    @staticmethod
    def validate_media(
        file_path: Path,
        max_size_mb: int,
        allowed_types: list[str],
        allowed_extensions: list[str]
    ) -> Tuple[bool, str, str, str]:
        """
        Validate a media file's size, MIME type, and extension.

        Args:
            file_path: Path to file
            max_size_mb: Maximum allowed size in MB
            allowed_types: List of allowed MIME types
            allowed_extensions: List of allowed file extensions

        Returns:
            Tuple of (is_valid, mime_type, category, error_message)
            category is one of: not_found, size, format, extension, error, none
        """
        try:
            # 1. Check file size
            if not file_path.exists():
                return False, "unknown", "not_found", f"File not found: {file_path}"

            file_size = file_path.stat().st_size
            if not MediaHandler.validate_file_size(file_size, max_size_mb):
                return False, "unknown", "size", f"File size exceeds maximum limit of {max_size_mb}MB"

            # 2. Check MIME type
            mime_type = MediaHandler.detect_mime(file_path)
            if not MediaHandler.validate_media_type(mime_type, allowed_types):
                return False, mime_type, "format", f"Mime type {mime_type} not allowed"

            # 3. Check file extension
            file_ext = file_path.suffix.lower()
            if allowed_extensions and file_ext not in allowed_extensions:
                return False, mime_type, "extension", f"File extension {file_ext} not allowed"

            return True, mime_type, "none", "File is valid"
        except Exception as e:
            return False, "unknown", "error", f"Validation failed: {e}"
