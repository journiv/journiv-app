"""
Integration tests for streak recalculation after entry deletion.
"""
from datetime import date, timedelta

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

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry 20",
        content=_content_with_words(10),
        logged_date=entry_date_20.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry 21",
        content=_content_with_words(10),
        logged_date=entry_date_21.isoformat(),
        logged_timezone="UTC",
    )

    entry_22 = api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry 22",
        content=_content_with_words(10),
        logged_date=entry_date_22.isoformat(),
        logged_timezone="UTC",
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

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry 20",
        content=_content_with_words(10),
        logged_date=entry_date_20.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry 21",
        content=_content_with_words(10),
        logged_date=entry_date_21.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry 23",
        content=_content_with_words(10),
        logged_date=entry_date_23.isoformat(),
        logged_timezone="UTC",
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

    entry_20 = api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry 20",
        content=_content_with_words(10),
        logged_date=entry_date_20.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry 21",
        content=_content_with_words(10),
        logged_date=entry_date_21.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry 22",
        content=_content_with_words(10),
        logged_date=entry_date_22.isoformat(),
        logged_timezone="UTC",
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

    entry_20 = api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry 20",
        content=_content_with_words(10),
        logged_date=entry_date_20.isoformat(),
        logged_timezone="UTC",
    )

    entry_21 = api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry 21",
        content=_content_with_words(10),
        logged_date=entry_date_21.isoformat(),
        logged_timezone="UTC",
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

    for logged_date in [entry_date_1, entry_date_2, entry_date_3]:
        api_client.create_entry_with_moment(
            token,
            journal_id=journal["id"],
            title=f"Entry {logged_date.day}",
            content=_content_with_words(10),
            logged_date=logged_date.isoformat(),
            logged_timezone="UTC",
        )

    for logged_date in [entry_date_10, entry_date_11, entry_date_12, entry_date_13]:
        api_client.create_entry_with_moment(
            token,
            journal_id=journal["id"],
            title=f"Entry {logged_date.day}",
            content=_content_with_words(10),
            logged_date=logged_date.isoformat(),
            logged_timezone="UTC",
        )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry 20",
        content=_content_with_words(10),
        logged_date=entry_date_20.isoformat(),
        logged_timezone="UTC",
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

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Nov 21 Entry 1",
        content=_content_with_words(10),
        logged_date=nov_21.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Nov 21 Entry 2",
        content=_content_with_words(10),
        logged_date=nov_21.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Nov 21 Entry 3",
        content=_content_with_words(10),
        logged_date=nov_21.isoformat(),
        logged_timezone="UTC",
    )

    entry_22_1 = api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Nov 22 Entry 1",
        content=_content_with_words(10),
        logged_date=nov_22.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Nov 22 Entry 2",
        content=_content_with_words(10),
        logged_date=nov_22.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Nov 23 Entry 1",
        content=_content_with_words(10),
        logged_date=nov_23.isoformat(),
        logged_timezone="UTC",
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

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Nov 21 Entry 1",
        content=_content_with_words(10),
        logged_date=nov_21.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Nov 21 Entry 2",
        content=_content_with_words(10),
        logged_date=nov_21.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Nov 21 Entry 3",
        content=_content_with_words(10),
        logged_date=nov_21.isoformat(),
        logged_timezone="UTC",
    )

    entry_22_1 = api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Nov 22 Entry 1",
        content=_content_with_words(10),
        logged_date=nov_22.isoformat(),
        logged_timezone="UTC",
    )

    entry_22_2 = api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Nov 22 Entry 2",
        content=_content_with_words(10),
        logged_date=nov_22.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Nov 23 Entry 1",
        content=_content_with_words(10),
        logged_date=nov_23.isoformat(),
        logged_timezone="UTC",
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


def test_case_h_backdating_entry_in_middle_of_streak_maintains_streak(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """Case H: Backdating entry in middle of streak maintains streak."""
    journal = journal_factory(title="Streak Test Journal")
    token = api_user.access_token

    base_date = date.today()
    # Create a 5-day streak
    day_1 = base_date - timedelta(days=4)
    day_2 = base_date - timedelta(days=3)
    day_3 = base_date - timedelta(days=2)
    day_4 = base_date - timedelta(days=1)
    day_5 = base_date

    # Create entries in order
    for idx, logged_date in enumerate([day_1, day_2, day_3, day_4, day_5]):
        api_client.create_entry_with_moment(
            token,
            journal_id=journal["id"],
            title=f"Entry Day {idx + 1}",
            content=_content_with_words(10),
            logged_date=logged_date.isoformat(),
            logged_timezone="UTC",
        )

    analytics_before = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_before["current_streak"] == 5

    # Now backdate an entry to day 3 (already has an entry)
    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Backdated Entry Day 3",
        content=_content_with_words(15),
        logged_date=day_3.isoformat(),
        logged_timezone="UTC",
    )

    analytics_after = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_after["current_streak"] == 5
    assert analytics_after["streak_start_date"] == day_1.isoformat()
    assert analytics_after["last_entry_date"] == day_5.isoformat()


