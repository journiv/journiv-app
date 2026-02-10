"""
Goal schemas.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, conint

from app.models.enums import GoalFrequency, GoalLogStatus, GoalType
from app.schemas.base import TimestampMixin
from app.schemas.goal_category import GoalCategoryResponse


class GoalBase(BaseModel):
    title: str
    activity_id: Optional[uuid.UUID] = None
    category_id: Optional[uuid.UUID] = None
    goal_type: GoalType = GoalType.ACHIEVE
    frequency_type: GoalFrequency = GoalFrequency.DAILY
    target_count: conint(ge=1) = 1  # type: ignore[valid-type]
    reminder_time: Optional[str] = None
    is_paused: bool = False
    icon: Optional[str] = None
    color_value: Optional[int] = None
    position: int = 0


class GoalCreate(GoalBase):
    pass


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    activity_id: Optional[uuid.UUID] = None
    category_id: Optional[uuid.UUID] = None
    goal_type: Optional[GoalType] = None
    frequency_type: Optional[GoalFrequency] = None
    target_count: Optional[conint(ge=1)] = None  # type: ignore[valid-type]
    reminder_time: Optional[str] = None
    is_paused: Optional[bool] = None
    icon: Optional[str] = None
    color_value: Optional[int] = None
    position: Optional[int] = None


class GoalResponse(GoalBase, TimestampMixin):
    id: uuid.UUID
    user_id: uuid.UUID
    archived_at: Optional[datetime] = None
    category: Optional[GoalCategoryResponse] = None


class GoalWithProgressResponse(GoalResponse):
    current_period_completed: int = 0
    target_count: conint(ge=1) = 1  # type: ignore[valid-type]
    status: Optional[GoalLogStatus] = None


class GoalLogResponse(TimestampMixin):
    id: uuid.UUID
    goal_id: uuid.UUID
    user_id: uuid.UUID
    logged_date: date
    period_start: date
    period_end: date
    status: GoalLogStatus
    count: int
    source: str
    last_updated_at: datetime
    moment_id: Optional[uuid.UUID] = None


class GoalToggleRequest(BaseModel):
    logged_date: date
    status: Optional[GoalLogStatus] = None


class GoalPositionUpdate(BaseModel):
    id: uuid.UUID
    position: int


class GoalReorderRequest(BaseModel):
    updates: List[GoalPositionUpdate]
