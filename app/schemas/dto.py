"""
Data Transfer Objects (DTOs) for import/export operations.

These DTOs represent the serialization format for Journiv data exports
and the expected format for imports from various sources.

IMPORTANT: This file maps to the ACTUAL database schema, not an idealized version.
Fields marked as placeholders are optional import/export conveniences and are not
persisted directly in the database.
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import (
    ExportType,
    GoalFrequency,
    GoalLogSource,
    GoalLogStatus,
    GoalType,
    ImportSourceType,
    JobStatus,
)

# ============================================================================
# Core DTOs - Mapped to Actual Database Schema
# ============================================================================

class MomentMediaDTO(BaseModel):
    """
    Media file metadata for import/export.

    Maps to: MomentMedia in app/models/moment.py
    """
    # Actual MomentMedia fields
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


class MomentMoodActivityDTO(BaseModel):
    """
    Mood/activity association within a moment for import/export.
    """
    mood_name: Optional[str] = Field(None, description="Mood name (references Mood.name)")
    activity_name: Optional[str] = Field(None, description="Activity name (user-defined)")
    mood_external_id: Optional[str] = Field(
        None,
        description="Original mood ID from export (preferred for accurate mapping)",
    )
    activity_external_id: Optional[str] = Field(
        None,
        description="Original activity ID from export (preferred for accurate mapping)",
    )


class MomentDTO(BaseModel):
    """
    Moment for import/export.

    Maps to: Moment model (app/models/moment.py) and MomentMoodActivity links.
    """
    logged_at_utc: datetime = Field(..., description="UTC timestamp when moment occurred")
    logged_date_tz: date = Field(..., description="User's local date for this moment")
    logged_timezone: str = Field(default="UTC", description="IANA timezone for moment context")
    note: Optional[str] = Field(None, max_length=500, description="Optional note for the moment")
    location_json: Optional[Dict[str, Any]] = Field(None, description="Structured location data")
    latitude: Optional[float] = Field(None, description="GPS latitude")
    longitude: Optional[float] = Field(None, description="GPS longitude")
    weather_json: Optional[Dict[str, Any]] = Field(None, description="Structured weather data")
    weather_summary: Optional[str] = Field(None, description="Human-readable weather summary")
    is_pinned: bool = Field(default=False, description="Whether moment is pinned")
    prompt_text: Optional[str] = Field(None, description="Original prompt text if moment used a prompt")
    tags: List[str] = Field(default_factory=list, description="List of tag names")
    people_external_ids: List[str] = Field(
        default_factory=list,
        description="References to exported people records by external_id",
    )
    primary_mood_name: Optional[str] = Field(None, description="Primary mood name")
    mood_activity: List[MomentMoodActivityDTO] = Field(default_factory=list, description="Mood/activity links")
    media: List["MomentMediaDTO"] = Field(default_factory=list, description="Media attached to moment")
    entry: Optional["EntryDTO"] = Field(
        None,
        description="Optional narrative entry attached to this moment",
    )

    created_at: datetime = Field(..., description="Moment creation time in UTC")
    updated_at: datetime = Field(..., description="Moment last update time in UTC")
    external_id: Optional[str] = Field(None, description="Original ID from source system")
    primary_mood_external_id: Optional[str] = Field(
        None,
        description="Original mood ID for primary mood (preferred for mapping)",
    )

    @field_validator('logged_timezone', mode='before')
    @classmethod
    def normalize_timezone(cls, v):
        """Normalize timezone to ensure it's never None or empty."""
        if not v or v == "":
            return "UTC"
        return v

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_logged_fields(cls, data):
        """Accept legacy import payload keys while preserving moment-first names."""
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "logged_at_utc" not in normalized and "logged_at" in normalized:
            normalized["logged_at_utc"] = normalized["logged_at"]
        if "logged_date_tz" not in normalized and "logged_date" in normalized:
            normalized["logged_date_tz"] = normalized["logged_date"]
        return normalized

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


