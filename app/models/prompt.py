"""
Prompt-related models.
"""
import uuid
from typing import TYPE_CHECKING, List, Optional

from pydantic import field_validator
from sqlalchemy import Column, ForeignKey
from sqlmodel import CheckConstraint, Field, Index, Relationship

from .base import BaseModel
from .enums import PromptCategory

if TYPE_CHECKING:
    from .entry import Entry
    from .user import User


class Prompt(BaseModel, table=True):
    """
    Prompt model for journaling prompts with categorization.
    """
    __tablename__ = "prompt"

    text: str = Field(..., min_length=1, max_length=1000)
    category: Optional[str] = Field(None, max_length=100)  # Should be a PromptCategory enum value
    difficulty_level: int = Field(default=1, ge=1, le=5)  # 1=easy, 5=complex
    estimated_time_minutes: Optional[int] = Field(None, ge=1, le=120)
    is_active: bool = Field(default=True)
    usage_count: int = Field(default=0, ge=0)
    # A user_id of NULL means it's a system prompt
    user_id: Optional[uuid.UUID] = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=True
        )
    )

    # Relations
    user: Optional["User"] = Relationship(back_populates="user_prompts")
    entries: List["Entry"] = Relationship(back_populates="prompt")

    # Table constraints and indexes
    __table_args__ = (
        Index('idx_prompts_category', 'category'),
        Index('idx_prompts_difficulty_level', 'difficulty_level'),
        Index('idx_prompts_user_active', 'user_id', 'is_active'),
        Index('idx_prompts_popular', 'is_active', 'usage_count'),  # For popular prompts queries
        # Constraints
        CheckConstraint('length(text) > 0', name='check_prompt_text_not_empty'),
        CheckConstraint('difficulty_level >= 1 AND difficulty_level <= 5', name='check_difficulty_level_range'),
        CheckConstraint('estimated_time_minutes IS NULL OR estimated_time_minutes > 0', name='check_estimated_time_positive'),
        CheckConstraint('usage_count >= 0', name='check_usage_count_positive'),
    )

    @field_validator('text')
    @classmethod
    def validate_text(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Prompt text cannot be empty')
        return v.strip()

    @field_validator('category')
    @classmethod
    def validate_category(cls, v):
        """Validate and normalize category to lowercase."""
        if v and len(v.strip()) == 0:
            return None

        if v:
            # Normalize to lowercase
            normalized = v.strip().lower()

            # Validate against allowed categories
            allowed_categories = {cat.value for cat in PromptCategory}
            if normalized not in allowed_categories:
                raise ValueError(
                    f'Invalid category: {v}. Must be one of {sorted(allowed_categories)}'
                )

            return normalized

        return v
