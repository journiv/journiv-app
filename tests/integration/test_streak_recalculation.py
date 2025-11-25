"""
Integration tests for streak recalculation after entry deletion.
"""
from datetime import date, timedelta

import pytest

from tests.lib import ApiUser, JournivApiClient


def _content_with_words(word_count: int) -> str:
    """Create deterministic entry content with a predictable word count."""
    return " ".join(f"word{idx}" for idx in range(word_count))


def test_case_a_deleting_latest_entry_reduces_streak(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """Case A: Deleting latest entry reduces streak."""
    journal = journal_factory(title="Streak Test Journal")
    token = api_user.access_token

    base_date = date.today()
    entry_date_20 = base_date - timedelta(days=2)
    entry_date_21 = base_date - timedelta(days=1)
    entry_date_22 = base_date

    entry_20 = api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Entry 20",
        content=_content_with_words(10),
        entry_date=entry_date_20.isoformat(),
        entry_timezone="UTC",
    )

    entry_21 = api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Entry 21",
        content=_content_with_words(10),
        entry_date=entry_date_21.isoformat(),
        entry_timezone="UTC",
    )

    entry_22 = api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Entry 22",
        content=_content_with_words(10),
        entry_date=entry_date_22.isoformat(),
        entry_timezone="UTC",
    )

    analytics_before = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_before["current_streak"] == 3

    api_client.delete_entry(token, entry_22["id"])

    analytics_after = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_after["current_streak"] == 2
    assert analytics_after["last_entry_date"] == entry_date_21.isoformat()
    assert analytics_after["streak_start_date"] == entry_date_20.isoformat()


def test_case_b_gaps_break_streak_correctly(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """Case B: Gaps break streak correctly."""
    journal = journal_factory(title="Streak Test Journal")
    token = api_user.access_token

    base_date = date.today()
    entry_date_20 = base_date - timedelta(days=3)
    entry_date_21 = base_date - timedelta(days=2)
    entry_date_23 = base_date

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Entry 20",
        content=_content_with_words(10),
        entry_date=entry_date_20.isoformat(),
        entry_timezone="UTC",
    )

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Entry 21",
        content=_content_with_words(10),
        entry_date=entry_date_21.isoformat(),
        entry_timezone="UTC",
    )

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Entry 23",
        content=_content_with_words(10),
        entry_date=entry_date_23.isoformat(),
        entry_timezone="UTC",
    )

    analytics = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics["current_streak"] == 1
    assert analytics["last_entry_date"] == entry_date_23.isoformat()
    assert analytics["streak_start_date"] == entry_date_23.isoformat()


def test_case_c_deleting_first_day_of_streak_updates_start_date(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """Case C: Deleting first day of streak updates start date."""
    journal = journal_factory(title="Streak Test Journal")
    token = api_user.access_token

    base_date = date.today()
    entry_date_20 = base_date - timedelta(days=2)
    entry_date_21 = base_date - timedelta(days=1)
    entry_date_22 = base_date

    entry_20 = api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Entry 20",
        content=_content_with_words(10),
        entry_date=entry_date_20.isoformat(),
        entry_timezone="UTC",
    )

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Entry 21",
        content=_content_with_words(10),
        entry_date=entry_date_21.isoformat(),
        entry_timezone="UTC",
    )

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Entry 22",
        content=_content_with_words(10),
        entry_date=entry_date_22.isoformat(),
        entry_timezone="UTC",
    )

    analytics_before = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_before["current_streak"] == 3
    assert analytics_before["streak_start_date"] == entry_date_20.isoformat()

    api_client.delete_entry(token, entry_20["id"])

    analytics_after = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_after["current_streak"] == 2
    assert analytics_after["streak_start_date"] == entry_date_21.isoformat()
    assert analytics_after["last_entry_date"] == entry_date_22.isoformat()


def test_case_d_deleting_all_entries_resets_to_zero(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """Case D: Deleting all entries resets to zero/null."""
    journal = journal_factory(title="Streak Test Journal")
    token = api_user.access_token

    base_date = date.today()
    entry_date_20 = base_date - timedelta(days=2)
    entry_date_21 = base_date - timedelta(days=1)

    entry_20 = api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Entry 20",
        content=_content_with_words(10),
        entry_date=entry_date_20.isoformat(),
        entry_timezone="UTC",
    )

    entry_21 = api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Entry 21",
        content=_content_with_words(10),
        entry_date=entry_date_21.isoformat(),
        entry_timezone="UTC",
    )

    analytics_before = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_before["current_streak"] == 2

    api_client.delete_entry(token, entry_20["id"])
    api_client.delete_entry(token, entry_21["id"])

    analytics_after = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_after["current_streak"] == 0
    assert analytics_after["longest_streak"] == 0
    assert analytics_after["last_entry_date"] is None
    assert analytics_after["streak_start_date"] is None


