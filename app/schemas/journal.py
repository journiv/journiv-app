"""
Journal schemas.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import JournalColor
from app.schemas.base import TimestampMixin

ENTRY_TEMPLATE_MAX_LENGTH = 5000


def normalize_entry_template(value: Optional[str]) -> Optional[str]:
    """
    Unify line endings and drop trailing whitespace; leading whitespace and
    blank lines between questions are the writer's layout. Blank means no
    template.
    """
    if value is None:
        return None
    text = value.replace("\r\n", "\n").replace("\r", "\n").rstrip()
    return text or None


_ENTRY_TEMPLATE_DESCRIPTION = (
    "Plain text pre-filled into the body of every new entry written in this "
    "journal, e.g. a few fixed questions. Null or blank means no template."
)


class JournalBase(BaseModel):
    """Base journal schema."""
    title: str
    description: Optional[str] = None
    color: Optional[JournalColor] = None
    icon: Optional[str] = None
    entry_template: Optional[str] = Field(
        default=None,
        max_length=ENTRY_TEMPLATE_MAX_LENGTH,
        description=_ENTRY_TEMPLATE_DESCRIPTION,
    )

    @field_validator("entry_template")
    @classmethod
    def _normalize_entry_template(cls, v: Optional[str]) -> Optional[str]:
        return normalize_entry_template(v)


class JournalCreate(JournalBase):
    """Journal creation schema."""
    pass


class JournalUpdate(BaseModel):
    """Journal update schema."""
    title: Optional[str] = None
    description: Optional[str] = None
    color: Optional[JournalColor] = None
    icon: Optional[str] = None
    entry_template: Optional[str] = Field(
        default=None,
        max_length=ENTRY_TEMPLATE_MAX_LENGTH,
        description=(
            _ENTRY_TEMPLATE_DESCRIPTION
            + " Omit to leave unchanged; send null or an empty string to remove it."
        ),
    )
    is_favorite: Optional[bool] = None
    is_archived: Optional[bool] = None

    @field_validator("entry_template")
    @classmethod
    def _normalize_entry_template(cls, v: Optional[str]) -> Optional[str]:
        return normalize_entry_template(v)


class JournalResponse(JournalBase, TimestampMixin):
    """Journal response schema."""
    id: uuid.UUID
    user_id: uuid.UUID
    is_favorite: bool
    is_archived: bool
    position: Optional[int] = None
    entry_count: int
    total_words: int
    last_entry_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class JournalReorderItem(BaseModel):
    """Single journal reorder item."""
    id: uuid.UUID
    position: int = Field(..., ge=0, description="New position (0-indexed)")


class JournalReorderRequest(BaseModel):
    """Request to reorder multiple journals."""
    updates: List[JournalReorderItem] = Field(..., min_length=1, description="List of journal ID and position pairs")
