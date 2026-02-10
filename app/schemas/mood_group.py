"""
Mood group schemas.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.mood import MoodResponse


class MoodGroupBase(BaseModel):
    name: str
    icon: Optional[str] = None
    color_value: Optional[int] = None
    position: int = 0
    user_id: Optional[uuid.UUID] = None


class MoodGroupCreate(BaseModel):
    name: str
    icon: Optional[str] = None
    color_value: Optional[int] = None
    position: Optional[int] = None
    mood_ids: Optional[List[uuid.UUID]] = None


class MoodGroupUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color_value: Optional[int] = None
    position: Optional[int] = None
    mood_ids: Optional[List[uuid.UUID]] = None


class MoodGroupResponse(MoodGroupBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    is_hidden: bool = False
    model_config = {"from_attributes": True}


class MoodGroupWithMoodsResponse(MoodGroupResponse):
    moods: List[MoodResponse] = []


class MoodGroupVisibilityUpdate(BaseModel):
    is_hidden: bool


class MoodGroupReorderItem(BaseModel):
    id: uuid.UUID
    position: int


class MoodGroupReorderRequest(BaseModel):
    updates: List[MoodGroupReorderItem]


class MoodGroupMoodReorderRequest(BaseModel):
    mood_ids: List[uuid.UUID]
