"""
Entry schemas.
"""
import uuid
from datetime import datetime, date
from typing import Optional, Dict, Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.base import TimestampMixin


class EntryBase(BaseModel):
    """Base entry schema."""
    title: Optional[str] = None
    content: Optional[str] = None
    entry_date: Optional[date] = None  # Allows backdating/future-dating entries
    entry_datetime_utc: Optional[datetime] = None
    entry_timezone: Optional[str] = None

    # Structured location fields
    location_json: Optional[Dict[str, Any]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Structured weather fields (Day One import)
    weather_json: Optional[Dict[str, Any]] = None
    weather_summary: Optional[str] = None


class EntryCreate(EntryBase):
    """Entry creation schema."""
    journal_id: uuid.UUID
    prompt_id: Optional[uuid.UUID] = None


class EntryUpdate(BaseModel):
    """Entry update schema."""
    title: Optional[str] = None
    content: Optional[str] = None
    entry_date: Optional[date] = None
    entry_datetime_utc: Optional[datetime] = None
    entry_timezone: Optional[str] = None

    # Structured location fields
    location_json: Optional[Dict[str, Any]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Structured weather fields
    weather_json: Optional[Dict[str, Any]] = None
    weather_summary: Optional[str] = None

    is_pinned: Optional[bool] = None
    journal_id: Optional[uuid.UUID] = None


class EntryResponse(EntryBase, TimestampMixin):
    """Entry response schema."""
    id: uuid.UUID
    journal_id: uuid.UUID
    prompt_id: Optional[uuid.UUID] = None
    entry_date: date  # Override to make it required in response
    entry_datetime_utc: datetime
    entry_timezone: str
    word_count: int
    is_pinned: bool
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    media_count: int = 0


class EntryPreviewResponse(TimestampMixin):
    """Entry preview schema for listings (truncated content)."""
    id: uuid.UUID
    title: Optional[str] = None
    content: Optional[str] = None  # Truncated by endpoint
    journal_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    entry_date: date
    entry_datetime_utc: datetime
    entry_timezone: str
    media_count: int = 0


from app.models.enums import MediaType, UploadStatus


class EntryMediaBase(BaseModel):
    """Base entry media schema."""
    media_type: MediaType
    file_path: Optional[str] = None
    original_filename: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: str
    thumbnail_path: Optional[str] = None
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    alt_text: Optional[str] = None
    upload_status: UploadStatus = UploadStatus.PENDING
    file_metadata: Optional[str] = None

class EntryMediaExternalFields(BaseModel):
    """External provider fields (internal use)."""
    external_provider: Optional[str] = None
    external_asset_id: Optional[str] = None
    external_url: Optional[str] = None
    external_created_at: Optional[datetime] = None
    external_metadata: Optional[Dict[str, Any]] = None


class EntryMediaCreate(EntryMediaBase, EntryMediaExternalFields):
    """Entry media creation schema."""
    entry_id: uuid.UUID
    checksum: Optional[str] = None


class EntryMediaCreateRequest(EntryMediaBase):
    """Entry media creation schema for public API."""
    entry_id: uuid.UUID
    checksum: Optional[str] = None


class MediaOrigin(BaseModel):
    """Optional origin metadata for external media."""
    source: Literal["internal", "immich"]
    external_id: Optional[str] = None
    external_url: Optional[str] = None


class EntryMediaExternalResponseFields(BaseModel):
    """External provider fields (excluded from response serialization)."""
    external_provider: Optional[str] = Field(default=None, exclude=True)
    external_asset_id: Optional[str] = Field(default=None, exclude=True)
    external_url: Optional[str] = Field(default=None, exclude=True)
    external_created_at: Optional[datetime] = Field(default=None, exclude=True)
    external_metadata: Optional[Dict[str, Any]] = Field(default=None, exclude=True)


class EntryMediaResponse(EntryMediaBase, EntryMediaExternalResponseFields, TimestampMixin):
    """Entry media response schema."""
    file_path: Optional[str] = Field(default=None, exclude=True)
    thumbnail_path: Optional[str] = Field(default=None, exclude=True)
    id: uuid.UUID
    entry_id: uuid.UUID
    created_at: datetime
    checksum: Optional[str] = None
    processing_error: Optional[str] = None
    signed_url: Optional[str] = None
    signed_thumbnail_url: Optional[str] = None
    signed_url_expires_at: Optional[int] = None
    signed_thumbnail_expires_at: Optional[int] = None
    origin: Optional[MediaOrigin] = None

    @model_validator(mode='after')
    def validate_source_presence(self):
        """Ensure media has either local or external source."""
        if self.upload_status in {UploadStatus.PENDING, UploadStatus.FAILED}:
            return self
        # Check local source
        has_local = self.file_path is not None and self.file_size is not None

        # Check external source
        has_external = self.external_provider is not None and (
            self.external_asset_id is not None or self.external_url is not None
        )

        if not (has_local or has_external):
            raise ValueError("Media must have either a local file or an external source")

        return self
