"""
Entry-related models.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional, TYPE_CHECKING

from pydantic import field_validator
from sqlalchemy import Column, ForeignKey, Enum as SAEnum, UniqueConstraint, String, DateTime
from sqlmodel import Field, Relationship, Index, CheckConstraint

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


class Entry(BaseModel, table=True):
    """
    Journal entry model
    """
    __tablename__ = "entry"
    title: Optional[str] = Field(None, max_length=300)
    content: str = Field(..., min_length=1, max_length=100000)  # 100K character limit
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
    location: Optional[str] = Field(None, max_length=200)
    weather: Optional[str] = Field(None, max_length=100)
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

        # Constraints
        CheckConstraint('length(content) > 0', name='check_content_not_empty'),
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
        if not v or len(v.strip()) == 0:
            raise ValueError('Content cannot be empty')
        return v.strip()

    @field_validator('location')
    @classmethod
    def validate_location(cls, v):
        if v and len(v.strip()) == 0:
            return None
        return v.strip() if v else v


class EntryMedia(BaseModel, table=True):
    """
    Media files associated with journal entries.
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
    file_path: str = Field(..., max_length=500)
    original_filename: Optional[str] = Field(None, max_length=255)
    file_size: int = Field(..., gt=0)
    mime_type: str = Field(..., max_length=100)
    thumbnail_path: Optional[str] = Field(None, max_length=500)
    duration: Optional[int] = Field(None, ge=0)  # in seconds for video/audio
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

    # Relations
    entry: "Entry" = Relationship(back_populates="media")

    # Table constraints and indexes
    __table_args__ = (
        # Performance indexes for critical queries
        Index('idx_entry_media_entry_id', 'entry_id'),
        Index('idx_entry_media_type', 'media_type'),
        Index('idx_entry_media_status', 'upload_status'),
        Index('idx_entry_media_checksum', 'checksum'),
        UniqueConstraint('entry_id', 'checksum', name='uq_entry_media_entry_checksum'),
        # Constraints
        CheckConstraint('file_size > 0', name='check_file_size_positive'),
        CheckConstraint('duration IS NULL OR duration >= 0', name='check_duration_non_negative'),
        CheckConstraint('width IS NULL OR width > 0', name='check_width_positive'),
        CheckConstraint('height IS NULL OR height > 0', name='check_height_positive'),
    )

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
