"""
Tag schemas.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, validator

from app.schemas.base import TimestampMixin


class TagBase(BaseModel):
    """Base tag schema."""
    name: str


class TagCreate(TagBase):
    """Tag creation schema."""

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Tag name cannot be empty')
        return v.strip().lower()


class TagUpdate(BaseModel):
    """Tag update schema."""
    name: Optional[str] = None

    @validator('name')
    def validate_name(cls, v):
        if v is None:
            return v
        if not v.strip():
            raise ValueError('Tag name cannot be empty')
        return v.strip().lower()


class TagResponse(TagBase, TimestampMixin):
    """Tag response schema."""
    id: uuid.UUID
    user_id: uuid.UUID
    usage_count: int
    created_at: datetime
    updated_at: datetime


class EntryTagLinkBase(BaseModel):
    """Base entry tag link schema."""
    entry_id: uuid.UUID
    tag_id: uuid.UUID


class EntryTagLinkCreate(EntryTagLinkBase):
    """Entry tag link creation schema."""
    pass


class EntryTagLinkResponse(EntryTagLinkBase, TimestampMixin):
    """Entry tag link response schema."""
    created_at: datetime
    updated_at: datetime
