"""
Mood schemas.
"""
import uuid
from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, Field, field_serializer

from app.schemas.base import TimestampMixin


class MoodBase(BaseModel):
    """Base mood schema."""
    name: str
    icon: Optional[str] = None
    category: str


class MoodResponse(MoodBase, TimestampMixin):
    """Mood response schema."""
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class MoodLogBase(BaseModel):
    """Base mood log schema."""
    mood_id: uuid.UUID
    note: Optional[str] = None


class MoodLogCreate(MoodLogBase):
    """Mood log creation schema."""
    entry_id: Optional[uuid.UUID] = None


class MoodLogUpdate(BaseModel):
    """Mood log update schema."""
    mood_id: Optional[uuid.UUID] = None
    note: Optional[str] = None


class MoodLogResponse(MoodLogBase, TimestampMixin):
    """Mood log response schema."""
    id: uuid.UUID
    user_id: uuid.UUID
    entry_id: Optional[uuid.UUID] = None
    created_at: datetime
    logged_date: date = Field(description="The date this mood represents")
    mood: Optional[MoodResponse] = None
    entry_date: Optional[date] = Field(None, description="Date from associated entry if available (deprecated, use logged_date)")

    @field_serializer('logged_date', 'entry_date')
    def serialize_dates(self, v: Optional[date], _info) -> Optional[str]:
        """Serialize date to ISO format string."""
        return v.isoformat() if v else None
