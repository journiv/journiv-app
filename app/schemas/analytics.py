"""
Analytics schemas.
"""
import uuid
from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel

from app.schemas.base import TimestampMixin


class WritingStreakBase(BaseModel):
    """Base writing streak schema."""
    current_streak: int = 0
    longest_streak: int = 0
    last_entry_date: Optional[date] = None
    streak_start_date: Optional[date] = None
    total_entries: int = 0
    total_words: int = 0
    average_words_per_entry: float = 0.0


class WritingStreakResponse(WritingStreakBase, TimestampMixin):
    """Writing streak response schema."""
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AnalyticsSummary(BaseModel):
    """Analytics summary schema."""
    total_entries: int
    total_words: int
    current_streak: int
    longest_streak: int
    average_words_per_entry: float
    entries_this_month: int
    entries_this_week: int
    most_used_tags: list[dict]
    mood_distribution: dict
    writing_frequency: dict
