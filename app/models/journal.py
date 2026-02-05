"""
Journal-related models.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from pydantic import field_validator
from sqlalchemy import Column, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import JSON, CheckConstraint, Field, Index, Relationship
from sqlmodel import Column as SQLModelColumn

from .base import BaseModel
from .enums import JournalColor

if TYPE_CHECKING:
    from .entry import Entry
    from .user import User


JSONType = JSONB().with_variant(JSON, "sqlite")


class Journal(BaseModel, table=True):
    """
    Journal model with enhanced features for better organization.
    """
    __tablename__ = "journal"

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    color: Optional[JournalColor] = Field(
        default=None,
        sa_column=Column(
            SAEnum(JournalColor, name="journal_color_enum"),
            nullable=True
        )
    )
    icon: Optional[str] = Field(None, max_length=50)
    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False
        )
    )
    is_favorite: bool = Field(default=False)
    is_archived: bool = Field(default=False)
    entry_count: int = Field(default=0, ge=0)  # Denormalized for performance
    total_words: int = Field(default=0, ge=0)  # Denormalized for performance
    last_entry_at: Optional[datetime] = None
    import_metadata: Optional[dict] = Field(
        default=None,
        sa_column=SQLModelColumn(
            JSONType
        ),
        description="Import metadata for preserving source details"
    )

    # Relations
    user: "User" = Relationship(back_populates="journals")
    entries: List["Entry"] = Relationship(
        back_populates="journal",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    # Table constraints and indexes
    __table_args__ = (
        # Composite indexes for common query patterns.
        Index('idx_journal_user_created', 'user_id', 'created_at'),
        Index('idx_journal_user_favorite', 'user_id', 'is_favorite'),
        Index('idx_journal_user_archived', 'user_id', 'is_archived'),
        # Constraints
        CheckConstraint('length(title) > 0', name='check_title_not_empty'),
        CheckConstraint('entry_count >= 0', name='check_entry_count_positive'),
        CheckConstraint('total_words >= 0', name='check_total_words_positive'),
    )

    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Title cannot be empty')
        return v.strip()

    @field_validator('description')
    @classmethod
    def validate_description(cls, v):
        if v and len(v.strip()) == 0:
            return None
        return v.strip() if v else v

    @field_validator('color')
    @classmethod
    def validate_color(cls, v):
        if v is None:
            return v
        if isinstance(v, JournalColor):
            return v
        value = v.strip().upper()
        try:
            return JournalColor(value)
        except ValueError as exc:
            allowed = ", ".join(color.value for color in JournalColor)
            raise ValueError(f"Color must be one of predefined palette values: {allowed}") from exc
