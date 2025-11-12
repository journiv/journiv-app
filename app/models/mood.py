"""
Mood-related models.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional, TYPE_CHECKING

from pydantic import field_validator
from sqlalchemy import Column, ForeignKey, Date, DateTime, String
from sqlmodel import Field, Relationship, Index, CheckConstraint

from app.core.time_utils import utc_now
from .base import BaseModel
from .enums import MoodCategory

if TYPE_CHECKING:
    from .user import User
    from .entry import Entry


class Mood(BaseModel, table=True):
    """
    System mood definitions for mood tracking.
    """
    __tablename__ = "mood"

    name: str = Field(..., unique=True, min_length=1, max_length=100)
    icon: Optional[str] = Field(None, max_length=50)
    category: str = Field(..., max_length=50)  # Should be a MoodCategory enum value

    # Relations
    mood_logs: List["MoodLog"] = Relationship(back_populates="mood")

    # Table constraints and indexes
    __table_args__ = (
        CheckConstraint('length(name) > 0', name='check_mood_name_not_empty'),
        CheckConstraint(
            "category IN ('positive', 'negative', 'neutral')",
            name='check_mood_category'
        ),
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        """Validate and normalize mood name to lowercase."""
        if not v or len(v.strip()) == 0:
            raise ValueError('Mood name cannot be empty')
        # Normalize to lowercase for consistency
        return v.strip().lower()

    @field_validator('category')
    @classmethod
    def validate_category(cls, v):
        """Validate category against MoodCategory enum."""
        allowed_categories = {cat.value for cat in MoodCategory}
        if v not in allowed_categories:
            raise ValueError(
                f'Invalid category: {v}. Must be one of {sorted(allowed_categories)}'
            )
        return v


class MoodLog(BaseModel, table=True):
    """
    Simple mood logging for tracking user moods.
    """
    __tablename__ = "mood_log"

    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False
        )
    )
    entry_id: Optional[uuid.UUID] = Field(
        sa_column=Column(
            ForeignKey("entry.id", ondelete="CASCADE"),
            nullable=True,
            unique=True  # Enforce one-to-one relationship at DB level
        )
    )
    mood_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("mood.id", ondelete="CASCADE"),
            nullable=False
        )
    )
    note: Optional[str] = Field(None, max_length=500)
    logged_date: date = Field(
        sa_column=Column(Date, nullable=False, index=True),
        description="The date this mood represents (from entry or when logged)"
    )
    logged_datetime_utc: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
        description="UTC timestamp when the mood was logged"
    )
    logged_timezone: str = Field(
        default="UTC",
        sa_column=Column(String(100), nullable=False, default="UTC"),
        description="IANA timezone for the mood log context"
    )

    # Relations
    user: "User" = Relationship(back_populates="mood_logs")
    entry: Optional["Entry"] = Relationship(back_populates="mood_log")
    mood: "Mood" = Relationship(back_populates="mood_logs")

    # Table constraints and indexes
    __table_args__ = (
        # For fetching a user's mood history (e.g., a timeline)
        Index('idx_mood_logs_user_id_logged_date', 'user_id', 'logged_date'),
        Index('idx_mood_logs_user_datetime', 'user_id', 'logged_datetime_utc'),
        # For analytics across all users (e.g., "moods logged on a date")
        Index('idx_mood_logs_logged_date', 'logged_date'),
        # For analytics on specific moods (e.g., "how many 'happy' logs exist")
        Index('idx_mood_logs_mood_id', 'mood_id'),
        Index('idx_mood_logs_user_mood', 'user_id', 'mood_id'),  # For "how often does user feel this mood" queries
    )

    @field_validator('note')
    @classmethod
    def validate_note(cls, v):
        if v and len(v.strip()) == 0:
            return None
        return v.strip() if v else v
