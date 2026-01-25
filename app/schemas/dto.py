"""
Data Transfer Objects (DTOs) for import/export operations.

These DTOs represent the serialization format for Journiv data exports
and the expected format for imports from various sources.

IMPORTANT: This file maps to the ACTUAL database schema, not an idealized version.
Fields marked as placeholders are not yet implemented in the database but reserved
for future use to maintain backward compatibility with the export format.
"""
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator

from app.models.enums import JobStatus, ImportSourceType, ExportType


# ============================================================================
# Core DTOs - Mapped to Actual Database Schema
# ============================================================================

class MediaDTO(BaseModel):
    """
    Media file metadata for import/export.

    Maps to: EntryMedia model (app/models/entry.py)
    """
    # Actual EntryMedia fields
    filename: str = Field(..., description="Original filename")
    file_path: Optional[str] = Field(None, description="File path (relative to media root)")
    media_type: str = Field(..., description="Media type: image, video, audio, unknown")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type (image/jpeg, video/mp4, etc.)")
    checksum: Optional[str] = Field(None, description="SHA256 checksum for deduplication")

    # Image/video dimensions
    width: Optional[int] = Field(None, description="Image/video width in pixels")
    height: Optional[int] = Field(None, description="Image/video height in pixels")

    # Audio/video duration
    duration: Optional[float] = Field(None, description="Audio/video duration in seconds")

    # Accessibility
    alt_text: Optional[str] = Field(None, description="Alt text for accessibility")

    # Additional metadata
    file_metadata: Optional[str] = Field(None, description="JSON metadata string")
    thumbnail_path: Optional[str] = Field(None, description="Path to thumbnail")
    upload_status: str = Field(
        default="completed",
        description="Upload status: pending, processing, completed, failed"
    )

    # Timestamps (inherited from BaseModel)
    created_at: datetime = Field(..., description="Media creation time in UTC")
    updated_at: datetime = Field(..., description="Media last update time in UTC")

    # PLACEHOLDER: For import compatibility, not in database yet
    caption: Optional[str] = Field(None, description="PLACEHOLDER: Media caption (not stored in DB, use alt_text)")

    # External provider fields
    external_provider: Optional[str] = Field(None, description="External provider name (e.g., 'immich')")
    external_asset_id: Optional[str] = Field(None, description="Asset ID in the external provider's system")
    external_url: Optional[str] = Field(None, description="Full URL to the asset in the external provider")
    external_created_at: Optional[datetime] = Field(None, description="Creation date from external provider")
    external_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata from external provider")

    # Import tracking (not exported for regular users in previous versions, but now used for external linking)
    external_id: Optional[str] = Field(None, description="Original ID from source system (legacy use) or external asset ID")


class MoodLogDTO(BaseModel):
    """
    Mood log entry for import/export.

    Maps to: MoodLog model (app/models/mood.py)
    Note: Mood is stored via relationship to Mood definition, not directly on Entry.
    """
    # Actual MoodLog fields
    mood_name: str = Field(..., description="Name of the mood (references Mood.name)")
    note: Optional[str] = Field(None, max_length=500, description="Optional note about the mood")
    logged_date: date = Field(..., description="Date this mood represents")
    logged_datetime_utc: datetime = Field(..., description="UTC timestamp when mood was logged")
    logged_timezone: str = Field(default="UTC", description="IANA timezone for the mood log")

    # Timestamps (inherited from BaseModel)
    created_at: datetime = Field(..., description="Mood log creation time in UTC")
    updated_at: datetime = Field(..., description="Mood log last update time in UTC")

    # PLACEHOLDER: For import compatibility with other apps
    mood_score: Optional[int] = Field(None, ge=-5, le=5, description="PLACEHOLDER: Mood score (not in DB)")


