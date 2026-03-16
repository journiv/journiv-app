"""
Activity-related models for Daylio-style activity tracking.
"""
import uuid
from typing import TYPE_CHECKING, List, Optional

from pydantic import field_validator
from sqlalchemy import Column, ForeignKey
from sqlmodel import CheckConstraint, Field, Index, Relationship, UniqueConstraint

from .base import BaseModel

if TYPE_CHECKING:
    from .activity_group import ActivityGroup
    from .goal import Goal
    from .moment import MomentMoodActivity
    from .user import User


class Activity(BaseModel, table=True):
    """
    User-defined activity definitions (e.g., "Exercise", "Read", "Meditate").
    Similar to how tags work, but specifically for activity tracking.
    """
    __tablename__ = "activity"

    name: str = Field(..., min_length=1, max_length=100, index=True)
    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )
    icon: Optional[str] = Field(None, max_length=50)  # e.g., "🏃" or "mdi-run"
    color: Optional[str] = Field(None, max_length=50)  # hex color or theme token
    position: int = Field(default=0, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    stable_key: Optional[str] = Field(default=None, max_length=100, index=True)
    group_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("activity_group.id", ondelete="SET NULL"),
            nullable=True,
            index=True
        )
    )

    # Relations
    user: "User" = Relationship(back_populates="activities")
    moment_activity_links: List["MomentMoodActivity"] = Relationship(
        back_populates="activity",
        sa_relationship_kwargs={"passive_deletes": True},
    )
    group: Optional["ActivityGroup"] = Relationship(back_populates="activities")
    goals: List["Goal"] = Relationship(back_populates="activity")

    # Table constraints and indexes
    __table_args__ = (
        Index('idx_activity_user_name', 'user_id', 'name'),
        Index('idx_activity_user_active', 'user_id', 'is_active'),
        Index('idx_activity_user_group_position', 'user_id', 'group_id', 'position'),
        CheckConstraint('length(name) > 0', name='check_activity_name_not_empty'),
        UniqueConstraint('user_id', 'stable_key', name='uq_activity_user_stable_key'),
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        """Validate and normalize activity name."""
        if not v or len(v.strip()) == 0:
            raise ValueError('Activity name cannot be empty')
        return v.strip()
