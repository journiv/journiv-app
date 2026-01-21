"""
Entry-related models.
"""
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional, TYPE_CHECKING, Dict, Any

from pydantic import field_validator, model_validator
from sqlalchemy import Column, ForeignKey, Enum as SAEnum, UniqueConstraint, String, DateTime, Float, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, Index, CheckConstraint, Column as SQLModelColumn, JSON

from app.core.time_utils import utc_now
from .base import BaseModel
from .enums import MediaType, UploadStatus

if TYPE_CHECKING:
    from .journal import Journal
    from .prompt import Prompt
    from .mood import MoodLog
    from .tag import Tag
    from .user import User

# Import EntryTagLink from separate file to avoid circular imports
from .entry_tag_link import EntryTagLink


def JSONType():
    return JSONB().with_variant(JSON, "sqlite")


class Entry(BaseModel, table=True):
    """
    Journal entry model
    """
    __tablename__ = "entry"

    title: Optional[str] = Field(None, max_length=300)
    content: Optional[str] = Field(None, max_length=100000)  # 100K character limit
    journal_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("journal.id", ondelete="CASCADE"),
            nullable=False
        )
    )
    prompt_id: Optional[uuid.UUID] = Field(
        sa_column=Column(
            ForeignKey("prompt.id", ondelete="SET NULL"),
            nullable=True
        )
    )
    entry_date: date = Field(index=True, description="User's local date for this entry (calculated from stored timezone)")  # Date of the journal entry (can be backdated/future-dated)
    entry_datetime_utc: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
        description="UTC timestamp representing when the entry occurred"
    )
    entry_timezone: str = Field(
        default="UTC",
        sa_column=Column(String(100), nullable=False, default="UTC"),
        description="IANA timezone for the entry's local context"
    )
    word_count: int = Field(default=0, ge=0, le=50000)  # Reasonable word count limit
    is_pinned: bool = Field(default=False)
    media_count: int = Field(
        default=0,
        sa_column=Column(Integer, server_default="0", nullable=False, index=True),
        description="Number of media items associated with this entry"
    )

    # Structured location fields
    location_json: Optional[dict] = Field(
        default=None,
        sa_column=SQLModelColumn(JSONType()),
        description="Structured location data: {name, street, locality, admin_area, country, latitude, longitude, timezone}"
    )
    latitude: Optional[float] = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
        description="GPS latitude"
    )
    longitude: Optional[float] = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
        description="GPS longitude"
    )

    # Structured weather fields (new)
    weather_json: Optional[dict] = Field(
        default=None,
        sa_column=SQLModelColumn(JSONType()),
        description="Structured weather data: {temp_c, condition, code, service}"
    )
    weather_summary: Optional[str] = Field(
        None,
        description="Human-readable weather summary"
    )
    import_metadata: Optional[dict] = Field(
        default=None,
        sa_column=SQLModelColumn(JSONType()),
        description="Import metadata for preserving source details"
    )

    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )

    # Relations
    journal: "Journal" = Relationship(back_populates="entries")
    prompt: Optional["Prompt"] = Relationship(back_populates="entries")
    media: List["EntryMedia"] = Relationship(
        back_populates="entry",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    mood_log: Optional["MoodLog"] = Relationship(
        back_populates="entry",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "uselist": False}
    )
    tags: List["Tag"] = Relationship(
        back_populates="entries",
        link_model=EntryTagLink
    )
    user: "User" = Relationship(back_populates="entries")

    # Table constraints and indexes
    __table_args__ = (
        Index('idx_entries_journal_date', 'journal_id', 'entry_date'),
        Index('idx_entries_created_at', 'created_at'),
        Index('idx_entries_prompt_id', 'prompt_id'),
        Index('idx_entry_user_datetime', 'user_id', 'entry_datetime_utc'),
        Index('idx_entry_latitude_longitude', 'latitude', 'longitude'),

        # Constraints
        CheckConstraint('word_count >= 0', name='check_word_count_positive'),
    )

    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if v and len(v.strip()) == 0:
            return None
        return v.strip() if v else v

    @field_validator('content')
    @classmethod
    def validate_content(cls, v):
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned if cleaned else None

    @field_validator('latitude')
    @classmethod
    def validate_latitude(cls, v):
        if v is not None and not (-90 <= v <= 90):
            raise ValueError(f'Latitude must be between -90 and 90, got {v}')
        return v

    @field_validator('longitude')
    @classmethod
    def validate_longitude(cls, v):
        if v is not None and not (-180 <= v <= 180):
            raise ValueError(f'Longitude must be between -180 and 180, got {v}')
        return v

    @model_validator(mode='after')
    def validate_location_consistency(self):
        if self.location_json and isinstance(self.location_json, dict):
            loc_lat = self.location_json.get('latitude')
            loc_lon = self.location_json.get('longitude')

            if loc_lat is not None:
                if not (-90 <= loc_lat <= 90):
                    raise ValueError(f'Latitude in location_json must be between -90 and 90, got {loc_lat}')
                if self.latitude is not None and abs(self.latitude - loc_lat) > 0.0001:
                    raise ValueError(f'latitude field ({self.latitude}) does not match location_json.latitude ({loc_lat})')

            if loc_lon is not None:
                if not (-180 <= loc_lon <= 180):
                    raise ValueError(f'Longitude in location_json must be between -180 and 180, got {loc_lon}')
                if self.longitude is not None and abs(self.longitude - loc_lon) > 0.0001:
                    raise ValueError(f'longitude field ({self.longitude}) does not match location_json.longitude ({loc_lon})')

        return self