class EntryDTO(BaseModel):
    """
    Journal entry for import/export.

    Maps to: Entry model (app/models/entry.py)
    """
    # Actual Entry fields
    title: Optional[str] = Field(None, max_length=300, description="Entry title")
    content: Optional[str] = Field(None, description="Entry content (plain text or markdown)")
    entry_date: date = Field(..., description="User's local date for this entry")
    entry_datetime_utc: datetime = Field(..., description="UTC timestamp when entry occurred")
    entry_timezone: str = Field(default="UTC", description="IANA timezone for entry context")
    word_count: int = Field(default=0, description="Word count")
    is_pinned: bool = Field(default=False, description="Whether entry is pinned")

    # Structured location fields (persisted in database after migration d8f3a9e2b1c4)
    location_json: Optional[Dict[str, Any]] = Field(
        None,
        description="Structured location data (persisted as JSON/JSONB in database): {name, street, locality, admin_area, country, latitude, longitude, timezone}. This DTO field maps directly to the database location_json JSON/JSONB column when saved."
    )
    latitude: Optional[float] = Field(None, description="GPS latitude (persisted as Float in database after migration)")
    longitude: Optional[float] = Field(None, description="GPS longitude (persisted as Float in database after migration)")

    # Structured weather fields (new in DB)
    weather_json: Optional[Dict[str, Any]] = Field(
        None,
        description="Structured weather data: {temp_c, condition, code, service}"
    )
    weather_summary: Optional[str] = Field(None, description="Human-readable weather summary")
    import_metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Import metadata for preserving source details"
    )

    # PLACEHOLDER: For backward compatibility with other apps
    temperature: Optional[float] = Field(None, description="PLACEHOLDER: Temperature in Celsius (use weather_json instead)")

    # Related data
    tags: List[str] = Field(default_factory=list, description="List of tag names")
    mood_log: Optional[MoodLogDTO] = Field(None, description="Associated mood log")
    media: List[MediaDTO] = Field(default_factory=list, description="Attached media files")

    # Prompt information (if entry was created from prompt)
    prompt_text: Optional[str] = Field(None, description="Original prompt text if entry used a prompt")

    # Timestamps (inherited from BaseModel)
    created_at: datetime = Field(..., description="Entry creation time in UTC")
    updated_at: datetime = Field(..., description="Entry last update time in UTC")

    # Import tracking (not exported for regular users)
    external_id: Optional[str] = Field(None, description="Original ID from source system")

    @field_validator('entry_timezone', mode='before')
    @classmethod
    def normalize_timezone(cls, v):
        """Normalize timezone to ensure it's never None or empty."""
        if not v or v == "":
            return "UTC"
        return v

    @field_validator('tags', mode='before')
    @classmethod
    def normalize_tags(cls, v):
        """Normalize tags to lowercase."""
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        try:
            iterable = list(v)
        except TypeError:
            iterable = [v]
        return [
            tag.strip().lower()
            for tag in iterable
            if isinstance(tag, str) and tag.strip()
        ]


class JournalDTO(BaseModel):
    """
    Journal (notebook) for import/export.

    Maps to: Journal model (app/models/journal.py)
    """
    # Actual Journal fields
    title: str = Field(..., description="Journal title")
    description: Optional[str] = Field(None, max_length=1000, description="Journal description")
    color: Optional[str] = Field(None, description="Journal color (hex code from JournalColor enum)")
    icon: Optional[str] = Field(None, max_length=50, description="Journal icon name")
    is_favorite: bool = Field(default=False, description="Whether journal is marked as favorite")
    is_archived: bool = Field(default=False, description="Whether journal is archived")

    # Denormalized fields
    entry_count: int = Field(default=0, description="Number of entries (denormalized)")
    last_entry_at: Optional[datetime] = Field(None, description="Timestamp of last entry")
    import_metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Import metadata for preserving source details"
    )

    # Entries in this journal
    entries: List[EntryDTO] = Field(default_factory=list, description="Journal entries")

    # Timestamps (inherited from BaseModel)
    created_at: datetime = Field(..., description="Journal creation time in UTC")
    updated_at: datetime = Field(..., description="Journal last update time in UTC")

    # Import tracking (not exported for regular users)
    external_id: Optional[str] = Field(None, description="Original ID from source system")


class MoodDefinitionDTO(BaseModel):
    """
    Mood definition for import/export.

    Maps to: Mood model (app/models/mood.py)
    IMPORTANT: Mood model only has name, icon, and category.
    Score, emoji, and color are PLACEHOLDERS.
    """
    # Actual Mood fields
    name: str = Field(..., description="Mood name (unique, lowercase)")
    category: str = Field(..., description="Mood category: positive, negative, neutral")
    icon: Optional[str] = Field(None, max_length=50, description="Mood icon")

    # PLACEHOLDER: For import compatibility with other apps, not in database
    emoji: Optional[str] = Field(None, description="PLACEHOLDER: Mood emoji (not in DB, use icon)")
    score: Optional[int] = Field(None, ge=-5, le=5, description="PLACEHOLDER: Mood score (not in DB)")
    color: Optional[str] = Field(None, description="PLACEHOLDER: Mood color (not in DB)")