class EntryDTO(BaseModel):
    """
    Journal entry for import/export.

    Maps to: Entry model (app/models/entry.py)
    Content-only — all metadata (location, weather, tags, media, mood) lives on MomentDTO.
    """
    # Actual Entry fields
    title: Optional[str] = Field(None, max_length=300, description="Entry title")
    content_delta: Optional[Dict[str, Any]] = Field(
        None,
        description="Entry content as Quill Delta JSON (source of truth)",
    )
    content_plain_text: Optional[str] = Field(
        None,
        description="Plain-text extraction from content_delta",
    )
    word_count: int = Field(default=0, description="Word count")
    is_draft: bool = Field(default=False, description="Whether entry is a draft")
    import_metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Import metadata for preserving source details"
    )

    # Parent journal reference (for moment-first export/import linking)
    journal_external_id: Optional[str] = Field(
        None,
        description="Journal external ID this entry belongs to",
    )

    # Timestamps (inherited from BaseModel)
    created_at: datetime = Field(..., description="Entry creation time in UTC")
    updated_at: datetime = Field(..., description="Entry last update time in UTC")

    # Import tracking
    external_id: Optional[str] = Field(None, description="Original ID from source system")

    @model_validator(mode='after')
    def validate_content_present(self) -> 'EntryDTO':
        """Ensure non-draft entries have some form of content."""
        if not self.is_draft:
            ops = self.content_delta.get("ops") if isinstance(self.content_delta, dict) else None
            has_delta_content = False
            if isinstance(ops, list):
                for op in ops:
                    if not isinstance(op, dict) or "insert" not in op:
                        continue
                    insert_value = op.get("insert")
                    if isinstance(insert_value, str):
                        if insert_value.strip() != "":
                            has_delta_content = True
                            break
                    elif insert_value is not None:
                        # Non-string insert payloads (embeds) count as content.
                        has_delta_content = True
                        break
            has_plain_text = (
                self.content_plain_text is not None
                and self.content_plain_text.strip() != ""
            )
            has_title = self.title is not None and self.title.strip() != ""
            if not any([has_delta_content, has_plain_text, has_title]):
                raise ValueError(
                    "Non-draft entry must have content (title, delta, or plain text)"
                )
        return self


class PersonDTO(BaseModel):
    """
    Person catalog entry for import/export.

    Maps to: Person model (app/models/person.py)
    """
    name: str = Field(..., description="Display name")
    nickname: Optional[str] = Field(None, description="Optional nickname")
    note: Optional[str] = Field(None, description="Optional profile note")
    profile_image_path: Optional[str] = Field(
        None, description="Optional backend-managed profile image path"
    )
    archived_at: Optional[datetime] = Field(None, description="Archived timestamp in UTC")
    created_at: datetime = Field(..., description="Person creation time in UTC")
    updated_at: datetime = Field(..., description="Person last update time in UTC")
    external_id: Optional[str] = Field(None, description="Original ID from source system")


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

    # Metadata fields
    last_entry_at: Optional[datetime] = Field(None, description="Timestamp of last entry")
    import_metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Import metadata for preserving source details"
    )

    # Timestamps (inherited from BaseModel)
    created_at: datetime = Field(..., description="Journal creation time in UTC")
    updated_at: datetime = Field(..., description="Journal last update time in UTC")

    # Import tracking
    external_id: Optional[str] = Field(None, description="Original ID from source system")


class MoodDefinitionDTO(BaseModel):
    """
    Mood definition for import/export.

    Maps to: Mood model (app/models/mood.py)
    """
    # Actual Mood fields
    name: str = Field(..., description="Mood name (unique, lowercase)")
    category: str = Field(..., description="Mood category: positive, negative, neutral")
    icon: Optional[str] = Field(None, max_length=50, description="Mood icon")
    key: Optional[str] = Field(None, description="Mood key (stable identifier)")
    color_value: Optional[int] = Field(None, description="Mood color value")
    score: Optional[int] = Field(None, ge=1, le=5, description="Mood score (1-5)")
    position: int = Field(default=0, description="Mood sort position")
    is_active: bool = Field(default=True, description="Whether mood is active/visible")
    is_custom: bool = Field(default=False, description="Whether mood is user-specific")
    created_at: Optional[datetime] = Field(None, description="Mood creation time in UTC")
    updated_at: Optional[datetime] = Field(None, description="Mood last update time in UTC")
    external_id: Optional[str] = Field(None, description="Original ID from source system")

    # PLACEHOLDER: For import compatibility with other apps, not in database
    emoji: Optional[str] = Field(None, description="PLACEHOLDER: Mood emoji (not in DB, use icon)")
    color: Optional[str] = Field(None, description="PLACEHOLDER: Mood color (not in DB)")


class MoodPreferenceDTO(BaseModel):
    """
    User mood order preferences for import/export.
    """
    mood_external_id: str = Field(..., description="Original mood ID from export")
    sort_order: int = Field(default=0, description="User-specific sort order")
    created_at: datetime = Field(..., description="Preference creation time in UTC")
    updated_at: datetime = Field(..., description="Preference last update time in UTC")


