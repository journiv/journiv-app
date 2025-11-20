"""
Analytics endpoint integration tests.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict

import pytest

from tests.integration.helpers import EndpointCase, assert_requires_authentication
from tests.lib import ApiUser, JournivApiClient


def _content_with_words(word_count: int) -> str:
    """Create deterministic entry content with a predictable word count."""
    return " ".join(f"word{idx}" for idx in range(word_count))


@dataclass
class AnalyticsSeedData:
    """Structured data returned by the analytics_dataset fixture."""

    primary_journal: Dict[str, Any]
    secondary_journal: Dict[str, Any]
    total_entries: int
    total_words: int
    current_month_entries: int
    current_month_words: int
    last_month_entries: int
    entries_by_day: Dict[str, Dict[str, int]]
    mood_dates: set[str]
    tag_usage: Dict[str, int]
    journal_entry_counts: Dict[str, int]
    journal_word_totals: Dict[str, int]
    streak_start_date: date
    streak_end_date: date
    current_streak: int
    longest_streak: int


@pytest.fixture
def analytics_dataset(
    api_client: JournivApiClient, api_user: ApiUser, journal_factory
) -> AnalyticsSeedData:
    """
    Create a realistic set of entries, moods, and tags for analytics coverage.
    """
    token = api_user.access_token
    primary = journal_factory(title="Analytics Primary")
    secondary = journal_factory(title="Analytics Secondary")

    today = date.today()
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    total_entries = 0
    total_words = 0
    current_month_entries = 0
    current_month_words = 0
    last_month_entries = 0
    entries_by_day: Dict[str, Dict[str, int]] = {}
    journal_entry_counts: Dict[str, int] = defaultdict(int)
    journal_word_totals: Dict[str, int] = defaultdict(int)

    def _register_entry(entry_date: date, words: int, journal_id: str) -> None:
        nonlocal total_entries, total_words, current_month_entries, current_month_words, last_month_entries
        iso_date = entry_date.isoformat()
        day_stats = entries_by_day.setdefault(iso_date, {"entry_count": 0, "total_words": 0})
        day_stats["entry_count"] += 1
        day_stats["total_words"] += words

        journal_entry_counts[journal_id] += 1
        journal_word_totals[journal_id] += words

        total_entries += 1
        total_words += words
        if entry_date >= month_start:
            current_month_entries += 1
            current_month_words += words
        elif last_month_start <= entry_date < month_start:
            last_month_entries += 1

    def _create_entry(journal: Dict[str, Any], entry_date: date, words: int, title: str) -> Dict[str, Any]:
        entry = api_client.create_entry(
            token,
            journal_id=journal["id"],
            title=title,
            content=_content_with_words(words),
            entry_date=entry_date.isoformat(),
            entry_timezone="UTC",
        )
        _register_entry(entry_date, words, journal["id"])
        return {"id": entry["id"], "date": entry_date}

    # Entries that build history outside the streak.
    last_month_entry_date = last_month_start + timedelta(days=2)
    _create_entry(secondary, last_month_entry_date, 15, "Secondary last month")
    _create_entry(secondary, today - timedelta(days=6), 12, "Secondary active entry")
    _create_entry(primary, today - timedelta(days=10), 18, "Primary warmup")

    # Create a 4-day streak leading up to today.
    streak_dates = [today - timedelta(days=offset) for offset in range(3, -1, -1)]
    streak_entries = []
    for idx, entry_date in enumerate(streak_dates):
        words = 20 + (idx * 10)
        streak_entries.append(
            _create_entry(primary, entry_date, words, f"Streak day {idx + 1}")
        )

    # Tag usage for writing pattern analytics.
    def _assign_tags(entry_id: str, names: list[str]) -> None:
        api_client.request(
            "POST",
            f"/tags/entry/{entry_id}/bulk",
            token=token,
            json=names,
            expected=(200,),
        )

    _assign_tags(streak_entries[-1]["id"], ["gratitude"])
    _assign_tags(streak_entries[-2]["id"], ["gratitude", "focus"])
    tag_usage = {"gratitude": 2, "focus": 1}

    # Mood logs to exercise writing pattern mood tracking.
    moods = api_client.list_moods(token)
    if not moods:
        pytest.skip("Analytics tests require at least one mood to be configured.")
    mood_id = moods[0]["id"]
    mood_dates = {
        streak_entries[-1]["date"].isoformat(),
        streak_entries[-2]["date"].isoformat(),
    }
    for entry in streak_entries[-2:]:
        api_client.create_mood_log(
            token,
            entry_id=entry["id"],
            mood_id=mood_id,
            logged_date=entry["date"].isoformat(),
            notes="Analytics coverage",
        )

    return AnalyticsSeedData(
        primary_journal=primary,
        secondary_journal=secondary,
        total_entries=total_entries,
        total_words=total_words,
        current_month_entries=current_month_entries,
        current_month_words=current_month_words,
        last_month_entries=last_month_entries,
        entries_by_day=entries_by_day,
        mood_dates=mood_dates,
        tag_usage=tag_usage,
        journal_entry_counts=dict(journal_entry_counts),
        journal_word_totals=dict(journal_word_totals),
        streak_start_date=streak_dates[0],
        streak_end_date=streak_dates[-1],
        current_streak=len(streak_dates),
        longest_streak=len(streak_dates),
    )


def test_writing_streak_metrics_reflect_actual_entries(
    api_client: JournivApiClient,
    api_user: ApiUser,
    analytics_dataset: AnalyticsSeedData,
):
    """Writing streak analytics should reflect the seeded streak exactly."""
    data = api_client.request(
        "GET", "/analytics/writing-streak", token=api_user.access_token
    ).json()

    assert data["current_streak"] == analytics_dataset.current_streak
    assert data["longest_streak"] == analytics_dataset.longest_streak
    assert data["total_entries"] == analytics_dataset.total_entries
    assert data["total_words"] == analytics_dataset.total_words

    expected_average = round(
        analytics_dataset.total_words / analytics_dataset.total_entries, 2
    )
    assert data["average_words_per_entry"] == expected_average
    assert data["streak_start_date"] == analytics_dataset.streak_start_date.isoformat()
    assert data["last_entry_date"] == analytics_dataset.streak_end_date.isoformat()


def test_writing_patterns_include_entries_moods_and_tags(
    api_client: JournivApiClient,
    api_user: ApiUser,
    analytics_dataset: AnalyticsSeedData,
):
    """Writing patterns must capture entry frequency, moods, and tag usage."""
    patterns = api_client.request(
        "GET",
        "/analytics/writing-patterns",
        token=api_user.access_token,
        params={"days": 60},
    ).json()

    assert patterns["period_days"] == 60

    by_day = {item["date"]: item for item in patterns["entries_by_day"]}
    for day, expected in analytics_dataset.entries_by_day.items():
        assert day in by_day, f"Missing activity for {day}"
        assert by_day[day]["entry_count"] == expected["entry_count"]
        assert by_day[day]["total_words"] == expected["total_words"]

    mood_counts = {item["date"]: item["mood_count"] for item in patterns["mood_patterns"]}
    for day in analytics_dataset.mood_dates:
        assert mood_counts.get(day) == 1

    tag_counts = {item["tag_name"]: item["usage_count"] for item in patterns["top_tags"]}
    for tag_name, count in analytics_dataset.tag_usage.items():
        assert tag_counts.get(tag_name) == count


def test_productivity_metrics_compare_current_and_last_month(
    api_client: JournivApiClient,
    api_user: ApiUser,
    analytics_dataset: AnalyticsSeedData,
):
    """Productivity metrics should include per-month statistics and growth."""
    metrics = api_client.request(
        "GET", "/analytics/productivity", token=api_user.access_token
    ).json()

    assert metrics["current_month_entries"] == analytics_dataset.current_month_entries
    assert metrics["current_month_words"] == analytics_dataset.current_month_words

    today = date.today()
    divisor = today.day or 1
    expected_avg_entries = round(analytics_dataset.current_month_entries / divisor, 2)
    expected_avg_words = round(analytics_dataset.current_month_words / divisor, 2)
    assert metrics["average_daily_entries"] == pytest.approx(expected_avg_entries, abs=0.5)
    assert metrics["average_words_per_day"] == pytest.approx(expected_avg_words, abs=1.0)

    if analytics_dataset.last_month_entries:
        expected_growth = round(
            (
                (analytics_dataset.current_month_entries - analytics_dataset.last_month_entries)
                / analytics_dataset.last_month_entries
            )
            * 100,
            2,
        )
    else:
        expected_growth = 0
    assert metrics["entry_growth_percentage"] == expected_growth


def test_journal_analytics_break_down_activity_per_journal(
    api_client: JournivApiClient,
    api_user: ApiUser,
    analytics_dataset: AnalyticsSeedData,
):
    """Journal analytics should list entry counts and words per journal."""
    analytics = api_client.request(
        "GET", "/analytics/journals", token=api_user.access_token
    ).json()

    journals = {item["journal_id"]: item for item in analytics["journals"]}
    for journal_id, count in analytics_dataset.journal_entry_counts.items():
        assert journal_id in journals
        assert journals[journal_id]["entry_count"] == count
        assert journals[journal_id]["total_words"] == analytics_dataset.journal_word_totals[journal_id]


def test_dashboard_combines_all_analytics_sources(
    api_client: JournivApiClient,
    api_user: ApiUser,
    analytics_dataset: AnalyticsSeedData,
):
    """Dashboard should surface each analytics payload and matching summary."""
    dashboard = api_client.request(
        "GET", "/analytics/dashboard", token=api_user.access_token
    ).json()

    assert dashboard["writing_streak"]["total_entries"] == analytics_dataset.total_entries
    assert dashboard["writing_patterns"]["period_days"] == 30
    assert len(dashboard["journals"]["journals"]) >= 2

    summary = dashboard["summary"]
    assert summary["total_entries"] == dashboard["writing_streak"]["total_entries"]
    assert summary["current_streak"] == dashboard["writing_streak"]["current_streak"]
    assert summary["total_journals"] == len(dashboard["journals"]["journals"])
    assert summary["longest_streak"] == dashboard["writing_streak"]["longest_streak"]


def test_analytics_requires_authentication(api_client: JournivApiClient):
    """All analytics endpoints must require a token."""
    assert_requires_authentication(
        api_client,
        [
            EndpointCase("GET", "/analytics/writing-streak"),
            EndpointCase("GET", "/analytics/writing-patterns"),
            EndpointCase("GET", "/analytics/productivity"),
            EndpointCase("GET", "/analytics/journals"),
            EndpointCase("GET", "/analytics/dashboard"),
        ],
    )


def test_writing_patterns_rejects_invalid_days(api_client: JournivApiClient, api_user: ApiUser):
    """Validation errors should propagate cleanly to the caller."""
    response = api_client.request(
        "GET",
        "/analytics/writing-patterns",
        token=api_user.access_token,
        params={"days": 400},
    )
    assert response.status_code == 422
