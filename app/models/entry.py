"""
Entry-related models.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from pydantic import field_validator
from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import JSON, CheckConstraint, Field, Index, Relationship
from sqlmodel import Column as SQLModelColumn

from app.utils.quill_delta import extract_plain_text

from .base import BaseModel

if TYPE_CHECKING:
    from .journal import Journal
    from .moment import Moment
    from .user import User


def JSONType():
    return JSONB().with_variant(JSON, "sqlite")


class Entry(BaseModel, table=True):
    """
    Journal entry model — narrative text extension of a Moment.

    Contains only text content. All contextual metadata (time, location,
    weather, tags, media, mood, activities) lives on the parent Moment.
    """
    __tablename__ = "entry"

    title: Optional[str] = Field(None, max_length=300)
    content_delta: Optional[dict] = Field(
        default=None,
        sa_column=SQLModelColumn(JSONType()),
        description="Quill Delta payload (stored as JSON/JSONB)",
    )
    content_plain_text: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="Plain-text extraction from content_delta for search/indexing",
    )
    journal_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("journal.id", ondelete="CASCADE"),
            nullable=False
        )
    )
    moment_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("moment.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    word_count: int = Field(default=0, ge=0, le=50000)
    is_draft: bool = Field(
        default=False,
        sa_column=Column(Boolean, server_default="false", nullable=False, index=True),
        description="Draft entries are not yet finalized"
    )
    import_metadata: Optional[dict] = Field(
        default=None,
        sa_column=SQLModelColumn(JSONType()),
        description="Import metadata for preserving source details"
    )

    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )

    # Relations
    journal: "Journal" = Relationship(back_populates="entries")
    user: "User" = Relationship(back_populates="entries")
    moment: "Moment" = Relationship(back_populates="entry")

    # Table constraints and indexes
    __table_args__ = (
        Index('idx_entries_created_at', 'created_at'),
        Index('idx_entry_moment_id', 'moment_id'),
        UniqueConstraint('moment_id', name='uq_entry_moment_id'),

        # Constraints
        CheckConstraint('word_count >= 0', name='check_word_count_positive'),
    )

    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if v and len(v.strip()) == 0:
            return None
        return v.strip() if v else v


def _should_refresh_plain_text(entry: Entry) -> bool:
    try:
        state = inspect(entry)
        attrs = getattr(state, "attrs", None)
        if attrs is None or not hasattr(attrs, "content_delta"):
            return True
        return attrs.content_delta.history.has_changes()
    except Exception:
        return True


@event.listens_for(Entry, "before_insert")
def _entry_before_insert(mapper, connection, target: Entry) -> None:
    plain_text = extract_plain_text(target.content_delta)
    target.content_plain_text = plain_text or None
    target.word_count = len(plain_text.split()) if plain_text else 0


@event.listens_for(Entry, "before_update")
def _entry_before_update(mapper, connection, target: Entry) -> None:
    if not _should_refresh_plain_text(target):
        return
    plain_text = extract_plain_text(target.content_delta)
    target.content_plain_text = plain_text or None
    target.word_count = len(plain_text.split()) if plain_text else 0