class UserSettingsDTO(BaseModel):
    """
    User settings for import/export.

    Maps to: UserSettings model (app/models/user.py)
    """
    # Actual UserSettings fields
    theme: str = Field(default="light", description="Theme preference: light, dark, auto")
    time_zone: str = Field(default="UTC", description="User's timezone (IANA format)")
    daily_prompt_enabled: bool = Field(default=True, description="Whether daily prompts are enabled")
    push_notifications: bool = Field(default=True, description="Whether push notifications are enabled")
    reminder_time: Optional[str] = Field(None, description="Daily reminder time in HH:MM format")
    writing_goal_daily: int = Field(default=500, description="Daily writing goal in words")

    # PLACEHOLDER: For import compatibility, not in database yet
    date_format: Optional[str] = Field(None, description="PLACEHOLDER: Date format preference (not in DB)")
    time_format: Optional[str] = Field(None, description="PLACEHOLDER: Time format 12h/24h (not in DB)")
    first_day_of_week: Optional[int] = Field(None, ge=0, le=6, description="PLACEHOLDER: First day of week (not in DB)")


# ============================================================================
# Top-Level Export DTO
# ============================================================================

class JournivExportDTO(BaseModel):
    """
    Complete Journiv data export.

    This is the top-level structure for full exports.
    """
    # Metadata
    export_version: str = Field("1.0", description="Export format version")
    export_date: datetime = Field(..., description="When export was created (UTC)")
    app_version: str = Field(..., description="Journiv version that created export")

    # User information (from User model)
    user_email: str = Field(..., description="User's email")
    user_name: Optional[str] = Field(None, description="User's display name")
    user_settings: Optional[UserSettingsDTO] = Field(None, description="User preferences")

    # Data
    journals: List[JournalDTO] = Field(..., description="All journals with their entries")
    mood_definitions: List[MoodDefinitionDTO] = Field(default_factory=list, description="System mood definitions")

    # Statistics (for reference only, not imported)
    stats: Optional[Dict[str, Any]] = Field(
        None,
        description="Export statistics (journal count, entry count, media count, etc.)"
    )


# ============================================================================
# Import/Export Request/Response DTOs
# ============================================================================

class ImportJobCreateRequest(BaseModel):
    """
    Request to create an import job.

    Maps to: ImportJob model (app/models/import_job.py)
    """
    source_type: ImportSourceType = Field(..., description="Source type: journiv, markdown, dayone")
    # file_path is set by upload endpoint, not by client


class ExportJobCreateRequest(BaseModel):
    """
    Request to create an export job.

    Maps to: ExportJob model (app/models/export_job.py)
    """
    export_type: ExportType = Field(..., description="Export type: full, journal")
    journal_ids: Optional[List[str]] = Field(None, description="Specific journal IDs for selective export")
    include_media: bool = Field(True, description="Whether to include media files")


class JobStatusResponse(BaseModel):
    """
    Generic job status response.

    Maps to: ImportJob and ExportJob models
    """
    id: str = Field(..., description="Job ID (UUID)")
    status: JobStatus = Field(..., description="Job status: pending, running, completed, failed, cancelled")
    progress: int = Field(..., ge=0, le=100, description="Progress percentage 0-100")
    total_items: int = Field(..., description="Total number of items to process")
    processed_items: int = Field(..., description="Number of items processed so far")
    created_at: datetime = Field(..., description="When job was created (UTC)")
    completed_at: Optional[datetime] = Field(None, description="When job completed or failed (UTC)")
    result_data: Optional[Dict[str, Any]] = Field(None, description="Result statistics (JSON)")
    errors: Optional[List[str]] = Field(None, description="Error messages (JSON array)")
    warnings: Optional[List[str]] = Field(None, description="Warning messages (JSON array)")


class ExportJobStatusResponse(JobStatusResponse):
    """
    Export job status with download info.

    Maps to: ExportJob model (app/models/export_job.py)
    """
    export_type: ExportType = Field(..., description="Export type: full, journal")
    include_media: bool = Field(..., description="Whether media is included")
    file_path: Optional[str] = Field(None, description="Path to export file (internal use)")
    file_size: Optional[int] = Field(None, description="Export file size in bytes")
    download_url: Optional[str] = Field(None, description="URL to download export file")


class ImportJobStatusResponse(JobStatusResponse):
    """
    Import job status.

    Maps to: ImportJob model (app/models/import_job.py)
    """
    source_type: ImportSourceType = Field(..., description="Source type: journiv, markdown, dayone")


