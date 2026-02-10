"""
Moment schemas.
"""
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.activity import ActivityResponse
from app.schemas.base import TimestampMixin
from app.schemas.entry import EntryBase, EntryPreviewResponse, EntryUpdate
from app.schemas.mood import MoodResponse


class MomentMoodActivityInput(BaseModel):
    mood_id: Optional[uuid.UUID] = None
    activity_id: Optional[uuid.UUID] = None

    @model_validator(mode="after")
    def validate_not_empty(self) -> "MomentMoodActivityInput":
        if self.mood_id is None and self.activity_id is None:
            raise ValueError("mood_id or activity_id is required")
        return self


class MomentEntryCreate(EntryBase):
    journal_id: uuid.UUID
    prompt_id: Optional[uuid.UUID] = None
    activity_ids: Optional[List[uuid.UUID]] = None


class MomentCreate(BaseModel):
    entry: Optional[MomentEntryCreate] = None
    logged_at: Optional[datetime] = None
    logged_date: Optional[date] = None
    logged_timezone: Optional[str] = None
    note: Optional[str] = Field(None, max_length=500)
    location_data: Optional[Dict[str, Any]] = None
    weather_data: Optional[Dict[str, Any]] = None
    primary_mood_id: Optional[uuid.UUID] = None
    mood_activity: List[MomentMoodActivityInput] = Field(default_factory=list)


class MomentUpdate(BaseModel):
    entry_update: Optional[EntryUpdate] = None
    entry_create: Optional[MomentEntryCreate] = None
    logged_at: Optional[datetime] = None
    logged_date: Optional[date] = None
    logged_timezone: Optional[str] = None
    note: Optional[str] = Field(None, max_length=500)
    location_data: Optional[Dict[str, Any]] = None
    weather_data: Optional[Dict[str, Any]] = None
    primary_mood_id: Optional[uuid.UUID] = None
    mood_activity: Optional[List[MomentMoodActivityInput]] = None

    @model_validator(mode="after")
    def validate_entry_payload(self) -> "MomentUpdate":
        if self.entry_update and self.entry_create:
            raise ValueError("Provide only one of entry_update or entry_create")
        return self


class MomentMoodActivityResponse(TimestampMixin):
    id: uuid.UUID
    mood: Optional[MoodResponse] = None
    activity: Optional[ActivityResponse] = None


class MomentResponse(TimestampMixin):
    id: uuid.UUID
    user_id: uuid.UUID
    entry_id: Optional[uuid.UUID] = None
    entry: Optional[EntryPreviewResponse] = None
    primary_mood_id: Optional[uuid.UUID] = None
    logged_at: datetime
    logged_date: date
    logged_timezone: str
    note: Optional[str] = None
    location_data: Optional[Dict[str, Any]] = None
    weather_data: Optional[Dict[str, Any]] = None
    mood_activity: List[MomentMoodActivityResponse] = Field(default_factory=list)


class MomentCalendarItem(BaseModel):
    logged_date: date
    primary_mood_id: Optional[uuid.UUID] = None
    moment_count: int = 0


class MomentPageResponse(BaseModel):
    items: List[MomentResponse]
    next_cursor_logged_at: Optional[datetime] = None
    next_cursor_id: Optional[uuid.UUID] = None
