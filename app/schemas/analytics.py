"""
Analytics schemas.
"""
import uuid
from datetime import date, datetime
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


class EntryDayAnalytics(BaseModel):
    """Entry activity aggregated by day."""
    date: date
    entry_count: int
    total_words: int


class MoodPatternPoint(BaseModel):
    """Mood activity aggregated by day."""
    date: date
    mood_count: int


class TagUsagePoint(BaseModel):
    """Tag usage counts."""
    tag_name: str
    usage_count: int


class WritingPatternsResponse(BaseModel):
    """Writing patterns response payload."""
    period_days: int
    entries_by_day: list[EntryDayAnalytics]
    mood_patterns: list[MoodPatternPoint]
    top_tags: list[TagUsagePoint]


class ProductivityMetricsResponse(BaseModel):
    """Productivity metrics response payload."""
    current_month_entries: int
    current_month_words: int
    entry_growth_percentage: float
    average_daily_entries: float
    average_words_per_day: float


class JournalAnalyticsItem(BaseModel):
    """Per-journal analytics summary."""
    journal_id: uuid.UUID
    title: str
    entry_count: int
    total_words: int
    last_entry: Optional[datetime] = None


class JournalAnalyticsResponse(BaseModel):
    """Journal analytics response payload."""
    journals: list[JournalAnalyticsItem]


class DashboardSummaryResponse(BaseModel):
    """Top-level dashboard summary."""
    total_journals: int
    total_entries: int
    current_streak: int
    longest_streak: int


class AnalyticsDashboardResponse(BaseModel):
    """Combined analytics dashboard response."""
    writing_streak: WritingStreakBase
    writing_patterns: WritingPatternsResponse
    productivity: ProductivityMetricsResponse
    journals: JournalAnalyticsResponse
    summary: DashboardSummaryResponse
