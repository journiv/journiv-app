"""
ZIP file handling utilities for import/export.

Handles creation and extraction of ZIP archives for data exports/imports.
"""
import zipfile
import json
import shutil
import gc
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from app.core.config import settings
from app.core.logging_config import log_warning, log_error
from app.utils.import_export.media_handler import MediaHandler

logger = logging.getLogger(__name__)


class ZipHandler:
    """
    Handles ZIP archive operations for import/export.

    Provides:
    - Creating ZIP archives with data and media files
    - Extracting ZIP archives safely
    - Validating ZIP contents
    """

    @staticmethod
    def create_export_zip(
        output_path: Path,
        data: Optional[Dict[str, Any]] = None,
        media_files: Optional[Dict[str, Path]] = None,
        data_filename: str = "data.json",
        data_file_path: Optional[Path] = None,
    ) -> int:
        """
        Create a ZIP archive for export.

        Structure:
        ```
        export.zip
        ├── data.json          # Main export data
        └── media/             # Media files (if any)
            ├── {entry_id_1}/  # Organized by entry ID
            │   ├── {media_id_1}_{filename1}
            │   └── {media_id_2}_{filename2}
            └── {entry_id_2}/
                └── {media_id_3}_{filename3}
        ```

        Media files are organized by entry_id to maintain relationships
        and avoid filename conflicts. Each media file path format is:
        `{entry_id}/{media_id}_{sanitized_filename}`

        Args:
            output_path: Path for output ZIP file
            data: Export data (will be JSON serialized)
            media_files: Dictionary of {relative_path: source_file_path}
            data_filename: Name for the JSON data file

        Returns:
            Total size of created ZIP file in bytes

        Raises:
            IOError: If ZIP creation fails
        """
        try:
            if data is None and data_file_path is None:
                raise ValueError("Either data or data_file_path must be provided")

            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Write JSON data
                if data_file_path:
                    zipf.write(data_file_path, arcname=data_filename)
                else:
                    json_str = json.dumps(data, indent=2, default=str)
                    zipf.writestr(data_filename, json_str)

                # Write media files
                if media_files:
                    for relative_path, source_path in media_files.items():
                        if source_path.exists():
                            # Store in media/ subdirectory
                            archive_path = f"media/{relative_path}"
                            zipf.write(source_path, archive_path)
                        else:
                            log_warning(f"Media file not found: {source_path}", source_path=str(source_path))

            # Return file size
            return output_path.stat().st_size

        except Exception as e:
            log_error(e, output_path=str(output_path))
            raise IOError(f"ZIP creation failed: {e}") from e

    @staticmethod
    def extract_zip(
        zip_path: Path,
        extract_to: Path,
        max_size_mb: int = 500,
        source_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract a ZIP archive safely.

        Args:
            zip_path: Path to ZIP file
            extract_to: Directory to extract to
            max_size_mb: Maximum allowed uncompressed size

        Returns:
            Dictionary with extraction info:
            {
                "data_file": Path to data file,
                "media_dir": Path to media directory,
                "total_size": Total extracted size in bytes,
                "file_count": Number of files extracted
            }

        Raises:
            ValueError: If ZIP is invalid or too large
            IOError: If extraction fails
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                # Validate ZIP
                if zipf.testzip() is not None:
                    raise ValueError("ZIP file is corrupted")

                # Check total uncompressed size
                total_size = sum(info.file_size for info in zipf.infolist())
                max_bytes = max_size_mb * 1024 * 1024

                if total_size > max_bytes:
                    raise ValueError(
                        f"ZIP too large: {total_size / (1024*1024):.1f}MB "
                        f"(max: {max_size_mb}MB)"
                    )

                # Ensure extract_to directory exists
                extract_to.mkdir(parents=True, exist_ok=True)
                extract_to_resolved = extract_to.resolve()

                # Check for path traversal attacks
                for info in zipf.infolist():
                    # Build extraction path and normalize to detect traversal attempts
                    extract_path = (extract_to / info.filename).resolve()

                    # Ensure it's within extract_to (prevents path traversal)
                    # Use proper path containment check, not string prefix matching
                    try:
                        extract_path.relative_to(extract_to_resolved)
                    except ValueError:
                        # Path is outside extract_to directory
                        raise ValueError(
                            f"ZIP contains unsafe path: {info.filename}"
                        )

                # Extract all files
                zipf.extractall(extract_to)

                # Find data file and media directory
                if source_type == "dayone":
                    # Day One has various JSON files at root, handled by DayOneParser
                    # We just need to find one to satisfy basic validation here
                    root_json_files = list(extract_to.glob("*.json"))
                    data_file = root_json_files[0] if root_json_files else None
                    media_dir = extract_to # Day One media are in photos/ videos/ at root
                else:
                    data_file = extract_to / "data.json"
                    media_dir = extract_to / "media"

                if not data_file:
                    raise ValueError(f"ZIP missing JSON data file (source: {source_type or 'journiv'})")

                if not data_file.exists():
                    raise ValueError(f"Extracted data file not found: {data_file}")

                return {
                    "data_file": data_file,
                    "media_dir": media_dir if media_dir.exists() else None,
                    "total_size": total_size,
                    "file_count": len(zipf.infolist())
                }

        except zipfile.BadZipFile as e:
            raise ValueError(f"Invalid ZIP file: {e}") from e
        except Exception as e:
            log_error(e, zip_path=str(zip_path), extract_to=str(extract_to))
            raise IOError(f"Extraction failed: {e}") from e

    @staticmethod
    def validate_zip_structure(zip_path: Path, source_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate ZIP file structure without extracting.

        Args:
            zip_path: Path to ZIP file
            source_type: Import source type ('journiv', 'dayone', etc.)

        Returns:
            Dictionary with validation results:
            {
                "valid": bool,
                "has_data_file": bool,
                "has_media": bool,
                "file_count": int,
                "total_size": int,
                "errors": List[str]
            }
        """
        result = {
            "valid": True,
            "has_data_file": False,
            "has_media": False,
            "file_count": 0,
            "total_size": 0,
            "errors": []
        }

        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                # Test ZIP integrity
                bad_file = zipf.testzip()
                if bad_file is not None:
                    result["valid"] = False
                    result["errors"].append(f"Corrupted file in ZIP: {bad_file}")
                    return result

                # Check contents
                file_list = zipf.namelist()
                result["file_count"] = len(file_list)
                result["total_size"] = sum(info.file_size for info in zipf.infolist())

                # Check for data file based on source type
                if source_type == "dayone":
                    # Day One exports have .json files at root (e.g., Del1.json, MyJournal.json)
                    # Check for any .json file at root level (not in subdirectories)
                    root_json_files = [f for f in file_list if f.endswith(".json") and "/" not in f]
                    if root_json_files:
                        result["has_data_file"] = True
                    else:
                        result["valid"] = False
                        result["errors"].append("Missing JSON file at root (Day One format expects JournalName.json)")
                else:
                    # Journiv exports have data.json
                    if "data.json" in file_list:
                        result["has_data_file"] = True
                    else:
                        result["valid"] = False
                        result["errors"].append("Missing data.json file")

                # Check for media directory
                if source_type == "dayone":
                    # Day One has photos/ and videos/ directories
                    media_files = [f for f in file_list if f.startswith("photos/") or f.startswith("Photos/") or f.startswith("videos/") or f.startswith("Videos/")]
                else:
                    # Journiv has media/ directory
                    media_files = [f for f in file_list if f.startswith("media/")]
                result["has_media"] = len(media_files) > 0

                # Check for path traversal
                for filename in file_list:
                    if ".." in filename or filename.startswith("/"):
                        result["valid"] = False
                        result["errors"].append(f"Unsafe path in ZIP: {filename}")

        except zipfile.BadZipFile as e:
            result["valid"] = False
            result["errors"].append(f"Invalid ZIP file: {e}")
        except (OSError, PermissionError, FileNotFoundError) as e:
            result["valid"] = False
            error_msg = f"File system error: {e}"
            result["errors"].append(error_msg)
            log_error(e, zip_path=str(zip_path), context="zip_validation_file_system_error")
        except RuntimeError as e:
            result["valid"] = False
            error_msg = f"Runtime error during validation: {e}"
            result["errors"].append(error_msg)
            log_error(e, zip_path=str(zip_path), context="zip_validation_runtime_error")
        except Exception as e:
            result["valid"] = False
            error_msg = f"Validation error: {e}"
            result["errors"].append(error_msg)
            log_error(e, zip_path=str(zip_path), context="zip_validation_unexpected_error")

        return result

    @staticmethod
    def stream_extract(
        zip_path: Path,
        extract_to: Path,
        media_dest: Optional[Path] = None,
        max_size_mb: int = 500,
        validate_media: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        source_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Extract ZIP file one entry at a time (memory-efficient).

        Memory usage: O(largest_individual_file), NOT O(total_zip_size)

        This method is identical to extract_zip() but extracts files
        individually instead of calling extractall(). This prevents
        memory spikes with large ZIP files.

        Zero-Copy Strategy:
        If media_dest is provided, media files are written directly to
        the destination (e.g., /data/media/{user_id}/) instead of temp
        directory. This eliminates redundant copy operations.

        Args:
            zip_path: Path to ZIP file
            extract_to: Directory to extract data.json to (temp directory)
            media_dest: Optional direct destination for media files (zero-copy)
            max_size_mb: Maximum allowed uncompressed size
            validate_media: Validate media types using libmagic (default: True)
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Same as extract_zip()

        Raises:
            ValueError: If ZIP is invalid or too large
            IOError: If extraction fails
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                # Same validation as extract_zip()
                if zipf.testzip() is not None:
                    raise ValueError("ZIP file is corrupted")

                # Check total size
                total_size = sum(info.file_size for info in zipf.infolist())
                max_bytes = max_size_mb * 1024 * 1024

                if total_size > max_bytes:
                    raise ValueError(
                        f"ZIP too large: {total_size / (1024*1024):.1f}MB "
                        f"(max: {max_size_mb}MB)"
                    )

                # Ensure extract_to exists
                extract_to.mkdir(parents=True, exist_ok=True)
                extract_to_resolved = extract_to.resolve()

                # Get file list
                entries = zipf.infolist()
                total_files = len(entries)

                # Track warnings during extraction
                warnings = []
                warning_categories = {}

                # Extract files one by one
                for idx, info in enumerate(entries, start=1):
                    # Skip directory entries
                    if info.is_dir():
                        continue

                    # Determine if this is a media file
                    if source_type == "dayone":
                        is_media_file = any(info.filename.lower().startswith(p) for p in ["photos/", "videos/"])
                    else:
                        is_media_file = info.filename.startswith("media/")

                    # Choose destination based on zero-copy strategy
                    if is_media_file and media_dest:
                        # Zero-copy: Write directly to final destination
                        # Extract to media_dest preserving structure
                        target_dir = media_dest

                        if source_type == "dayone":
                            # For Day One, preserve photos/ or videos/ directories
                            relative_path = Path(info.filename)
                        else:
                            relative_path = Path(info.filename).relative_to("media")

                        target_path = (media_dest / relative_path).resolve()
                    else:
                        # Extract data.json and other files to temp
                        target_dir = extract_to
                        target_path = (extract_to / info.filename).resolve()

                    # Path traversal check
                    try:
                        target_path.relative_to(target_dir.resolve())
                    except ValueError:
                        raise ValueError(f"ZIP contains unsafe path: {info.filename}")

                    # Extract single file to appropriate destination
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zipf.open(info) as source:
                        with open(target_path, 'wb') as dest:
                            shutil.copyfileobj(source, dest)

                    # Validate media files using centralized MediaHandler
                    if is_media_file and validate_media:
                        validation_result = MediaHandler.validate_media(
                            target_path,
                            max_size_mb=max_size_mb,
                            allowed_types=settings.allowed_media_types,
                            allowed_extensions=settings.allowed_file_extensions
                        )

                        is_valid, mime_type, category, error_msg = validation_result

                        if not is_valid:
                            warning_msg = f"Media validation failed for {info.filename}: {error_msg}"
                            log_warning(
                                warning_msg,
                                filename=info.filename,
                                mime_type=mime_type,
                                category=category,
                                error=error_msg,
                                context="stream_extract_validation_failed"
                            )
                            warnings.append(warning_msg)

                            # Categorize warnings using structured metadata
                            cat_map = {
                                "size": "Skipped due to size",
                                "format": "Skipped due to format",
                                "extension": "Skipped due to extension",
                                "not_found": "Skipped (not found)",
                                "error": "Skipped (error)"
                            }
                            display_category = cat_map.get(category, f"Skipped ({category})")
                            warning_categories[display_category] = warning_categories.get(display_category, 0) + 1

                            # (2) Remove invalid file immediately
                            try:
                                if target_path.exists():
                                    target_path.unlink()
                                    logger.info(f"Deleted invalid media file: {target_path}")
                            except Exception as cleanup_exc:
                                # Log but don't fail the whole extraction for a cleanup error
                                logger.exception(
                                    f"Failed to delete invalid media file {target_path}"
                                )

                    # Report progress
                    if progress_callback:
                        progress_callback(idx, total_files)

                    # Explicit garbage collection hint for large files
                    # Python's GC will clean up extracted file buffers
                    if idx % 100 == 0:  # Every 100 files
                        gc.collect()

                # Return same structure as extract_zip()
                if source_type == "dayone":
                    root_json_files = list(extract_to.glob("*.json"))
                    data_file = root_json_files[0] if root_json_files else None
                    media_dir = extract_to
                else:
                    data_file = extract_to / "data.json"
                    media_dir = extract_to / "media"

                if media_dest and media_dest.exists():
                    media_dir = media_dest

                if not data_file:
                    raise ValueError(f"ZIP missing JSON data file (source: {source_type or 'journiv'})")

                if not data_file.exists():
                    raise ValueError(f"Extracted data file not found: {data_file}")

                return {
                    "data_file": data_file,
                    "media_dir": media_dir if media_dir and media_dir.exists() else None,
                    "total_size": total_size,
                    "file_count": len(entries),
                    "warnings": warnings,
                    "warning_categories": warning_categories,
                }

        except zipfile.BadZipFile as e:
            raise ValueError(f"Invalid ZIP file: {e}") from e
        except Exception as e:
            log_error(e, zip_path=str(zip_path), extract_to=str(extract_to))
            raise IOError(f"Extraction failed: {e}") from e

    @staticmethod
    def list_zip_contents(zip_path: Path) -> List[str]:
        """
        List all files in a ZIP archive.

        Args:
            zip_path: Path to ZIP file

        Returns:
            List of file paths in the ZIP

        Raises:
            ValueError: If ZIP is invalid
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                return zipf.namelist()
        except zipfile.BadZipFile as e:
            raise ValueError(f"Invalid ZIP file: {e}") from e