def test_case_i_backdating_entry_to_fill_gap_extends_streak(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """Case I: Backdating entry to fill a gap extends the streak."""
    journal = journal_factory(title="Streak Test Journal")
    token = api_user.access_token

    base_date = date.today()
    # Create entries with a gap
    day_1 = base_date - timedelta(days=4)
    day_2 = base_date - timedelta(days=3)
    # day_3 is missing (gap)
    day_4 = base_date - timedelta(days=1)
    day_5 = base_date

    # Create entries with a gap on day 3
    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry Day 1",
        content=_content_with_words(10),
        logged_date=day_1.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry Day 2",
        content=_content_with_words(10),
        logged_date=day_2.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry Day 4",
        content=_content_with_words(10),
        logged_date=day_4.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry Day 5",
        content=_content_with_words(10),
        logged_date=day_5.isoformat(),
        logged_timezone="UTC",
    )

    analytics_before = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    # Current streak should be 2 (day 4 and day 5)
    assert analytics_before["current_streak"] == 2
    assert analytics_before["longest_streak"] == 2

    # Fill the gap by backdating to day 3
    day_3 = base_date - timedelta(days=2)
    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Backdated Entry Day 3",
        content=_content_with_words(15),
        logged_date=day_3.isoformat(),
        logged_timezone="UTC",
    )

    analytics_after = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    # Now we have a 5-day streak!
    assert analytics_after["current_streak"] == 5
    assert analytics_after["longest_streak"] == 5
    assert analytics_after["streak_start_date"] == day_1.isoformat()
    assert analytics_after["last_entry_date"] == day_5.isoformat()


def test_case_j_backdating_entry_before_current_streak_does_not_affect_it(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """Case J: Backdating entry before current streak does not affect it."""
    journal = journal_factory(title="Streak Test Journal")
    token = api_user.access_token

    base_date = date.today()
    # Create a 3-day streak
    day_3 = base_date - timedelta(days=2)
    day_4 = base_date - timedelta(days=1)
    day_5 = base_date

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry Day 3",
        content=_content_with_words(10),
        logged_date=day_3.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry Day 4",
        content=_content_with_words(10),
        logged_date=day_4.isoformat(),
        logged_timezone="UTC",
    )

    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Entry Day 5",
        content=_content_with_words(10),
        logged_date=day_5.isoformat(),
        logged_timezone="UTC",
    )

    analytics_before = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_before["current_streak"] == 3
    assert analytics_before["streak_start_date"] == day_3.isoformat()

    # Backdate an entry to day 1 (before the streak, with gap)
    day_1 = base_date - timedelta(days=10)
    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Backdated Entry Day 1",
        content=_content_with_words(15),
        logged_date=day_1.isoformat(),
        logged_timezone="UTC",
    )

    analytics_after = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    # Current streak should remain 3
    assert analytics_after["current_streak"] == 3
    assert analytics_after["streak_start_date"] == day_3.isoformat()
    assert analytics_after["last_entry_date"] == day_5.isoformat()


def test_case_k_backdating_far_before_long_streak_preserves_streak(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """Case K: Backdating entry far before a long streak preserves the streak.

    Creates a 10-day consecutive streak, then backdates an entry several weeks prior.
    The current streak should remain intact after backdating.
    """
    journal = journal_factory(title="Streak Test Journal")
    token = api_user.access_token

    # Create a 10-day consecutive streak
    dec_5 = date(2025, 12, 5)
    dec_14 = date(2025, 12, 14)

    # Create entries for the 10-day streak
    current_date = dec_5
    while current_date <= dec_14:
        api_client.create_entry_with_moment(
            token,
            journal_id=journal["id"],
            title=f"Entry {current_date.isoformat()}",
            content=_content_with_words(20),
            logged_date=current_date.isoformat(),
            logged_timezone="Europe/Berlin",
        )
        current_date += timedelta(days=1)

    analytics_before = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    assert analytics_before["current_streak"] == 10
    assert analytics_before["streak_start_date"] == dec_5.isoformat()
    assert analytics_before["last_entry_date"] == dec_14.isoformat()

    # Backdate an entry several weeks before the streak (with gap)
    nov_16 = date(2025, 11, 16)
    api_client.create_entry_with_moment(
        token,
        journal_id=journal["id"],
        title="Backdated Entry",
        content=_content_with_words(25),
        logged_date=nov_16.isoformat(),
        logged_timezone="Europe/Berlin",
    )

    analytics_after = api_client.request(
        "GET", "/analytics/writing-streak", token=token
    ).json()
    # Current streak should remain 10
    assert analytics_after["current_streak"] == 10
    assert analytics_after["streak_start_date"] == dec_5.isoformat()
    assert analytics_after["last_entry_date"] == dec_14.isoformat()
    assert analytics_after["longest_streak"] == 10
