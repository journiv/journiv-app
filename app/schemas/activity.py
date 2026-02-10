"""
Activity-related schemas for API requests and responses.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from app.schemas.base import TimestampMixin

# Activity schemas

class ActivityBase(BaseModel):
    """Base activity schema."""
    name: str
    icon: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None
    group_id: Optional[uuid.UUID] = None


class ActivityCreate(ActivityBase):
    """Activity creation schema."""

    @field_validator('name')
    @classmethod
    def validate_name_not_empty(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Activity name cannot be empty')
        return v.strip()


class ActivityUpdate(BaseModel):
    """Activity update schema."""
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None
    group_id: Optional[uuid.UUID] = None

    @field_validator('name')
    @classmethod
    def validate_name_not_empty(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError('Activity name cannot be empty')
        return v.strip() if v else v


class ActivityResponse(ActivityBase, TimestampMixin):
    """Activity response schema."""
    id: uuid.UUID
    user_id: uuid.UUID
    group_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ActivityWithUsageResponse(ActivityResponse):
    """Activity response with usage count."""
    usage_count: int


class ActivityPositionUpdate(BaseModel):
    id: uuid.UUID
    position: int


class ActivityReorderRequest(BaseModel):
    updates: list[ActivityPositionUpdate]
