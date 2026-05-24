"""
Moment-related models.
"""
import uuid
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import field_validator, model_validator
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import JSON, CheckConstraint, Field, Index, Relationship
from sqlmodel import Column as SQLModelColumn

from app.core.time_utils import ensure_utc, local_date_for_user, utc_now

from .base import BaseModel
from .enums import MediaType, UploadStatus

if TYPE_CHECKING:
    from .activity import Activity
    from .entry import Entry
    from .goal import GoalLog
    from .mood import Mood
    from .person import Person
    from .prompt import Prompt
    from .tag import Tag
    from .user import User

from .moment_person_link import MomentPersonLink
from .moment_tag_link import MomentTagLink


def JSONType():
    return JSONB().with_variant(JSON, "sqlite")


class Moment(BaseModel, table=True):
    """
    Primary life anchor for the timeline.

    Owns all contextual data: time, location, weather, moods, activities,
    tags, and media. An Entry is an optional narrative extension.
    """
    __tablename__ = "moment"

    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )
    primary_mood_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("mood.id", ondelete="SET NULL"),
            nullable=True
        )
    )
    prompt_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("prompt.id", ondelete="SET NULL"),
            nullable=True
        )
    )
    logged_at_utc: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
        description="UTC timestamp when the moment occurred"
    )
    logged_date_tz: date = Field(
        default=None,
        sa_column=Column(Date, nullable=False, index=True),
        description="User's local date for this moment"
    )
    logged_timezone: str = Field(
        default="UTC",
        sa_column=Column(String(100), nullable=False, default="UTC"),
        description="IANA timezone for the moment context"
    )
    note: Optional[str] = Field(None, max_length=500)

    # Structured location fields
    location_json: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=SQLModelColumn(JSONType(), nullable=True),
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

    # Structured weather fields
    weather_json: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=SQLModelColumn(JSONType(), nullable=True),
        description="Structured weather data: {temp_c, condition, code, service}"
    )
    weather_summary: Optional[str] = Field(
        None,
        description="Human-readable weather summary"
    )

    is_pinned: bool = Field(
        default=False,
        sa_column=Column(Boolean, server_default="false", nullable=False),
    )
    media_count: int = Field(
        default=0,
        sa_column=Column(Integer, server_default="0", nullable=False, index=True),
        description="Number of media items associated with this moment"
    )

    # Relations
    user: "User" = Relationship(back_populates="moments")
    entry: Optional["Entry"] = Relationship(
        back_populates="moment",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"}
    )
    prompt: Optional["Prompt"] = Relationship(back_populates="moments")
    tags: List["Tag"] = Relationship(back_populates="moments", link_model=MomentTagLink)
    people: List["Person"] = Relationship(back_populates="moments", link_model=MomentPersonLink)
    mood_activity_links: List["MomentMoodActivity"] = Relationship(
        back_populates="moment",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    goal_logs: List["GoalLog"] = Relationship(
        back_populates="moment",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    media: List["MomentMedia"] = Relationship(
        back_populates="moment",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    # Table constraints and indexes
    __table_args__ = (
        Index('idx_moment_user_logged_at_utc', 'user_id', 'logged_at_utc', 'id'),
        Index('idx_moment_user_logged_date_tz', 'user_id', 'logged_date_tz'),
        Index('idx_moment_latitude_longitude', 'latitude', 'longitude'),
        Index('idx_moment_prompt_id', 'prompt_id'),
        Index('idx_moment_note', 'note'),
        CheckConstraint('media_count >= 0', name='check_moment_media_count_non_negative'),
    )

    @model_validator(mode="after")
    def _ensure_logged_date(self) -> "Moment":
        if self.logged_date_tz is None:
            tz_name = (self.logged_timezone or "UTC").strip() or "UTC"
            reference_dt = (
                ensure_utc(self.logged_at_utc) if self.logged_at_utc is not None else utc_now()
            )
            # Explicitly local_date_for_user uses the timezone to derive the date
            self.logged_date_tz = local_date_for_user(reference_dt, tz_name)
        return self

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

            if loc_lat is not None and isinstance(loc_lat, (int, float)):
                if not (-90 <= loc_lat <= 90):
                    raise ValueError(f'Latitude in location_json must be between -90 and 90, got {loc_lat}')
                if self.latitude is not None and abs(float(self.latitude) - float(loc_lat)) > 0.0001:
                    raise ValueError(f'latitude field ({self.latitude}) does not match location_json.latitude ({loc_lat})')

            if loc_lon is not None and isinstance(loc_lon, (int, float)):
                if not (-180 <= loc_lon <= 180):
                    raise ValueError(f'Longitude in location_json must be between -180 and 180, got {loc_lon}')
                if self.longitude is not None and abs(float(self.longitude) - float(loc_lon)) > 0.0001:
                    raise ValueError(f'longitude field ({self.longitude}) does not match location_json.longitude ({loc_lon})')

        return self


class MomentMedia(BaseModel, table=True):
    """
    Media files associated with moments.

    Supports both local files (stored on Journiv server) and external links
    (referenced from external providers like Immich).
    """
    __tablename__ = "moment_media"

    moment_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("moment.id", ondelete="CASCADE"),
            nullable=False,
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
    display_path: Optional[str] = Field(None, max_length=500)  # Web-compatible version (e.g., WebP for HEIC)

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
    moment: "Moment" = Relationship(back_populates="media")

    # Table constraints and indexes
    __table_args__ = (
        Index('idx_moment_media_moment_id', 'moment_id'),
        Index('idx_moment_media_type', 'media_type'),
        Index('idx_moment_media_status', 'upload_status'),
        Index('idx_moment_media_checksum', 'checksum'),
        Index('idx_moment_media_external_provider', 'external_provider', 'external_asset_id'),
        UniqueConstraint('moment_id', 'checksum', name='uq_moment_media_moment_checksum'),
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


def _derive_logged_date_tz(moment: Moment) -> date:
    """Compute local date from UTC timestamp and timezone, with safe fallbacks."""
    tz_name = (moment.logged_timezone or "UTC").strip() or "UTC"
    reference_dt = ensure_utc(moment.logged_at_utc) if moment.logged_at_utc is not None else utc_now()
    return local_date_for_user(reference_dt, tz_name)


@event.listens_for(Moment, "before_insert")
def _moment_before_insert(mapper, connection, target: Moment) -> None:
    # Guarantee persisted values satisfy NOT NULL while keeping timezone-aware derivation.
    target.logged_at_utc = ensure_utc(target.logged_at_utc) if target.logged_at_utc is not None else utc_now()
    if not target.logged_timezone:
        target.logged_timezone = "UTC"
    if target.logged_date_tz is None:
        target.logged_date_tz = _derive_logged_date_tz(target)


@event.listens_for(Moment, "before_update")
def _moment_before_update(mapper, connection, target: Moment) -> None:
    target.logged_at_utc = ensure_utc(target.logged_at_utc) if target.logged_at_utc is not None else utc_now()
    if not target.logged_timezone:
        target.logged_timezone = "UTC"
    if target.logged_date_tz is None:
        target.logged_date_tz = _derive_logged_date_tz(target)


class MomentMoodActivity(BaseModel, table=True):
    """
    Link table for moods and activities within a moment.
    """
    __tablename__ = "moment_mood_activity"

    moment_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("moment.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )
    mood_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("mood.id", ondelete="CASCADE"),
            nullable=True,
            index=True
        )
    )
    activity_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("activity.id", ondelete="CASCADE"),
            nullable=True,
            index=True
        )
    )

    # Relations
    moment: "Moment" = Relationship(back_populates="mood_activity_links")
    mood: Optional["Mood"] = Relationship(back_populates="moment_activity_links")
    activity: Optional["Activity"] = Relationship(back_populates="moment_activity_links")

    # Table constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "(mood_id IS NOT NULL OR activity_id IS NOT NULL)",
            name="check_moment_mood_activity_not_empty"
        ),
    )
