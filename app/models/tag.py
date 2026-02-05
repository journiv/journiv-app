"""
Tag-related models.
"""
import uuid
from typing import TYPE_CHECKING, List

from pydantic import field_validator
from sqlalchemy import Column, ForeignKey
from sqlmodel import CheckConstraint, Field, Index, Relationship, UniqueConstraint

from .base import BaseModel

if TYPE_CHECKING:
    from .entry import Entry
    from .user import User

# Import EntryTagLink from separate file to avoid circular imports
from .entry_tag_link import EntryTagLink


class Tag(BaseModel, table=True):
    """
    Tag model for categorizing journal entries.
    """
    __tablename__ = "tag"

    name: str = Field(..., min_length=1, max_length=100, index=True)
    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False
        )
    )  # Tags are user-specific
    usage_count: int = Field(default=0, ge=0)

    # Relations
    user: "User" = Relationship(back_populates="tags")
    entries: List["Entry"] = Relationship(
        back_populates="tags",
        link_model=EntryTagLink
    )

    # Table constraints and indexes
    __table_args__ = (
        Index('idx_tags_usage_count', 'user_id', 'usage_count'),
        # Constraints
        # Ensures a user cannot have two tags with the same name.
        UniqueConstraint('user_id', 'name', name='uq_tag_user_name'),
        CheckConstraint('length(name) > 0', name='check_tag_name_not_empty'),
        CheckConstraint('usage_count >= 0', name='check_usage_count_non_negative'),
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Tag name cannot be empty')
        return v.strip().lower()
