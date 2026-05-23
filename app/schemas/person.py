"""
People schemas.
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import TimestampMixin


class PersonSort(str, Enum):
    by_name = "by_name"
    frequent = "frequent"
    recent = "recent"


class PersonGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color_value: Optional[int] = None
    icon: Optional[str] = Field(None, max_length=50)
    position: int = Field(default=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            raise ValueError("Group name cannot be empty")
        return cleaned


class PersonGroupCreate(PersonGroupBase):
    position: Optional[int] = None


class PersonGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color_value: Optional[int] = None
    icon: Optional[str] = Field(None, max_length=50)
    position: Optional[int] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Group name cannot be empty")
        return cleaned


class PersonGroupSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color_value: Optional[int] = None
    icon: Optional[str] = None


class PersonGroupResponse(PersonGroupBase, TimestampMixin):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PersonSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    nickname: Optional[str] = None
    profile_image_url: Optional[str] = None


class PersonGroupWithPeopleResponse(PersonGroupResponse):
    people: List[PersonSummaryResponse] = Field(default_factory=list)


class PersonGroupPositionUpdate(BaseModel):
    id: uuid.UUID
    position: int


class PersonGroupReorderRequest(BaseModel):
    updates: List[PersonGroupPositionUpdate]


class PersonBase(BaseModel):
    name: str
    nickname: Optional[str] = None
    note: Optional[str] = None


class PersonCreate(PersonBase):
    group_ids: List[uuid.UUID] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            raise ValueError("Person name cannot be empty")
        return cleaned


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    nickname: Optional[str] = None
    note: Optional[str] = None
    group_ids: Optional[List[uuid.UUID]] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Person name cannot be empty")
        return cleaned


class PersonResponse(PersonSummaryResponse, TimestampMixin):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    note: Optional[str] = None
    archived_at: Optional[datetime] = None
    memory_count: int = 0
    last_seen_at_utc: Optional[datetime] = None
    groups: List[PersonGroupSummaryResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MomentPeopleReplaceRequest(BaseModel):
    person_ids: List[uuid.UUID] = Field(default_factory=list)
