"""
Moment schemas.
"""
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.enums import GoalLogStatus
from app.schemas.activity import ActivityResponse
from app.schemas.base import TimestampMixin
from app.schemas.entry import EntryPreviewResponse, EntryUpdate, QuillDelta
from app.schemas.media_thumbnail import MomentMediaThumbnail
from app.schemas.mood import MoodResponse
from app.schemas.tag import TagResponse


class MomentMoodActivityInput(BaseModel):
    mood_id: Optional[uuid.UUID] = None
    activity_id: Optional[uuid.UUID] = None

    @model_validator(mode="after")
    def validate_not_empty(self) -> "MomentMoodActivityInput":
        if self.mood_id is None and self.activity_id is None:
            raise ValueError("mood_id or activity_id is required")
        return self


class MomentEntryCreate(BaseModel):
    """Entry content to create inline with a moment."""
    title: Optional[str] = None
    content_delta: Optional[QuillDelta] = None
    journal_id: uuid.UUID


class MomentCreate(BaseModel):
    entry: Optional[MomentEntryCreate] = None
    logged_at_utc: Optional[datetime] = None
    logged_date_tz: Optional[date] = None
    logged_timezone: Optional[str] = None
    note: Optional[str] = Field(None, max_length=500)
    location_json: Optional[Dict[str, Any]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    weather_json: Optional[Dict[str, Any]] = None
    weather_summary: Optional[str] = None
    is_pinned: bool = False
    prompt_id: Optional[uuid.UUID] = None
    primary_mood_id: Optional[uuid.UUID] = None
    mood_activity: List[MomentMoodActivityInput] = Field(default_factory=list)


class MomentUpdate(BaseModel):
    entry_update: Optional[EntryUpdate] = None
    entry_create: Optional[MomentEntryCreate] = None
    logged_at_utc: Optional[datetime] = None
    logged_date_tz: Optional[date] = None
    logged_timezone: Optional[str] = None
    note: Optional[str] = Field(None, max_length=500)
    location_json: Optional[Dict[str, Any]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    weather_json: Optional[Dict[str, Any]] = None
    weather_summary: Optional[str] = None
    is_pinned: Optional[bool] = None
    prompt_id: Optional[uuid.UUID] = None
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


class MomentCompletedGoalResponse(BaseModel):
    goal_id: uuid.UUID
    title: str
    icon: Optional[str] = None
    color_value: Optional[int] = None
    status: GoalLogStatus
    count: int


class MomentResponse(TimestampMixin):
    id: uuid.UUID
    user_id: uuid.UUID
    entry: Optional[EntryPreviewResponse] = None
    primary_mood_id: Optional[uuid.UUID] = None
    prompt_id: Optional[uuid.UUID] = None
    logged_at_utc: datetime
    logged_date_tz: date
    logged_timezone: str
    note: Optional[str] = None
    location_json: Optional[Dict[str, Any]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    weather_json: Optional[Dict[str, Any]] = None
    weather_summary: Optional[str] = None
    is_pinned: bool = False
    mood_activity: List[MomentMoodActivityResponse] = Field(default_factory=list)
    tags: List[TagResponse] = Field(default_factory=list)
    completed_goals: List[MomentCompletedGoalResponse] = Field(default_factory=list)
    media_count: int = 0
    media: List[MomentMediaThumbnail] = Field(default_factory=list)


class MomentCalendarItem(BaseModel):
    logged_date_tz: date
    primary_mood_id: Optional[uuid.UUID] = None
    moment_count: int = 0


class MomentPageResponse(BaseModel):
    items: List[MomentResponse]
    next_cursor_logged_at_utc: Optional[datetime] = None
    next_cursor_id: Optional[uuid.UUID] = None