class MoodGroupDTO(BaseModel):
    """
    Mood group for import/export.

    Maps to: MoodGroup model (app/models/mood_group.py)
    """
    name: str = Field(..., description="Mood group name")
    icon: Optional[str] = Field(None, description="Mood group icon")
    color_value: Optional[int] = Field(None, description="Mood group color value")
    position: int = Field(default=0, description="Mood group sort position")
    is_custom: bool = Field(default=True, description="Whether group is user-specific")
    created_at: datetime = Field(..., description="Mood group creation time in UTC")
    updated_at: datetime = Field(..., description="Mood group last update time in UTC")
    external_id: Optional[str] = Field(None, description="Original ID from source system")


class MoodGroupLinkDTO(BaseModel):
    """
    Link between mood group and mood for import/export.
    """
    mood_group_external_id: str = Field(..., description="Original mood group ID")
    mood_external_id: str = Field(..., description="Original mood ID")
    position: int = Field(default=0, description="Position within the group")
    created_at: datetime = Field(..., description="Link creation time in UTC")
    updated_at: datetime = Field(..., description="Link last update time in UTC")


class MoodGroupPreferenceDTO(BaseModel):
    """
    User mood group order preferences for import/export.
    """
    mood_group_external_id: str = Field(..., description="Original mood group ID")
    sort_order: int = Field(default=0, description="User-specific sort order")
    created_at: datetime = Field(..., description="Preference creation time in UTC")
    updated_at: datetime = Field(..., description="Preference last update time in UTC")


class ActivityGroupDTO(BaseModel):
    """
    Activity group for import/export.

    Maps to: ActivityGroup model (app/models/activity_group.py)
    """
    name: str = Field(..., description="Activity group name")
    color_value: Optional[int] = Field(None, description="Activity group color value")
    icon: Optional[str] = Field(None, description="Activity group icon")
    position: int = Field(default=0, description="Activity group sort position")
    created_at: datetime = Field(..., description="Activity group creation time in UTC")
    updated_at: datetime = Field(..., description="Activity group last update time in UTC")
    external_id: Optional[str] = Field(None, description="Original ID from source system")


class ActivityDTO(BaseModel):
    """
    Activity for import/export.

    Maps to: Activity model (app/models/activity.py)
    """
    name: str = Field(..., description="Activity name")
    icon: Optional[str] = Field(None, description="Activity icon")
    color: Optional[str] = Field(None, description="Activity color")
    position: int = Field(default=0, description="Activity sort position")
    group_external_id: Optional[str] = Field(None, description="Original activity group ID")
    created_at: datetime = Field(..., description="Activity creation time in UTC")
    updated_at: datetime = Field(..., description="Activity last update time in UTC")
    external_id: Optional[str] = Field(None, description="Original ID from source system")


class GoalCategoryDTO(BaseModel):
    """
    Goal category for import/export.

    Maps to: GoalCategory model (app/models/goal_category.py)
    """
    name: str = Field(..., description="Goal category name")
    color_value: Optional[int] = Field(None, description="Goal category color value")
    icon: Optional[str] = Field(None, description="Goal category icon")
    position: int = Field(default=0, description="Goal category sort position")
    created_at: datetime = Field(..., description="Goal category creation time in UTC")
    updated_at: datetime = Field(..., description="Goal category last update time in UTC")
    external_id: Optional[str] = Field(None, description="Original ID from source system")


class GoalDTO(BaseModel):
    """
    Goal definition for import/export.

    Maps to: Goal model (app/models/goal.py)
    """
    title: str = Field(..., description="Goal title")
    goal_type: GoalType = Field(default=GoalType.ACHIEVE, description="Goal type")
    frequency_type: GoalFrequency = Field(default=GoalFrequency.DAILY, description="Goal frequency")
    target_count: int = Field(default=1, ge=1, description="Target count for completion")
    reminder_time: Optional[str] = Field(None, description="Reminder time in HH:MM")
    is_paused: bool = Field(default=False, description="Whether goal is paused")
    icon: Optional[str] = Field(None, description="Goal icon")
    color_value: Optional[int] = Field(None, description="Goal color value")
    position: int = Field(default=0, description="Goal sort position")
    archived_at: Optional[datetime] = Field(None, description="Archived timestamp if any")
    activity_external_id: Optional[str] = Field(None, description="Original activity ID")
    category_external_id: Optional[str] = Field(None, description="Original goal category ID")
    created_at: datetime = Field(..., description="Goal creation time in UTC")
    updated_at: datetime = Field(..., description="Goal last update time in UTC")
    external_id: Optional[str] = Field(None, description="Original ID from source system")


