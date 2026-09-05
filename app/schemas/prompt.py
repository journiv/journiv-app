"""
Prompt schemas.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, validator

from app.models.enums import PromptCategory
from app.schemas.base import TimestampMixin


class PromptBase(BaseModel):
    """Base prompt schema."""

    text: str
    category: Optional[str] = None
    difficulty_level: int = 1
    estimated_time_minutes: Optional[int] = None

    @validator("text")
    def validate_text_not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Text cannot be empty")
        return value.strip()

    @validator("category")
    def validate_category(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        allowed = {category.value for category in PromptCategory}
        if normalized not in allowed:
            raise ValueError(
                f"Invalid category: {value}. Must be one of {sorted(allowed)}"
            )
        return normalized


class PromptResponse(PromptBase, TimestampMixin):
    """Prompt response schema."""

    id: uuid.UUID
    is_active: bool
    usage_count: int
    # Derived from the signed-in writer's Moments; it is never a global prompt
    # counter and does not need a denormalized database column.
    answered_count: int
    user_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class PromptPageResponse(BaseModel):
    """A deterministic offset page of active system prompts."""

    items: List[PromptResponse]
    total: int
    next_offset: Optional[int] = None
    # Counts deliberately ignore the active category filter, so the browser can
    # keep every category chip available while a writer switches between them.
    category_counts: Dict[str, int]
    all_count: int


class PromptCreate(PromptBase):
    """Prompt creation schema."""

    pass


class PromptUpdate(BaseModel):
    """Prompt update schema."""

    text: Optional[str] = None
    category: Optional[str] = None
    difficulty_level: Optional[int] = None
    estimated_time_minutes: Optional[int] = None
    is_active: Optional[bool] = None

    @validator("text")
    def validate_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("Text cannot be empty")
        return value.strip()

    @validator("category")
    def validate_category(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        allowed = {category.value for category in PromptCategory}
        if normalized not in allowed:
            raise ValueError(
                f"Invalid category: {value}. Must be one of {sorted(allowed)}"
            )
        return normalized

    @validator("difficulty_level")
    def validate_difficulty(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if value < 1 or value > 5:
            raise ValueError("difficulty_level must be between 1 and 5")
        return value

    @validator("estimated_time_minutes")
    def validate_estimated_time(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if value <= 0:
            raise ValueError("estimated_time_minutes must be greater than 0")
        return value