def test_case_e_longest_streak_persists_historically(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """Case E: Longest streak persists historically."""
    journal = journal_factory(title="Streak Test Journal")
    token = api_user.access_token

    base_date = date.today()
    entry_date_1 = base_date - timedelta(days=19)
    entry_date_2 = base_date - timedelta(days=18)
    entry_date_3 = base_date - timedelta(days=17)
    entry_date_10 = base_date - timedelta(days=10)
    entry_date_11 = base_date - timedelta(days=9)
    entry_date_12 = base_date - timedelta(days=8)
    entry_date_13 = base_date - timedelta(days=7)
    entry_date_20 = base_date

    for entry_date in [entry_date_1, entry_date_2, entry_date_3]:
        api_client.create_entry(
            token,
            journal_id=journal["id"],
            title=f"Entry {entry_date.day}",
            content=_content_with_words(10),
            entry_date=entry_date.isoformat(),
            entry_timezone="UTC",
        )

    for entry_date in [entry_date_10, entry_date_11, entry_date_12, entry_date_13]:
        api_client.create_entry(
            token,
            journal_id=journal["id"],
            title=f"Entry {entry_date.day}",
            content=_content_with_words(10),
            entry_date=entry_date.isoformat(),
            entry_timezone="UTC",
        )

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Entry 20",
        content=_content_with_words(10),
        entry_date=entry_date_20.isoformat(),
        entry_timezone="UTC",
    )

    analytics = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics["current_streak"] == 1
    assert analytics["longest_streak"] == 4


def test_case_f_deleting_partial_entries_in_day_does_not_break_streak(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """Case F: Deleting partial entries in a day does NOT break streak."""
    journal = journal_factory(title="Streak Test Journal")
    token = api_user.access_token

    base_date = date.today()
    nov_21 = base_date - timedelta(days=2)
    nov_22 = base_date - timedelta(days=1)
    nov_23 = base_date

    entry_21_1 = api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Nov 21 Entry 1",
        content=_content_with_words(10),
        entry_date=nov_21.isoformat(),
        entry_timezone="UTC",
    )

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Nov 21 Entry 2",
        content=_content_with_words(10),
        entry_date=nov_21.isoformat(),
        entry_timezone="UTC",
    )

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Nov 21 Entry 3",
        content=_content_with_words(10),
        entry_date=nov_21.isoformat(),
        entry_timezone="UTC",
    )

    entry_22_1 = api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Nov 22 Entry 1",
        content=_content_with_words(10),
        entry_date=nov_22.isoformat(),
        entry_timezone="UTC",
    )

    entry_22_2 = api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Nov 22 Entry 2",
        content=_content_with_words(10),
        entry_date=nov_22.isoformat(),
        entry_timezone="UTC",
    )

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Nov 23 Entry 1",
        content=_content_with_words(10),
        entry_date=nov_23.isoformat(),
        entry_timezone="UTC",
    )

    analytics_before = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_before["current_streak"] == 3

    api_client.delete_entry(token, entry_22_1["id"])

    analytics_after = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_after["current_streak"] == 3
    assert analytics_after["streak_start_date"] == nov_21.isoformat()
    assert analytics_after["last_entry_date"] == nov_23.isoformat()


def test_case_g_deleting_all_entries_from_day_breaks_streak(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """Case G: Deleting all entries from a day DOES break streak."""
    journal = journal_factory(title="Streak Test Journal")
    token = api_user.access_token

    base_date = date.today()
    nov_21 = base_date - timedelta(days=2)
    nov_22 = base_date - timedelta(days=1)
    nov_23 = base_date

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Nov 21 Entry 1",
        content=_content_with_words(10),
        entry_date=nov_21.isoformat(),
        entry_timezone="UTC",
    )

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Nov 21 Entry 2",
        content=_content_with_words(10),
        entry_date=nov_21.isoformat(),
        entry_timezone="UTC",
    )

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Nov 21 Entry 3",
        content=_content_with_words(10),
        entry_date=nov_21.isoformat(),
        entry_timezone="UTC",
    )

    entry_22_1 = api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Nov 22 Entry 1",
        content=_content_with_words(10),
        entry_date=nov_22.isoformat(),
        entry_timezone="UTC",
    )

    entry_22_2 = api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Nov 22 Entry 2",
        content=_content_with_words(10),
        entry_date=nov_22.isoformat(),
        entry_timezone="UTC",
    )

    api_client.create_entry(
        token,
        journal_id=journal["id"],
        title="Nov 23 Entry 1",
        content=_content_with_words(10),
        entry_date=nov_23.isoformat(),
        entry_timezone="UTC",
    )

    analytics_before = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_before["current_streak"] == 3

    api_client.delete_entry(token, entry_22_1["id"])
    api_client.delete_entry(token, entry_22_2["id"])

    analytics_after = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_after["current_streak"] == 1
    assert analytics_after["streak_start_date"] == nov_23.isoformat()
    assert analytics_after["last_entry_date"] == nov_23.isoformat()

