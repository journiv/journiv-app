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


# ---------------------------------------------------------------------------
# Analytics endpoint response models
#
# These describe the exact dicts assembled in ``AnalyticsService`` so the
# generated OpenAPI client gets real types instead of ``Dict[str, Any]``. The
# service still returns plain dicts; FastAPI validates them against these models
# and the routes pass ``response_model_exclude_none=True`` so a missing optional
# key stays absent on the wire (the historical ``_strip_none_values`` contract).
# ---------------------------------------------------------------------------


class WritingStreakAnalytics(BaseModel):
    """``GET /analytics/writing-streak`` response.

    ``get_writing_analytics`` always returns the counters (0 when the user has
    written nothing), so they are required; only the two dates can be absent
    (dropped by ``response_model_exclude_none``). No field defaults, so the
    generated OpenAPI schema does not depend on how a Pydantic version
    serialises ``0.0``.
    """
    current_streak: int
    longest_streak: int
    total_entries: int
    total_words: int
    average_words_per_entry: float
    last_entry_date: Optional[date] = None
    streak_start_date: Optional[date] = None


class EntriesByDayPoint(BaseModel):
    """One day of writing activity in :class:`WritingPatterns`."""
    date: date
    entry_count: int
    total_words: int


class MoodPatternPoint(BaseModel):
    """Moments carrying a primary mood on a given day."""
    date: date
    mood_count: int


class TopTagCount(BaseModel):
    """A tag and how often it was used in the analysed window."""
    tag_name: str
    usage_count: int


class WritingPatterns(BaseModel):
    """``GET /analytics/writing-patterns`` response."""
    period_days: int
    entries_by_day: list[EntriesByDayPoint]
    mood_patterns: list[MoodPatternPoint]
    top_tags: list[TopTagCount]


class ProductivityMetrics(BaseModel):
    """``GET /analytics/productivity`` response."""
    current_month_entries: int
    current_month_words: int
    entry_growth_percentage: float
    average_daily_entries: float
    average_words_per_day: float


class JournalAnalyticsRow(BaseModel):
    """Per-journal totals in :class:`JournalAnalytics`."""
    journal_id: uuid.UUID
    title: str
    entry_count: int
    total_words: int
    last_entry: Optional[datetime] = None


class JournalAnalytics(BaseModel):
    """``GET /analytics/journals`` response."""
    journals: list[JournalAnalyticsRow]


class DashboardSummary(BaseModel):
    """The ``summary`` block of :class:`AnalyticsDashboard`."""
    total_journals: int
    total_entries: int
    current_streak: int
    longest_streak: int


class AnalyticsDashboard(BaseModel):
    """``GET /analytics/dashboard`` response."""
    writing_streak: WritingStreakAnalytics
    writing_patterns: WritingPatterns
    productivity: ProductivityMetrics
    journals: JournalAnalytics
    summary: DashboardSummary
