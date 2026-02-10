import uuid
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.activity import ActivityResponse


class ActivityGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color_value: Optional[int] = None
    icon: Optional[str] = Field(None, max_length=50)
    position: int = Field(default=0)

class ActivityGroupCreate(ActivityGroupBase):
    pass

class ActivityGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color_value: Optional[int] = None
    icon: Optional[str] = Field(None, max_length=50)
    position: Optional[int] = None

class ActivityGroupResponse(ActivityGroupBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID

class ActivityGroupWithActivitiesResponse(ActivityGroupResponse):
    activities: List[ActivityResponse] = []


class ActivityGroupPositionUpdate(BaseModel):
    id: uuid.UUID
    position: int


class ActivityGroupReorderRequest(BaseModel):
    updates: List[ActivityGroupPositionUpdate]