class GoalLogDTO(BaseModel):
    """
    Goal log for import/export.

    Maps to: GoalLog model (app/models/goal.py)
    """
    goal_external_id: str = Field(..., description="Original goal ID")
    logged_date: date = Field(..., description="Date the log applies to")
    period_start: date = Field(..., description="Period start date")
    period_end: date = Field(..., description="Period end date")
    status: GoalLogStatus = Field(..., description="Goal log status")
    count: int = Field(default=0, description="Progress count")
    source: GoalLogSource = Field(default=GoalLogSource.AUTO, description="Log source")
    last_updated_at: datetime = Field(..., description="Last updated timestamp")
    moment_external_id: Optional[str] = Field(None, description="Original moment ID")
    created_at: datetime = Field(..., description="Log creation time in UTC")
    updated_at: datetime = Field(..., description="Log last update time in UTC")
    external_id: Optional[str] = Field(None, description="Original ID from source system")


class GoalManualLogDTO(BaseModel):
    """
    Manual goal log for import/export.

    Maps to: GoalManualLog model (app/models/goal.py)
    """
    goal_external_id: str = Field(..., description="Original goal ID")
    logged_date: date = Field(..., description="Logged date")
    status: GoalLogStatus = Field(..., description="Manual log status")
    created_at: datetime = Field(..., description="Manual log creation time in UTC")
    updated_at: datetime = Field(..., description="Manual log last update time in UTC")
    external_id: Optional[str] = Field(None, description="Original ID from source system")


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
    start_of_week_day: int = Field(default=0, ge=0, le=6, description="Week start day (0=Mon ... 6=Sun)")

    # PLACEHOLDER: For import compatibility, not in database yet
    date_format: Optional[str] = Field(None, description="PLACEHOLDER: Date format preference (not in DB)")
    time_format: Optional[str] = Field(None, description="PLACEHOLDER: Time format 12h/24h (not in DB)")
    first_day_of_week: Optional[int] = Field(None, ge=0, le=6, description="PLACEHOLDER: First day of week (legacy)")


# ============================================================================
# Top-Level Export DTO
# ============================================================================

class JournivExportDTO(BaseModel):
    """
    Complete Journiv data export.

    This is the top-level structure for full exports.
    """
    # Metadata
    export_version: str = Field("1.5", description="Export format version")
    export_date: datetime = Field(..., description="When export was created (UTC)")
    app_version: str = Field(..., description="Journiv version that created export")

    # User information (from User model)
    user_email: str = Field(..., description="User's email")
    user_name: Optional[str] = Field(None, description="User's display name")
    user_settings: Optional[UserSettingsDTO] = Field(None, description="User preferences")

    # Data
    journals: List[JournalDTO] = Field(..., description="All journals (metadata/library)")
    mood_definitions: List[MoodDefinitionDTO] = Field(default_factory=list, description="Mood definitions (system + custom)")
    mood_preferences: List[MoodPreferenceDTO] = Field(default_factory=list, description="User mood preferences")
    mood_groups: List[MoodGroupDTO] = Field(default_factory=list, description="Mood groups")
    mood_group_links: List[MoodGroupLinkDTO] = Field(default_factory=list, description="Mood group links")
    mood_group_preferences: List[MoodGroupPreferenceDTO] = Field(default_factory=list, description="User mood group preferences")
    activities: List[ActivityDTO] = Field(default_factory=list, description="User activities")
    activity_groups: List[ActivityGroupDTO] = Field(default_factory=list, description="Activity groups")
    people: List[PersonDTO] = Field(default_factory=list, description="User-defined people catalog")
    goal_categories: List[GoalCategoryDTO] = Field(default_factory=list, description="Goal categories")
    goals: List[GoalDTO] = Field(default_factory=list, description="Goals")
    goal_logs: List[GoalLogDTO] = Field(default_factory=list, description="Goal logs")
    goal_manual_logs: List[GoalManualLogDTO] = Field(default_factory=list, description="Manual goal logs")
    moments: List[MomentDTO] = Field(
        default_factory=list,
        description="Complete timeline; each moment may include an optional nested entry",
    )

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
    source_type: ImportSourceType = Field(..., description="Source type: journiv, markdown, dayone, daylio")
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
    moments_created: int = Field(0, description="Number of moments created")
    media_files_imported: int = Field(0, description="Number of media files imported")
    tags_created: int = Field(0, description="Number of new tags created")
    moods_created: int = Field(0, description="Number of new mood definitions created")
    mood_groups_created: int = Field(0, description="Number of mood groups created")
    mood_group_links_created: int = Field(0, description="Number of mood group links created")
    mood_preferences_imported: int = Field(0, description="Number of mood preferences imported")
    mood_group_preferences_imported: int = Field(0, description="Number of mood group preferences imported")
    activity_groups_created: int = Field(0, description="Number of activity groups created")
    activities_created: int = Field(0, description="Number of activities created")
    goal_categories_created: int = Field(0, description="Number of goal categories created")
    goals_created: int = Field(0, description="Number of goals created")
    goal_logs_created: int = Field(0, description="Number of goal logs created")
    goal_manual_logs_created: int = Field(0, description="Number of manual goal logs created")
    people_created: int = Field(0, description="Number of people created")
    people_reused: int = Field(0, description="Existing people reused by normalized name")
    people_links_created: int = Field(0, description="Moment-person links created")

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


