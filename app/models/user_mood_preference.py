"""
User mood preference model for per-user visibility controls.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, Index, Relationship

from .base import BaseModel

if TYPE_CHECKING:
    from .mood import Mood
    from .user import User


class UserMoodPreference(BaseModel, table=True):
    """
    Per-user preferences for moods (e.g., hiding system moods).
    """
    __tablename__ = "user_mood_preference"

    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    mood_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("mood.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    sort_order: int = Field(default=0, nullable=False)
    is_hidden: bool = Field(default=False, nullable=False)

    user: Optional["User"] = Relationship(back_populates="mood_preferences")
    mood: Optional["Mood"] = Relationship(back_populates="preferences")

    __table_args__ = (
        Index(
            "uq_user_mood_preference_user_mood",
            "user_id",
            "mood_id",
            unique=True,
        ),
        Index(
            "idx_user_mood_preference_user_sort_order",
            "user_id",
            "sort_order",
        ),
    )
