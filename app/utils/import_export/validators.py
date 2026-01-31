"""
Validation utilities for import/export data.

Validates data structure and content before processing.
"""
from typing import Dict, Any, List, Optional
from pydantic import ValidationError

from app.schemas.dto import (
    JournivExportDTO,
    JournalDTO,
    EntryDTO,
    MediaDTO,
)
from app.core.logging_config import log_error


class ValidationResult:
    """Result of data validation."""

    def __init__(self):
        self.valid = True
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def add_error(self, error: str):
        """Add an error message."""
        self.valid = False
        self.errors.append(error)

    def add_warning(self, warning: str):
        """Add a warning message."""
        self.warnings.append(warning)

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_import_data(data: Dict[str, Any], source_type: str) -> ValidationResult:
    """
    Validate import data structure.

    Args:
        data: Parsed import data
        source_type: Source type (journiv/markdown/dayone)

    Returns:
        ValidationResult with any errors or warnings
    """
    result = ValidationResult()

    # Validate based on source type
    if source_type.lower() == "journiv":
        result = validate_journiv_export(data)
    else:
        # For other sources, basic validation
        result = validate_basic_structure(data)

    return result


def validate_export_data(data: Dict[str, Any]) -> ValidationResult:
    """
    Validate export data before creating ZIP.

    Args:
        data: Export data to validate

    Returns:
        ValidationResult with any errors or warnings
    """
    return validate_journiv_export(data)


def validate_journiv_export(data: Dict[str, Any]) -> ValidationResult:
    """
    Validate Journiv export format.

    Args:
        data: Export data dictionary

    Returns:
        ValidationResult
    """
    result = ValidationResult()

    try:
        export_dto = JournivExportDTO(**data)

        # Additional validations
        if not export_dto.journals:
            result.add_warning("Export contains no journals")

        total_entries = sum(len(j.entries) for j in export_dto.journals)
        if total_entries == 0:
            result.add_warning("Export contains no entries")

        # Check for duplicate journal titles
        journal_titles = [j.title.lower() for j in export_dto.journals]
        if len(journal_titles) != len(set(journal_titles)):
            result.add_warning("Export contains duplicate journals")

        # Validate each journal
        for idx, journal in enumerate(export_dto.journals):
            journal_result = validate_journal(journal, f"Journal {idx + 1}")
            result.errors.extend(journal_result.errors)
            result.warnings.extend(journal_result.warnings)
            if journal_result.has_errors():
                result.valid = False

    except ValidationError as e:
        result.add_error(f"Invalid export format: {e}")
        log_error(e, context="export_validation")
    except Exception as e:
        # Unexpected exceptions (programming errors, system issues) should propagate
        # rather than being misclassified as validation errors
        log_error(e, context="export_validation_unexpected_error")
        raise

    return result


def validate_journal(journal: JournalDTO, context: str = "Journal") -> ValidationResult:
    """
    Validate a journal DTO.

    Args:
        journal: Journal to validate
        context: Context string for error messages

    Returns:
        ValidationResult
    """
    result = ValidationResult()

    # Check journal title
    if not journal.title or not journal.title.strip():
        result.add_error(f"{context}: Title is required")

    # Check for duplicate entry dates (potential duplicates)
    entry_dates = [e.entry_date for e in journal.entries]
    if len(entry_dates) != len(set(entry_dates)):
        result.add_warning(f"{context}: Contains entries with duplicate dates")

    # Validate each entry
    for idx, entry in enumerate(journal.entries):
        entry_result = validate_entry(entry, f"{context}, Entry {idx + 1}")
        result.errors.extend(entry_result.errors)
        result.warnings.extend(entry_result.warnings)
        if entry_result.has_errors():
            result.valid = False

    return result


def validate_entry(entry: EntryDTO, context: str = "Entry") -> ValidationResult:
    """
    Validate an entry DTO.

    Args:
        entry: Entry to validate
        context: Context string for error messages

    Returns:
        ValidationResult
    """
    result = ValidationResult()

    # Check required fields
    if not entry.is_draft:
        if not entry.content_delta or not entry.content_delta.get("ops"):
            result.add_warning(f"{context}: Content is empty")

    if not entry.entry_date:
        result.add_error(f"{context}: Entry date is required")

    # Validate GPS coordinates if present
    if entry.latitude is not None:
        if not (-90 <= entry.latitude <= 90):
            result.add_error(f"{context}: Invalid latitude (must be -90 to 90)")

    if entry.longitude is not None:
        if not (-180 <= entry.longitude <= 180):
            result.add_error(f"{context}: Invalid longitude (must be -180 to 180)")

    # Validate media
    for idx, media in enumerate(entry.media):
        media_result = validate_media(media, f"{context}, Media {idx + 1}")
        result.errors.extend(media_result.errors)
        result.warnings.extend(media_result.warnings)
        if media_result.has_errors():
            result.valid = False

    return result


def validate_media(media: MediaDTO, context: str = "Media") -> ValidationResult:
    """
    Validate a media DTO.

    Args:
        media: Media to validate
        context: Context string for error messages

    Returns:
        ValidationResult
    """
    result = ValidationResult()

    # Check required fields
    if not media.filename or not media.filename.strip():
        result.add_error(f"{context}: Filename is required")

    if not media.media_type or not media.media_type.strip():
        result.add_error(f"{context}: Media type is required")

    # Validate dimensions if present
    if media.width is not None and media.width <= 0:
        result.add_error(f"{context}: Width must be positive")

    if media.height is not None and media.height <= 0:
        result.add_error(f"{context}: Height must be positive")

    # Validate duration if present
    if media.duration is not None and media.duration < 0:
        result.add_error(f"{context}: Duration cannot be negative")

    return result


def validate_basic_structure(data: Dict[str, Any]) -> ValidationResult:
    """
    Basic validation for non-Journiv import sources.

    Args:
        data: Import data

    Returns:
        ValidationResult
    """
    result = ValidationResult()

    if not data:
        result.add_error("Import data is empty")
        return result

    # Check for common fields
    if "journals" not in data and "entries" not in data:
        result.add_warning(
            "Import data doesn't contain 'journals' or 'entries' field. "
            "Parser may need custom handling."
        )

    return result


def validate_file_path(file_path: str, max_size_mb: Optional[int] = None) -> ValidationResult:
    """
    Validate an uploaded file path.

    Args:
        file_path: Path to file
        max_size_mb: Maximum allowed size in MB

    Returns:
        ValidationResult
    """
    result = ValidationResult()

    from pathlib import Path

    path = Path(file_path)

    if not path.exists():
        result.add_error(f"File does not exist: {file_path}")
        return result

    if not path.is_file():
        result.add_error(f"Path is not a file: {file_path}")
        return result

    file_size = path.stat().st_size
    if max_size_mb:
        from app.utils.import_export.media_handler import MediaHandler
        if not MediaHandler.validate_file_size(file_size, max_size_mb):
            result.add_error(
                f"File too large: {file_size / (1024*1024):.1f}MB "
                f"(max: {max_size_mb}MB)"
            )

    return result