# Resolve forward references for moment/entry nesting.
MomentDTO.model_rebuild()
EntryDTO.model_rebuild()
JournalDTO.model_rebuild()
JournivExportDTO.model_rebuild()


# ============================================================================
# Schema Compatibility Notes
# ============================================================================
"""
DATABASE SCHEMA MAPPING NOTES:

2. MOOD SYSTEM:
   - Mood definitions: Stored in 'mood' table (name, key, icon, color_value, category,
     score, position, is_active, user_id)
   - Mood links stored in moment_mood_activity, primary mood stored on moment
   - Mood ordering stored in mood.position
   - Mood groups stored in mood_group + mood_group_link (ordering in mood_group.position)
   - Placeholders: emoji, color (string) not stored in database

3. ACTIVITIES:
   - Activities stored in 'activity' (name, icon, color, position, group_id)
   - Activity groups stored in 'activity_group' (name, icon, color_value, position)

4. GOALS:
   - Goal definitions stored in 'goal' (type, frequency, target_count, activity_id, category_id)
   - Goal categories stored in 'goal_category'
   - Goal logs stored in 'goal_log' (period-based)
   - Manual overrides stored in 'goal_manual_log'

5. MOMENT LOCATION:
   - Database: location_json, latitude, longitude live on 'moment' table
   - DTO field location_json on MomentDTO maps directly to moment.location_json
   - DTO fields latitude, longitude map directly to moment Float columns

6. MOMENT MEDIA:
   - Stored in 'moment_media' table with full metadata, linked via moment_id
   - Fields: file_path, original_filename, file_size, mime_type, media_type
   - Optional: thumbnail_path, width, height, duration, alt_text, checksum
   - Upload tracking: upload_status, processing_error, file_metadata

7. TAGS:
   - Stored in 'tag' table (user-specific, case-insensitive)
   - Many-to-many with moments via 'moment_tag_link' table
   - Normalized to lowercase in database

8. USER SETTINGS:
   - Stored in 'user_settings' table (one-to-one with user)
   - Fields: theme, time_zone, daily_prompt_enabled, push_notifications,
     reminder_time, writing_goal_daily
   - Placeholders: date_format, time_format, first_day_of_week

9. TIMESTAMPS:
   - All models inherit from BaseModel: id, created_at, updated_at, is_deleted
   - Moment has: logged_date_tz (date), logged_at_utc (datetime), logged_timezone (str)
   - Entry has: content fields only (title, content_delta, word_count, is_draft)

10. ENUM TYPES:
   - MediaType: image, video, audio, unknown
   - UploadStatus: pending, processing, completed, failed
   - MoodCategory: positive, negative, neutral
   - Theme: light, dark, auto
   - JournalColor: 20+ predefined hex colors
   - JobStatus: pending, running, completed, failed, cancelled
   - ImportSourceType: journiv, markdown, dayone
   - ExportType: full, journal

PLACEHOLDER FIELDS (for future implementation):
- MomentMediaDTO: caption (use alt_text instead)
- MoodDefinitionDTO: emoji, color (string) not stored in database
- UserSettingsDTO: date_format, time_format, first_day_of_week

TODO: These placeholders maintain compatibility with import formats from other apps
but are not stored in the database. They should be mapped to existing fields
or skipped during import.
"""
