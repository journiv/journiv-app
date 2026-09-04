"""
Mood analytics schemas.

These describe the exact dicts assembled in ``MoodService.get_mood_statistics``
and ``MoodService.get_mood_streak`` so the generated OpenAPI client gets real
types instead of ``Dict[str, Any]``. The service still returns plain dicts;
FastAPI validates them against these models and the routes pass
``response_model_exclude_none=True`` so a missing optional key stays absent on
the wire (the historical ``_strip_none_values`` contract).
"""
from datetime import date
from typing import Optional

from pydantic import BaseModel


class MoodDateRange(BaseModel):
    """The analysed window echoed back in :class:`MoodStatistics`."""
    start_date: date
    end_date: date


class MostFrequentMood(BaseModel):
    """The single most-logged mood in the analysed window."""
    name: str
    category: str
    count: int


class MoodCount(BaseModel):
    """One mood and its log count."""
    mood: str
    category: str
    count: int


class MoodDailyTrend(BaseModel):
    """Per-day count of mood logs in one category."""
    date: date
    category: str
    count: int


class MoodStatistics(BaseModel):
    """``GET /moods/analytics/statistics`` response."""
    total_logs: int
    date_range: MoodDateRange
    mood_distribution: dict[str, float]
    most_frequent_mood: Optional[MostFrequentMood] = None
    mood_counts: list[MoodCount]
    daily_trends: list[MoodDailyTrend]


class MoodStreak(BaseModel):
    """``GET /moods/analytics/streak`` response.

    ``get_mood_streak`` always returns the two counters (0 when nothing is
    logged); only ``last_logged_date`` can be absent.
    """
    current_streak: int
    total_days_logged: int
    last_logged_date: Optional[date] = None
