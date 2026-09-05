"""Response schemas for the prompt analytics workspace."""

import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel


class PromptCategoryAnalytics(BaseModel):
    """How often the current writer has answered one prompt category."""

    category: str
    answered_count: int


class PromptCompletionWeek(BaseModel):
    """Prompt-linked Moments completed in the calendar week beginning here."""

    week_start: date
    answered_count: int


class PromptMostUsedAnalytics(BaseModel):
    """The current writer's most frequently answered prompt, when one exists."""

    id: uuid.UUID
    text: str
    answered_count: int


class PromptAnalyticsResponse(BaseModel):
    """``GET /prompts/analytics/statistics`` response for the current writer."""

    prompts_answered: int
    total_answers: int
    current_streak: int
    favorite_categories: list[PromptCategoryAnalytics]
    completion_trend: list[PromptCompletionWeek]
    most_used_prompt: Optional[PromptMostUsedAnalytics] = None
