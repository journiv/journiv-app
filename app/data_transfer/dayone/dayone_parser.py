"""
Day One export parser.

Parses Day One JSON export files and extracts media.
"""
import json
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging_config import log_error, log_info, log_warning

from .models import DayOneExport, DayOneJournal

# Security constants
MAX_FILENAME_LENGTH = 255
MAX_JSON_SIZE_MB = 500
ALLOWED_EXTENSIONS = set(settings.allowed_file_extensions or []) | {'.json'}

# Validation patterns
MD5_HASH_PATTERN = re.compile(r'^[0-9a-fA-F]{32}$')
IDENTIFIER_PATTERN = re.compile(r'^[0-9a-fA-F\-]{1,64}$')


def _validate_md5_hash(md5_hash: Optional[str]) -> Optional[str]:
    """
    Validate MD5 hash format (32 hex characters).

    Returns:
        Validated hash if valid, None otherwise
    """
    if not md5_hash:
        return None

    if MD5_HASH_PATTERN.match(md5_hash):
        return md5_hash

    log_warning(
        "Invalid MD5 hash format, skipping glob search",
        md5_hash=md5_hash[:50] if len(md5_hash) > 50 else md5_hash
    )
    return None


def _validate_identifier(identifier: str) -> Optional[str]:
    """
    Validate identifier format (alphanumerics and hyphens, max 64 chars).

    Returns:
        Validated identifier if valid, None otherwise
    """
    if not identifier:
        return None

    if IDENTIFIER_PATTERN.match(identifier):
        return identifier

    log_warning(
        "Invalid identifier format, skipping glob search",
        identifier=identifier[:50] if len(identifier) > 50 else identifier
    )
    return None