# ============================================================================
# Import Result DTOs
# ============================================================================

class ImportResultSummary(BaseModel):
    """
    Summary of import operation results.

    Used in ImportJob.result_data (JSON field)
    """
    journals_created: int = Field(0, description="Number of journals created")
    entries_created: int = Field(0, description="Number of entries created")
    media_files_imported: int = Field(0, description="Number of media files imported")
    tags_created: int = Field(0, description="Number of new tags created")
    moods_created: int = Field(0, description="Number of new mood definitions created")
    mood_logs_created: int = Field(0, description="Number of mood logs created")

    # Deduplication stats
    media_files_deduplicated: int = Field(0, description="Media files deduplicated by checksum")
    tags_reused: int = Field(0, description="Existing tags reused by name")
    moods_reused: int = Field(0, description="Existing mood definitions reused")

    # Skipped items
    entries_skipped: int = Field(0, description="Entries skipped (duplicates or errors)")
    media_files_skipped: int = Field(0, description="Media files skipped (errors)")

    # Warnings and errors (non-fatal issues that occurred during import)
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-fatal warnings that occurred during import (e.g., invalid colors, unknown types)"
    )
    warning_categories: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of warnings by category (e.g., 'Skipped due to size', 'Skipped due to dimensions')"
    )
    id_mappings: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="Mapping of external IDs to newly created IDs grouped by entity type"
    )


# ============================================================================
# Schema Compatibility Notes
# ============================================================================
"""
DATABASE SCHEMA MAPPING NOTES:

2. MOOD SYSTEM:
   - Mood definitions: Stored in 'mood' table (name, icon, category)
   - Mood logs: Stored in 'mood_log' table (links user, entry, mood)
   - Entry relationship: Optional one-to-one via Entry.mood_log
   - Placeholders: score, emoji, color (not in database)

3. ENTRY LOCATION:
   - Database (after migration d8f3a9e2b1c4):
     * location_json: JSON/JSONB field storing structured location data (persisted)
     * latitude: Float field for GPS latitude (persisted)
     * longitude: Float field for GPS longitude (persisted)
   - Legacy (removed): Single 'location' varchar field (max 200 chars) was removed in migration d8f3a9e2b1c4
   - DTO field location_json: Maps directly to database location_json JSON/JSONB column (persisted)
   - DTO fields latitude, longitude: Map directly to database Float columns (persisted)
   - Placeholder: temperature (not in database, use weather_json instead)

4. ENTRY MEDIA:
   - Stored in 'entry_media' table with full metadata
   - Fields: file_path, original_filename, file_size, mime_type, media_type
   - Optional: thumbnail_path, width, height, duration, alt_text, checksum
   - Upload tracking: upload_status, processing_error, file_metadata

5. TAGS:
   - Stored in 'tag' table (user-specific, case-insensitive)
   - Many-to-many with entries via 'entry_tag_link' table
   - Normalized to lowercase in database

6. USER SETTINGS:
   - Stored in 'user_settings' table (one-to-one with user)
   - Fields: theme, time_zone, daily_prompt_enabled, push_notifications,
     reminder_time, writing_goal_daily
   - Placeholders: date_format, time_format, first_day_of_week

7. TIMESTAMPS:
   - All models inherit from BaseModel: id, created_at, updated_at, is_deleted
   - Entry has: entry_date (date), entry_datetime_utc (datetime), entry_timezone (str)
   - MoodLog has: logged_date (date), logged_datetime_utc (datetime), logged_timezone (str)

8. ENUM TYPES:
   - MediaType: image, video, audio, unknown
   - UploadStatus: pending, processing, completed, failed
   - MoodCategory: positive, negative, neutral
   - Theme: light, dark, auto
   - JournalColor: 20+ predefined hex colors
   - JobStatus: pending, running, completed, failed, cancelled
   - ImportSourceType: journiv, markdown, dayone
   - ExportType: full, journal

PLACEHOLDER FIELDS (for future implementation):
- MediaDTO: caption (use alt_text instead)
- MoodDefinitionDTO: emoji, score, color (only name, icon, category exist)
- MoodLogDTO: mood_score (not stored, added for Day one import compatibility)
- EntryDTO: temperature (not persisted in DB, use weather_json instead; added for Day One import compatibility)
- UserSettingsDTO: date_format, time_format, first_day_of_week

TODO: These placeholders maintain compatibility with import formats from other apps
but are not stored in the database. They should be mapped to existing fields
or skipped during import.
"""
