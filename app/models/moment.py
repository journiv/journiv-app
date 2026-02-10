"""
Moment-related models.
"""
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import model_validator
from sqlalchemy import Column, Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import JSON, CheckConstraint, Field, Index, Relationship
from sqlmodel import Column as SQLModelColumn

from app.core.time_utils import ensure_utc, local_date_for_user, utc_now

from .base import BaseModel

if TYPE_CHECKING:
    from .activity import Activity
    from .entry import Entry
    from .goal import GoalLog
    from .mood import Mood
    from .user import User


def JSONType():
    return JSONB().with_variant(JSON, "sqlite")


class Moment(BaseModel, table=True):
    """
    Unified timeline anchor for moods, activities, and entries.
    """
    __tablename__ = "moment"

    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )
    entry_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("entry.id", ondelete="SET NULL"),
            nullable=True,
            unique=True
        )
    )
    primary_mood_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("mood.id", ondelete="SET NULL"),
            nullable=True
        )
    )
    logged_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
        description="UTC timestamp when the moment occurred"
    )
    logged_date: Optional[date] = Field(
        default=None,
        sa_column=Column(Date, nullable=True, index=True),
        description="User's local date for this moment"
    )
    logged_timezone: str = Field(
        default="UTC",
        sa_column=Column(String(100), nullable=False, default="UTC"),
        description="IANA timezone for the moment context"
    )
    note: Optional[str] = Field(None, max_length=500)
    location_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=SQLModelColumn(JSONType(), nullable=True),
        description="Structured location data"
    )
    weather_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=SQLModelColumn(JSONType(), nullable=True),
        description="Structured weather data"
    )

    # Relations
    user: "User" = Relationship(back_populates="moments")
    entry: Optional["Entry"] = Relationship(back_populates="moment")
    mood_activity_links: List["MomentMoodActivity"] = Relationship(
        back_populates="moment",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    goal_logs: List["GoalLog"] = Relationship(
        back_populates="moment",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    # Table constraints and indexes
    __table_args__ = (
        Index('idx_moment_user_logged_at', 'user_id', 'logged_at', 'id'),
        Index('idx_moment_user_logged_date', 'user_id', 'logged_date'),
    )

    @model_validator(mode="after")
    def _ensure_logged_date(self) -> "Moment":
        if self.logged_date is None and self.logged_at is not None:
            tz_name = (self.logged_timezone or "UTC").strip() or "UTC"
            self.logged_date = local_date_for_user(ensure_utc(self.logged_at), tz_name)
        return self


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