class EntryMedia(BaseModel, table=True):
    """
    Media files associated with journal entries.

    Supports both local files (stored on Journiv server) and external links
    (referenced from external providers like Immich).
    """
    __tablename__ = "entry_media"

    entry_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("entry.id", ondelete="CASCADE"),
            nullable=False
        )
    )
    media_type: MediaType = Field(
        sa_column=Column(
            SAEnum(MediaType, name="media_type_enum"),
            nullable=False
        )
    )

    # Local file fields (nullable for external media)
    file_path: Optional[str] = Field(None, max_length=500)
    file_size: Optional[int] = Field(None, gt=0)
    thumbnail_path: Optional[str] = Field(None, max_length=500)

    # Common fields
    original_filename: Optional[str] = Field(None, max_length=255)
    mime_type: str = Field(..., max_length=100)
    duration: Optional[float] = Field(None, ge=0)  # in seconds for video/audio
    width: Optional[int] = Field(None, ge=0)
    height: Optional[int] = Field(None, ge=0)
    alt_text: Optional[str] = Field(None, max_length=500)  # Accessibility
    upload_status: UploadStatus = Field(
        default=UploadStatus.PENDING,
        sa_column=Column(
            SAEnum(UploadStatus, name="upload_status_enum"),
            nullable=False,
            default=UploadStatus.PENDING
        )
    )
    file_metadata: Optional[str] = Field(None, max_length=2000)  # JSON metadata
    processing_error: Optional[str] = Field(None, max_length=1000)  # Error message if processing failed
    checksum: Optional[str] = Field(
        default=None,
        sa_column=Column(String(64), nullable=True)
    )

    # External provider fields (for link-only media)
    external_provider: Optional[str] = Field(
        default=None,
        sa_column=Column(String(50), nullable=True, index=True),
        description="External provider name (e.g., 'immich', 'jellyfin')"
    )
    external_asset_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255), nullable=True, index=True),
        description="Asset ID in the external provider's system"
    )
    external_url: Optional[str] = Field(
        default=None,
        sa_column=Column(String(512), nullable=True),
        description="Full URL to the asset in the external provider"
    )
    external_created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Creation date from external provider (e.g., photo taken_at)"
    )
    external_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=SQLModelColumn(JSONType(), nullable=True),
        description="Additional metadata from external provider (JSON)"
    )

    # Relations
    entry: "Entry" = Relationship(back_populates="media")

    # Table constraints and indexes
    __table_args__ = (
        # Performance indexes for critical queries
        Index('idx_entry_media_entry_id', 'entry_id'),
        Index('idx_entry_media_type', 'media_type'),
        Index('idx_entry_media_status', 'upload_status'),
        Index('idx_entry_media_checksum', 'checksum'),
        Index('idx_entry_media_external_provider', 'external_provider', 'external_asset_id'),
        UniqueConstraint('entry_id', 'checksum', name='uq_entry_media_entry_checksum'),
        # Constraints
        # Either local file (file_path + file_size) OR external link (external_provider)
        CheckConstraint(
            '(file_path IS NOT NULL AND file_size > 0) OR (external_provider IS NOT NULL)',
            name='check_media_source'
        ),
        CheckConstraint('file_size IS NULL OR file_size > 0', name='check_file_size_positive'),
        CheckConstraint('duration IS NULL OR duration >= 0', name='check_duration_non_negative'),
        CheckConstraint('width IS NULL OR width > 0', name='check_width_positive'),
        CheckConstraint('height IS NULL OR height > 0', name='check_height_positive'),
    )

    @property
    def is_external(self) -> bool:
        """Check if this media is linked from an external provider."""
        return self.external_provider is not None

    @field_validator('media_type')
    @classmethod
    def validate_media_type(cls, v):
        if isinstance(v, MediaType):
            return v
        try:
            return MediaType(v)
        except ValueError as exc:
            allowed_types = sorted(media_type.value for media_type in MediaType)
            raise ValueError(f'Invalid media_type: {v}. Must be one of {allowed_types}') from exc

    @field_validator('upload_status')
    @classmethod
    def validate_upload_status(cls, v):
        if isinstance(v, UploadStatus):
            return v
        try:
            return UploadStatus(v)
        except ValueError as exc:
            allowed_statuses = sorted(status.value for status in UploadStatus)
            raise ValueError(f'Invalid upload_status: {v}. Must be one of {allowed_statuses}') from exc

    @field_validator('external_created_at')
    @classmethod
    def validate_external_created_at(cls, v):
        if v is None:
            return v
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v
