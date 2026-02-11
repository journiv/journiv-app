"""
Constants for import/export operations.

Centralizes magic numbers and configuration values for better maintainability.
"""


class ProgressStages:
    """Progress percentage milestones for job tracking."""

    # Export job stages
    EXPORT_BUILDING_DATA = 10
    EXPORT_CREATING_ZIP = 50
    EXPORT_FINALIZING = 90

    # Import job stages
    IMPORT_EXTRACTING = 10
    IMPORT_PROCESSING = 30
    IMPORT_FINALIZING = 90

    # Common
    COMPLETED = 100


class ExportConfig:
    """Configuration constants for export operations."""

    EXPORT_VERSION = "1.3"
    DATA_FILENAME = "data.json"


class ImportConfig:
    """Configuration constants for import operations."""

    # File validation
    MAX_FILENAME_LENGTH = 255
    ALLOWED_EXTENSIONS = frozenset({".zip"})

    # Batch processing (for future optimization)
    ENTRY_BATCH_SIZE = 100
    MEDIA_BATCH_SIZE = 50
