"""
Analytics and tracking models.

This module provides models for tracking user writing analytics including
streaks, entry counts, and word counts.
"""
import uuid
from datetime import date
from typing import TYPE_CHECKING, Optional

from pydantic import field_validator
from sqlalchemy import Column, ForeignKey
from sqlmodel import CheckConstraint, Field, Index, Relationship

from .base import BaseModel

if TYPE_CHECKING:
    from .user import User


class WritingStreak(BaseModel, table=True):
    """
    Writing streak tracking for users.

    Tracks daily writing streaks, total statistics, and analytics.
    All denormalized fields (total_entries, total_words, average_words_per_entry)
    should be recalculated periodically using analytics_service methods.
    """
    __tablename__ = "writing_streak"

    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            unique=True,
            nullable=False
        ),
        description="User this streak record belongs to"
    )
    current_streak: int = Field(
        default=0,
        ge=0,
        description="Current consecutive days with entries"
    )
    longest_streak: int = Field(
        default=0,
        ge=0,
        description="Longest streak ever achieved by user"
    )
    last_entry_date: Optional[date] = Field(
        default=None,
        description="Date of most recent entry"
    )
    streak_start_date: Optional[date] = Field(
        default=None,
        description="Date when current streak started"
    )
    total_entries: int = Field(
        default=0,
        ge=0,
        description="Total number of entries (denormalized, recalculate periodically)"
    )
    total_words: int = Field(
        default=0,
        ge=0,
        description="Total word count across all entries (denormalized, recalculate periodically)"
    )
    average_words_per_entry: float = Field(
        default=0.0,
        ge=0.0,
        description="Average words per entry (denormalized, recalculate periodically)"
    )

    # Relations
    user: "User" = Relationship(back_populates="writing_streak")

    # Table constraints and indexes
    __table_args__ = (
        Index('idx_writing_streak_user_date', 'user_id', 'last_entry_date'),
        # Index for date-based analytics queries
        Index('idx_writing_streak_last_entry', 'last_entry_date'),
        # Index for finding active streaks
        Index('idx_writing_streak_active', 'last_entry_date', 'current_streak'),
        # Constraints
        CheckConstraint('current_streak >= 0', name='check_current_streak_positive'),
        CheckConstraint('longest_streak >= 0', name='check_longest_streak_positive'),
        CheckConstraint('total_entries >= 0', name='check_total_entries_positive'),
        CheckConstraint('total_words >= 0', name='check_total_words_positive'),
        CheckConstraint('average_words_per_entry >= 0.0', name='check_avg_words_positive'),
        CheckConstraint('longest_streak >= current_streak', name='check_longest_gte_current'),
    )

    @field_validator('average_words_per_entry')
    @classmethod
    def validate_average_words(cls, v: float) -> float:
        """
        Validate that average_words_per_entry is non-negative.

        Note: This validator only checks bounds. The actual average is calculated
        in the service layer (analytics_service.py) to ensure consistency.
        """
        if v < 0:
            raise ValueError('average_words_per_entry must be non-negative')
        return v

    @field_validator('longest_streak')
    @classmethod
    def validate_longest_streak(cls, v: int, info) -> int:
        """
        Validate that longest_streak is at least as large as current_streak.

        This is also enforced by a database constraint for data integrity.
        """
        # Note: info.data contains previously validated fields
        current_streak = info.data.get('current_streak', 0)
        if v < current_streak:
            raise ValueError('longest_streak must be >= current_streak')
        return v
