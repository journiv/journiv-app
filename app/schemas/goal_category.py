import uuid
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GoalCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color_value: Optional[int] = None
    icon: Optional[str] = Field(None, max_length=50)
    position: Optional[int] = None


class GoalCategoryCreate(GoalCategoryBase):
    pass


class GoalCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color_value: Optional[int] = None
    icon: Optional[str] = Field(None, max_length=50)
    position: Optional[int] = None


class GoalCategoryResponse(GoalCategoryBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID


class GoalCategoryPositionUpdate(BaseModel):
    id: uuid.UUID
    position: int


class GoalCategoryReorderRequest(BaseModel):
    updates: List[GoalCategoryPositionUpdate]
