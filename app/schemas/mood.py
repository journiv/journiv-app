"""
Mood schemas.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from app.schemas.base import TimestampMixin


class MoodBase(BaseModel):
    """Base mood schema."""
    name: str
    key: Optional[str] = None
    icon: Optional[str] = None
    color_value: Optional[int] = None
    category: str
    score: int
    position: int = 0
    is_active: bool = True
    user_id: Optional[uuid.UUID] = None


class MoodCreate(BaseModel):
    name: str
    icon: Optional[str] = None
    color_value: Optional[int] = None
    score: int
    position: Optional[int] = None

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: int) -> int:
        if value < 1 or value > 5:
            raise ValueError("Score must be between 1 and 5")
        return value


class MoodUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color_value: Optional[int] = None
    score: Optional[int] = None
    position: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if value < 1 or value > 5:
            raise ValueError("Score must be between 1 and 5")
        return value


class MoodResponse(MoodBase, TimestampMixin):
    """Mood response schema."""
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    is_hidden: bool = False
    sort_order: Optional[int] = None


class MoodVisibilityUpdate(BaseModel):
    is_hidden: bool


class MoodReorderRequest(BaseModel):
    mood_ids: list[uuid.UUID]