class DayOneParser:
    """
    Parser for Day One JSON exports.

    Day One export structure:
    ```
    dayone_export.zip
      ├── Journal.json          (where "Journal" is the journal name)
      ├── Photos/
      │   └── {photo_id}.{ext}
      └── Videos/
          └── {video_id}.{ext}
    ```
    """

    @staticmethod
    def parse_zip(
        zip_path: Path,
        extract_to: Path,
        is_already_extracted: bool = False
    ) -> Tuple[List[DayOneJournal], Optional[Path]]:
        """
        Parse Day One ZIP export.

        Args:
            zip_path: Path to Day One ZIP file
            extract_to: Directory to extract to
            is_already_extracted: If True, skip extraction and parse extract_to directly

        Returns:
            Tuple of (list of DayOneJournal objects, media directory path)

        Raises:
            ValueError: If ZIP is invalid or missing required files
            IOError: If extraction fails
        """
        if not is_already_extracted:
            if not zip_path.exists():
                raise ValueError(f"ZIP file not found: {zip_path}")

            if not zip_path.is_file():
                raise ValueError(f"ZIP path is not a file: {zip_path}")

        try:
            if not is_already_extracted:
                # Safety check: verify extract_to is within allowed base directory
                base_temp_dir = Path(settings.import_temp_dir).resolve()
                extract_to_resolved = extract_to.resolve()

                # Check that extract_to is not a root path or home directory
                root_path = Path("/")
                home_path = Path.home()
                if (extract_to_resolved == root_path or
                    extract_to_resolved == home_path or
                    (os.name == 'nt' and len(extract_to_resolved.parts) == 1 and extract_to_resolved.drive)):
                    log_error(
                        f"Unsafe extraction path detected: {extract_to_resolved}",
                        extract_path=str(extract_to_resolved)
                    )
                    raise ValueError(f"Unsafe extraction path: {extract_to_resolved}")

                # Verify extract_to is within the allowed base temp directory
                try:
                    if not extract_to_resolved.is_relative_to(base_temp_dir):
                        log_error(
                            f"Extraction path outside allowed base directory: {extract_to_resolved} (base: {base_temp_dir})",
                            extract_path=str(extract_to_resolved),
                            base_dir=str(base_temp_dir)
                        )
                        raise ValueError(
                            f"Extraction path must be within {base_temp_dir}, got {extract_to_resolved}"
                        )
                except AttributeError:
                    # Python < 3.9 doesn't have is_relative_to, check if base_temp_dir is a parent
                    try:
                        extract_to_resolved.relative_to(base_temp_dir)
                    except ValueError:
                        log_error(
                            f"Extraction path outside allowed base directory: {extract_to_resolved} (base: {base_temp_dir})",
                            extract_path=str(extract_to_resolved),
                            base_dir=str(base_temp_dir)
                        )
                        raise ValueError(
                            f"Extraction path must be within {base_temp_dir}, got {extract_to_resolved}"
                        ) from None

                if extract_to.exists():
                    shutil.rmtree(extract_to)
                extract_to.mkdir(parents=True, exist_ok=True)

            if not is_already_extracted:
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    # Validate ZIP integrity
                    corrupt_file = zipf.testzip()
                    if corrupt_file is not None:
                        raise ValueError(f"ZIP file is corrupted: {corrupt_file}")

                    # Enforce max uncompressed size
                    total_size = sum(info.file_size for info in zipf.infolist())
                    max_bytes = settings.import_export_max_file_size_mb * 1024 * 1024
                    if total_size > max_bytes:
                        raise ValueError(
                            f"ZIP too large: {total_size / (1024*1024):.1f}MB "
                            f"(max: {settings.import_export_max_file_size_mb}MB)"
                        )

                    extract_root = extract_to.resolve()
                    file_count = 0
                    max_files = 50000  # Prevent zip bombs with many files

                    for info in zipf.infolist():
                        file_count += 1
                        if file_count > max_files:
                            raise ValueError(f"ZIP contains too many files (max: {max_files})")

                        # Skip directories
                        if info.is_dir():
                            continue

                        # Validate filename length
                        if len(info.filename) > MAX_FILENAME_LENGTH:
                            raise ValueError(f"Filename too long: {info.filename[:50]}...")

                        # Validate filename before constructing path
                        if info.filename.startswith('/') or '..' in info.filename.split('/'):
                            raise ValueError(f"ZIP contains unsafe path: {info.filename}")

                        # Check for null bytes in filename
                        if '\x00' in info.filename:
                            raise ValueError(f"ZIP contains invalid filename: {info.filename}")

                        dest_path = (extract_to / info.filename).resolve()

                        # Prevent directory traversal / absolute paths
                        try:
                            dest_path.relative_to(extract_root)
                        except ValueError:
                            raise ValueError(f"ZIP contains unsafe path: {info.filename}") from None

                        # Disallow symlinks (check external attributes)
                        if info.external_attr >> 16 & 0o170000 == 0o120000:
                            raise ValueError(f"ZIP contains symlink: {info.filename}")

                        # Validate file extension
                        file_ext = os.path.splitext(info.filename.lower())[1]
                        if file_ext and file_ext not in ALLOWED_EXTENSIONS:
                            log_warning(
                                f"Skipping file with unsupported extension: {info.filename}",
                                filename=info.filename,
                                extension=file_ext
                            )
                            continue

                        # Extract this validated file
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        zipf.extract(info, extract_to)

                log_info(f"Extracted Day One ZIP to {extract_to}", extract_path=str(extract_to))

            # Find all JSON files (Day One exports one JSON per journal)
            json_files = list(extract_to.glob("*.json"))

            if not json_files:
                raise ValueError("No JSON files found in Day One export")

            if len(json_files) > 100:
                raise ValueError(f"Too many JSON files in export: {len(json_files)} (max: 100)")

            journals = []
            for json_file in json_files:
                # Validate JSON file size
                json_size_mb = json_file.stat().st_size / (1024 * 1024)
                if json_size_mb > MAX_JSON_SIZE_MB:
                    raise ValueError(
                        f"JSON file too large: {json_size_mb:.1f}MB (max: {MAX_JSON_SIZE_MB}MB)"
                    )

                # Journal name is the filename without .json extension
                journal_name = json_file.stem
                if not journal_name or len(journal_name) > 500:
                    log_warning(f"Invalid journal name: {journal_name}, using default")
                    journal_name = "Imported Journal"

                # Parse JSON with error handling
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except UnicodeDecodeError as e:
                    raise ValueError(f"Invalid JSON encoding in {json_file.name}: {e}") from e

                # Validate it's a dictionary
                if not isinstance(data, dict):
                    raise ValueError(f"JSON file {json_file.name} must contain an object, not {type(data).__name__}")

                # Parse Day One export with validation
                try:
                    dayone_export = DayOneExport(**data)
                except Exception as e:
                    raise ValueError(f"Invalid Day One export format in {json_file.name}: {e}") from e

                # Create journal with entries
                journal = DayOneJournal(
                    name=journal_name,
                    entries=dayone_export.entries,
                    export_metadata=dayone_export.metadata,
                    export_version=dayone_export.version,
                    source_file=json_file.name,
                )
                journals.append(journal)

                log_info(
                    f"Parsed Day One journal '{journal_name}' with {len(journal.entries)} entries",
                    journal_name=journal_name,
                    entry_count=len(journal.entries)
                )

            # Check for media directories (Day One uses lowercase)
            media_dir = None
            photos_dir_lower = extract_to / "photos"
            photos_dir_upper = extract_to / "Photos"
            videos_dir_lower = extract_to / "videos"
            videos_dir_upper = extract_to / "Videos"

            # Support both lowercase (common) and uppercase directory names
            photos_exists = photos_dir_lower.exists() or photos_dir_upper.exists()
            videos_exists = videos_dir_lower.exists() or videos_dir_upper.exists()

            if photos_exists or videos_exists:
                media_dir = extract_to
                log_info(
                    f"Found media directory with photos={photos_exists}, videos={videos_exists}",
                    has_photos=photos_exists,
                    has_videos=videos_exists
                )

            return journals, media_dir

        except ValueError as e:
            # Re-raise ValueError for validation errors (don't wrap in IOError)
            log_error(e, zip_path=str(zip_path))
            raise
        except json.JSONDecodeError as e:
            log_error(e, zip_path=str(zip_path))
            raise ValueError(f"Invalid JSON in Day One export: {e}") from e
        except zipfile.BadZipFile as e:
            log_error(e, zip_path=str(zip_path))
            raise ValueError(f"Invalid ZIP file: {e}") from e
        except Exception as e:
            log_error(e, zip_path=str(zip_path))
            raise IOError(f"Failed to parse Day One export: {e}") from e

    @staticmethod
    def validate_export(data: Dict) -> bool:
        """
        Validate that the data looks like a Day One export.

        Args:
            data: Parsed JSON data

        Returns:
            True if valid Day One export, False otherwise
        """
        # Day One exports must have an "entries" array
        if "entries" not in data:
            return False

        # Each entry must have required fields
        entries = data.get("entries", [])
        if not entries:
            return True  # Empty export is valid

        # Check first entry has required fields
        first_entry = entries[0]
        required_fields = ["uuid", "creationDate"]

        for field in required_fields:
            if field not in first_entry:
                log_warning(
                    f"Day One entry missing required field: {field}",
                    missing_field=field
                )
                return False

        return True

    @staticmethod
    def find_media_file(
        media_dir: Path,
        identifier: str,
        md5_hash: Optional[str] = None,
        media_type: str = "photo"
    ) -> Optional[Path]:
        """
        Find a media file in the Day One media directory.

        Day One stores media files using MD5 hash as filename, not the identifier.
        For example: e249a0b05c6158a53c1338330f9bece4.jpeg

        Args:
            media_dir: Root media directory (contains photos/ and videos/)
            identifier: Day One media identifier (UUID) - fallback if MD5 not found
            md5_hash: MD5 hash of the media file (preferred for lookup)
            media_type: "photo" or "video"

        Returns:
            Path to media file if found, None otherwise
        """
        # Try both lowercase and uppercase directory names
        if media_type == "photo":
            search_dirs = [media_dir / "photos", media_dir / "Photos"]
        elif media_type == "video":
            search_dirs = [media_dir / "videos", media_dir / "Videos"]
        else:
            log_warning(f"Unknown media type: {media_type}", media_type=media_type)
            return None

        # Find first existing directory
        search_dir = None
        for dir_path in search_dirs:
            if dir_path.exists():
                search_dir = dir_path
                break

        if not search_dir:
            return None

        # Get allowed extensions from settings (case-insensitive)
        # Filter by media type using common patterns
        if media_type == "photo":
            # Photo extensions: jpg, jpeg, png, gif, webp, heic
            photo_patterns = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic'}
            extensions = [ext for ext in ALLOWED_EXTENSIONS if ext.lower() in photo_patterns]
            # Add uppercase variants for case-insensitive matching
            extensions.extend([ext.upper() for ext in extensions if ext.islower()])
        else:
            # Video extensions: mp4, avi, mov, webm, m4v
            video_patterns = {'.mp4', '.avi', '.mov', '.webm', '.m4v'}
            extensions = [ext for ext in ALLOWED_EXTENSIONS if ext.lower() in video_patterns]
            # Add uppercase variants for case-insensitive matching
            extensions.extend([ext.upper() for ext in extensions if ext.islower()])

        # First, try to find by MD5 hash (Day One's naming convention)
        # Validate MD5 hash before use
        validated_md5 = _validate_md5_hash(md5_hash)
        if validated_md5:
            for ext in extensions:
                media_path = search_dir / f"{validated_md5}{ext}"
                if media_path.exists():
                    return media_path

        # Fallback: try identifier (in case export format varies)
        # Validate identifier before use
        validated_identifier = _validate_identifier(identifier)
        if validated_identifier:
            for ext in extensions:
                media_path = search_dir / f"{validated_identifier}{ext}"
                if media_path.exists():
                    return media_path

        # Last resort: search for any file starting with MD5 or identifier
        # Use already-validated values to prevent metacharacter injection
        if validated_md5:
            for file_path in search_dir.glob(f"{validated_md5}.*"):
                return file_path

        if validated_identifier:
            for file_path in search_dir.glob(f"{validated_identifier}.*"):
                return file_path

        return None
