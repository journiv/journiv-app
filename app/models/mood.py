"""
Mood-related models.
"""
import uuid
from typing import TYPE_CHECKING, List, Optional

from pydantic import field_validator
from sqlalchemy import BigInteger, Column, ForeignKey
from sqlmodel import CheckConstraint, Field, Index, Relationship

from .base import BaseModel
from .enums import MoodCategory
from .user_mood_preference import (
    UserMoodPreference,  # Ensure mapper registry knows this model.
)

if TYPE_CHECKING:
    from .moment import MomentMoodActivity
    from .mood_group import MoodGroupLink
    from .user import User
    from .user_mood_preference import UserMoodPreference


class Mood(BaseModel, table=True):
    """
    Mood definitions for mood tracking (system and user).
    """
    __tablename__ = "mood"

    name: str = Field(..., min_length=1, max_length=100, index=True)
    key: Optional[str] = Field(default=None, max_length=50)
    icon: Optional[str] = Field(None, max_length=50)
    color_value: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    category: str = Field(..., max_length=50)  # Should be a MoodCategory enum value
    score: int = Field(default=3, ge=1, le=5)
    position: int = Field(default=0, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    user_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )

    # Relations
    moment_activity_links: List["MomentMoodActivity"] = Relationship(
        back_populates="mood"
    )
    user: Optional["User"] = Relationship(back_populates="moods")
    preferences: List["UserMoodPreference"] = Relationship(
        back_populates="mood",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    group_links: List["MoodGroupLink"] = Relationship(
        back_populates="mood",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    # Table constraints and indexes
    __table_args__ = (
        CheckConstraint('length(name) > 0', name='check_mood_name_not_empty'),
        CheckConstraint('score >= 1 AND score <= 5', name='check_mood_score_range'),
        CheckConstraint(
            "category IN ('positive', 'negative', 'neutral')",
            name='check_mood_category'
        ),
        Index('idx_mood_user_position', 'user_id', 'position'),
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        """Validate and normalize mood name."""
        if not v or len(v.strip()) == 0:
            raise ValueError('Mood name cannot be empty')
        return v.strip()

    @field_validator('key')
    @classmethod
    def normalize_key(cls, v):
        if v is None:
            return v
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
