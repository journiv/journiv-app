"""
User-related models.
"""
import uuid
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from pydantic import field_validator, EmailStr, HttpUrl
from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, Relationship, Index, CheckConstraint, String

from .base import BaseModel, TimestampMixin
from .enums import Theme

if TYPE_CHECKING:
    from .journal import Journal
    from .prompt import Prompt
    from .mood import MoodLog
    from .tag import Tag
    from .analytics import WritingStreak
    from .external_identity import ExternalIdentity
    from .entry import Entry


class User(BaseModel, table=True):
    """
    User model
    """
    __tablename__ = "user"

    email: EmailStr = Field(
        sa_column=Column(String(255), unique=True, nullable=False)
    )
    password: str = Field(..., min_length=8)  # Hashed password
    name: str = Field(..., max_length=100, sa_column=Column(String(100), nullable=False))
    is_active: bool = Field(default=True)
    profile_picture_url: Optional[HttpUrl] = Field(
        default=None,
        sa_column=Column(String(512), nullable=True)
    )
    last_login_at: Optional[datetime] = None

    # Relations
    journals: List["Journal"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    user_prompts: List["Prompt"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    mood_logs: List["MoodLog"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    settings: Optional["UserSettings"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "uselist": False}
    )
    tags: List["Tag"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    writing_streak: Optional["WritingStreak"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "uselist": False}
    )
    external_identities: List["ExternalIdentity"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    entries: List["Entry"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    # Table constraints and indexes
    __table_args__ = (
        # Index for quickly filtering active/inactive users.
        Index('idx_user_active', 'is_active'),
        # Constraints
        CheckConstraint("length(name) > 0", name='check_name_not_empty'),
    )

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if v is None:
            return v
        return str(v).lower().strip()

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Name cannot be empty')
        return v.strip()


class UserSettings(TimestampMixin, table=True):
    """
    User settings and preferences.
    """
    __tablename__ = "user_settings"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            unique=True,
            nullable=False
        )
    )
    daily_prompt_enabled: bool = Field(default=True)
    time_zone: str = Field(default="UTC", max_length=50)
    push_notifications: bool = Field(default=True)
    reminder_time: Optional[str] = Field(None, max_length=5)  # HH:MM format
    writing_goal_daily: int = Field(default=500, ge=1, le=10000)  # Words per day (default: 500)
    theme: str = Field(default="light", max_length=20)  # light, dark, auto

    # Relations
    user: "User" = Relationship(back_populates="settings")

    # Table constraints and indexes
    __table_args__ = (
        # Constraints
        CheckConstraint('writing_goal_daily > 0', name='check_goal_positive'),
        CheckConstraint("theme IN ('light', 'dark', 'auto')", name='check_theme_valid'),
    )

    @field_validator('theme')
    @classmethod
    def validate_theme(cls, v):
        """Validate theme using Theme enum."""
        allowed_themes = {theme.value for theme in Theme}
        if v not in allowed_themes:
            raise ValueError(f'Invalid theme: {v}. Must be one of {sorted(allowed_themes)}')
        return v

    @field_validator('time_zone')
    @classmethod
    def validate_timezone(cls, v):
        """Validate that timezone is a valid IANA timezone identifier."""
        if not v:
            return v
        from app.core.time_utils import validate_timezone
        if not validate_timezone(v):
            import re
            # Allow UTC offsets as a fallback
            if re.fullmatch(r'UTC([+-]\d{1,2})?(:[0-5]\d)?', v):
                return v
            raise ValueError(f'Invalid timezone: "{v}". Must be a valid IANA timezone name (e.g., "America/New_York") or a UTC offset (e.g., "UTC-5").')
        return v

    @field_validator('reminder_time')
    @classmethod
    def validate_reminder_time(cls, v):
        if v and not v.strip():
            return None
        if v:
            import re
            # Validate time format (HH:MM)
            if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', v.strip()):
                raise ValueError('reminder_time must be in HH:MM format')
            return v.strip()
        return v
