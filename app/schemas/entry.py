"""
Entry schemas.
"""
import uuid
from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, validator

from app.schemas.base import TimestampMixin


class EntryBase(BaseModel):
    """Base entry schema."""
    title: str
    content: str
    entry_date: Optional[date] = None  # Allows backdating/future-dating entries
    location: Optional[str] = None
    weather: Optional[str] = None


class EntryCreate(EntryBase):
    """Entry creation schema."""
    journal_id: uuid.UUID
    prompt_id: Optional[uuid.UUID] = None

    @validator('title')
    def validate_title_not_empty(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Title cannot be empty')
        return v.strip()


class EntryUpdate(BaseModel):
    """Entry update schema."""
    title: Optional[str] = None
    content: Optional[str] = None
    entry_date: Optional[date] = None
    location: Optional[str] = None
    weather: Optional[str] = None
    is_pinned: Optional[bool] = None


class EntryResponse(EntryBase, TimestampMixin):
    """Entry response schema."""
    id: uuid.UUID
    journal_id: uuid.UUID
    prompt_id: Optional[uuid.UUID] = None
    entry_date: date  # Override to make it required in response
    word_count: int
    is_pinned: bool
    created_at: datetime
    updated_at: datetime


class EntryPreviewResponse(TimestampMixin):
    """Entry preview schema for listings (truncated content)."""
    id: uuid.UUID
    title: str
    content: str  # Truncated by endpoint
    journal_id: uuid.UUID
    created_at: datetime


from app.models.enums import MediaType, UploadStatus


class EntryMediaBase(BaseModel):
    """Base entry media schema."""
    media_type: MediaType
    file_path: str
    original_filename: Optional[str] = None
    file_size: int
    mime_type: str
    thumbnail_path: Optional[str] = None
    duration: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    alt_text: Optional[str] = None
    upload_status: UploadStatus = UploadStatus.PENDING
    file_metadata: Optional[str] = None


class EntryMediaCreate(EntryMediaBase):
    """Entry media creation schema."""
    entry_id: uuid.UUID
    checksum: Optional[str] = None


class EntryMediaResponse(EntryMediaBase, TimestampMixin):
    """Entry media response schema."""
    id: uuid.UUID
    entry_id: uuid.UUID
    created_at: datetime
    checksum: Optional[str] = None
    processing_error: Optional[str] = None

    def model_dump(self, **kwargs):
        """Custom serialization to ensure enums are converted to strings."""
        data = super().model_dump(**kwargs)
        # Convert enums to their string values
        if 'media_type' in data and hasattr(data['media_type'], 'value'):
            data['media_type'] = data['media_type'].value
        if 'upload_status' in data and hasattr(data['upload_status'], 'value'):
            data['upload_status'] = data['upload_status'].value
        return data
