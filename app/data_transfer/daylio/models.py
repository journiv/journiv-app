"""
Daylio backup models.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DaylioBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class DaylioMood(DaylioBaseModel):
    id: int
    custom_name: Optional[str] = None
    predefined_name_id: int
    mood_group_id: int
    icon_id: int
    state: int = 0


class DaylioTagGroup(DaylioBaseModel):
    id: int
    name: str
    order: Optional[int] = 0
    is_displayed_in_reports: Optional[bool] = None
    is_expanded: Optional[bool] = None
    id_predefined: Optional[int] = None


class DaylioTag(DaylioBaseModel):
    id: int
    name: str
    createdAt: Optional[int] = None
    icon: Optional[int] = None
    order: Optional[int] = 0
    state: Optional[int] = None
    id_tag_group: Optional[int] = None


class DaylioAsset(DaylioBaseModel):
    id: int
    checksum: str
    type: int
    createdAt: Optional[int] = None
    createdAtOffset: Optional[int] = None


class DaylioDayEntry(DaylioBaseModel):
    datetime: int
    year: int
    month: int
    day: int
    hour: int
    minute: int
    timeZoneOffset: Optional[int] = None
    mood: Optional[int] = None
    tags: List[int] = Field(default_factory=list)
    assets: List[int] = Field(default_factory=list)
    note: Optional[str] = None
    note_title: Optional[str] = None
    isFavorite: Optional[bool] = None


class DaylioGoal(DaylioBaseModel):
    goal_id: int
    name: Optional[str] = None
    id_tag: Optional[int] = None
    id_icon: Optional[int] = None
    id_avatar: Optional[int] = None
    id_challenge: Optional[int] = None
    order_number: Optional[int] = None
    order: Optional[int] = None
    reminder_enabled: Optional[bool] = None
    reminder_hour: Optional[int] = None
    reminder_minute: Optional[int] = None
    repeat_type: Optional[int] = None
    repeat_value: Optional[int] = None
    state: Optional[int] = None
    created_at: Optional[int] = None
    is_displayed_in_reports: Optional[bool] = None


class DaylioGoalEntry(DaylioBaseModel):
    id: int
    goalId: int
    createdAt: int
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: Optional[int] = 0


class DaylioGoalSuccessWeek(DaylioBaseModel):
    goal_id: int
    week: int
    year: int
    create_at_day: Optional[int] = None
    create_at_month: Optional[int] = None
    create_at_year: Optional[int] = None


class DaylioBackup(DaylioBaseModel):
    version: int
    dayEntries: List[DaylioDayEntry] = Field(default_factory=list)
    customMoods: List[DaylioMood] = Field(default_factory=list)
    tags: List[DaylioTag] = Field(default_factory=list)
    tag_groups: List[DaylioTagGroup] = Field(default_factory=list)
    goals: List[DaylioGoal] = Field(default_factory=list)
    goalEntries: List[DaylioGoalEntry] = Field(default_factory=list)
    goalSuccessWeeks: List[DaylioGoalSuccessWeek] = Field(default_factory=list)
    assets: List[DaylioAsset] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
