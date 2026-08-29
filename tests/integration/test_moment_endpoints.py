"""
Moment API integration coverage.
"""
import calendar
from datetime import datetime, timedelta, timezone

from tests.integration.helpers import sample_jpeg_bytes
from tests.lib import ApiUser, JournivApiClient


def test_moment_listing_supports_mood_filtering(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    """Moments can be filtered by specific mood IDs."""
    # Create moods
    happy_mood = api_client.create_mood(api_user.access_token, name="Happy", icon="😊")
    sad_mood = api_client.create_mood(api_user.access_token, name="Sad", icon="😢")

    # Create moments with different moods
    happy_moment = moment_factory(
        primary_mood_id=happy_mood["id"],
        note="Feeling good",
        mood_activity=[{"mood_id": happy_mood["id"]}],
    )
    sad_moment = moment_factory(
        primary_mood_id=sad_mood["id"],
        note="Feeling down",
        mood_activity=[{"mood_id": sad_mood["id"]}],
    )
    neutral_moment = moment_factory(note="Neutral")  # No mood

    # Filter by Happy mood
    happy_results = api_client.list_moments(
        api_user.access_token, mood_ids=[happy_mood["id"]]
    )
    happy_ids = {m["id"] for m in happy_results}

    assert happy_moment["id"] in happy_ids
    assert sad_moment["id"] not in happy_ids
    assert neutral_moment["id"] not in happy_ids

    # Filter by Sad mood
    sad_results = api_client.list_moments(
        api_user.access_token, mood_ids=[sad_mood["id"]]
    )
    sad_ids = {m["id"] for m in sad_results}

    assert sad_moment["id"] in sad_ids
    assert happy_moment["id"] not in sad_ids


def test_moment_listing_supports_multiple_mood_filters(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    """Moments can be filtered by a list of mood IDs (OR logic)."""
    mood1 = api_client.create_mood(api_user.access_token, name="Mood1")
    mood2 = api_client.create_mood(api_user.access_token, name="Mood2")
    mood3 = api_client.create_mood(api_user.access_token, name="Mood3")

    m1 = moment_factory(
        primary_mood_id=mood1["id"],
        mood_activity=[{"mood_id": mood1["id"]}],
    )
    m2 = moment_factory(
        primary_mood_id=mood2["id"],
        mood_activity=[{"mood_id": mood2["id"]}],
    )
    m3 = moment_factory(
        primary_mood_id=mood3["id"],
        mood_activity=[{"mood_id": mood3["id"]}],
    )

    # Filter by Mood1 OR Mood2
    results = api_client.list_moments(
        api_user.access_token, mood_ids=[mood1["id"], mood2["id"]]
    )
    result_ids = {m["id"] for m in results}

    assert m1["id"] in result_ids
    assert m2["id"] in result_ids
    assert m3["id"] not in result_ids


def test_moment_search_by_note(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    """Search should find moments by matching text in the note."""
    target_moment = moment_factory(note="This includes a UniqueKeyword for search")
    other_moment = moment_factory(note="Just a normal note")

    results = api_client.list_moments(api_user.access_token, search="UniqueKeyword")
    result_ids = {m["id"] for m in results}

    assert target_moment["id"] in result_ids
    assert other_moment["id"] not in result_ids


def test_moment_search_by_entry_content(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
    entry_factory,
):
    """Search should find moments linked to entries with matching content."""
    entry = entry_factory(content="Entry content with HiddenTreasure inside")

    # Find the moment associated with the entry
    moments = api_client.list_moments(api_user.access_token)
    entry_moment = next((m for m in moments if (m.get("entry") or {}).get("id") == entry["id"]), None)

    assert entry_moment is not None, "Entry creation should have created a moment"

    results = api_client.list_moments(api_user.access_token, search="HiddenTreasure")
    result_ids = {m["id"] for m in results}

    assert entry_moment["id"] in result_ids


def test_moment_search_by_entry_title(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Search should find moments linked to entries with matching title."""
    entry = entry_factory(title="My Secret Title")

    # Find the auto-created moment
    moments = api_client.list_moments(api_user.access_token)
    entry_moment = next((m for m in moments if (m.get("entry") or {}).get("id") == entry["id"]), None)
    assert entry_moment is not None

    results = api_client.list_moments(api_user.access_token, search="Secret Title")
    result_ids = {m["id"] for m in results}

    assert entry_moment["id"] in result_ids


def test_moment_search_combined_with_mood(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
    entry_factory,
):
    """Search and mood filters can be combined."""
    mood = api_client.create_mood(api_user.access_token, name="Focus")

    # Match: Correct Mood + Correct Text
    match = moment_factory(
        primary_mood_id=mood["id"], note="Working on ImportantProject"
    )

    # Mismatch: Correct Mood + Wrong Text
    wrong_text = moment_factory(primary_mood_id=mood["id"], note="Just chilling")

    # Mismatch: Wrong Mood + Correct Text
    wrong_mood = moment_factory(note="Thinking about ImportantProject")

    results = api_client.list_moments(
        api_user.access_token, search="ImportantProject", mood_ids=[mood["id"]]
    )
    result_ids = {m["id"] for m in results}

    assert match["id"] in result_ids
    assert wrong_text["id"] not in result_ids
    assert wrong_mood["id"] not in result_ids


def test_moment_listing_supports_empty_mood_list(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    """Passing an empty list for mood_ids should result in NO filtering (return all)."""
    m1 = moment_factory(note="Moment 1")
    m2 = moment_factory(note="Moment 2")

    results = api_client.list_moments(
        api_user.access_token,
        mood_ids=[],  # Empty list
    )
    result_ids = {m["id"] for m in results}

    assert m1["id"] in result_ids
    assert m2["id"] in result_ids


def test_moment_listing_supports_tag_filtering(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    """Moments can be filtered to those carrying a given tag."""
    tagged = moment_factory(note="Tagged moment")
    untagged = moment_factory(note="Untagged moment")

    tags = api_client.request(
        "POST",
        f"/moments/{tagged['id']}/tags",
        token=api_user.access_token,
        json=["hiking"],
        expected=(200, 201),
    ).json()
    tag_id = tags[0]["id"]

    results = api_client.list_moments(api_user.access_token, tag_ids=[tag_id])
    result_ids = {m["id"] for m in results}

    assert tagged["id"] in result_ids
    assert untagged["id"] not in result_ids


def test_moment_listing_supports_activity_filtering(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    """Moments can be filtered to those logging a given activity."""
    activity = api_client.create_activity(api_user.access_token, name="Running")
    with_activity = moment_factory(
        note="Went running",
        mood_activity=[{"activity_id": activity["id"]}],
    )
    without_activity = moment_factory(note="Sat still")

    results = api_client.list_moments(
        api_user.access_token, activity_ids=[activity["id"]]
    )
    result_ids = {m["id"] for m in results}

    assert with_activity["id"] in result_ids
    assert without_activity["id"] not in result_ids


def test_moment_media_count_tracks_upload_and_delete(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    moment = moment_factory(note="With media")

    uploaded = api_client.upload_media(
        api_user.access_token,
        moment_id=moment["id"],
        filename="moment.jpg",
        content=sample_jpeg_bytes(),
        content_type="image/jpeg",
        alt_text="count me",
    )
    media_id = uploaded["id"]

    with_media = api_client.request(
        "GET",
        f"/moments/{moment['id']}",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    assert with_media["media_count"] >= 1

    api_client.request(
        "DELETE",
        f"/media/{media_id}",
        token=api_user.access_token,
        expected=(200,),
    )

    without_media = api_client.request(
        "GET",
        f"/moments/{moment['id']}",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    assert without_media["media_count"] == 0


def test_moment_response_includes_completed_goals_for_activity_driven_goal(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    activity = api_client.create_activity(api_user.access_token, name="Walk")
    goal = api_client.create_goal(
        api_user.access_token,
        title="Walk once daily",
        goal_type="achieve",
        frequency_type="daily",
        target_count=1,
        activity_id=activity["id"],
    )

    moment = api_client.create_moment(
        api_user.access_token,
        mood_activity=[{"activity_id": activity["id"]}],
        note="Walked today",
    )
    fetched = api_client.request(
        "GET",
        f"/moments/{moment['id']}",
        token=api_user.access_token,
        expected=(200,),
    ).json()

    completed_goals = fetched.get("completed_goals") or []
    assert any(item["goal_id"] == goal["id"] for item in completed_goals)


def test_moment_memories_endpoint_uses_auto_fallback_order(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    today = datetime.now(timezone.utc).date()

    # Last-years memory (highest auto priority)
    last_year_day = calendar.monthrange(today.year - 1, today.month)[1]
    last_year = today.replace(year=today.year - 1, day=min(today.day, last_year_day))
    yearly_memory = moment_factory(
        logged_date=last_year.isoformat(),
        logged_timezone="UTC",
        note="Yearly memory",
    )

    # Last-week memory (should be ignored when yearly exists)
    last_week = today - timedelta(days=3)
    moment_factory(
        logged_date=last_week.isoformat(),
        logged_timezone="UTC",
        note="Weekly memory",
    )

    response = api_client.request(
        "GET",
        "/moments/memories",
        token=api_user.access_token,
        params={"limit": 10},
        expected=(200,),
    ).json()

    assert response["requested_filter"] == "auto"
    assert response["applied_filter"] == "last_years"
    returned_ids = {item["id"] for item in response["items"]}
    assert yearly_memory["id"] in returned_ids


def test_moment_memories_endpoint_supports_explicit_last_month_filter(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    today = datetime.now(timezone.utc).date()
    previous_month_end = today.replace(day=1) - timedelta(days=1)
    previous_month_last_day = calendar.monthrange(previous_month_end.year, previous_month_end.month)[1]
    previous_month_date = previous_month_end.replace(day=min(today.day, previous_month_last_day))

    month_memory = moment_factory(
        logged_date=previous_month_date.isoformat(),
        logged_timezone="UTC",
        note="Previous month memory",
    )

    # Noise that should not appear with explicit filter (current month, never last month)
    noise_moment = moment_factory(
        logged_date=today.isoformat(),
        logged_timezone="UTC",
        note="Current month noise",
    )

    response = api_client.request(
        "GET",
        "/moments/memories",
        token=api_user.access_token,
        params={"filter": "last_month", "limit": 10},
        expected=(200,),
    ).json()

    assert response["requested_filter"] == "last_month"
    assert response["applied_filter"] == "last_month"
    returned_ids = {item["id"] for item in response["items"]}
    assert month_memory["id"] in returned_ids
    assert noise_moment["id"] not in returned_ids


def test_moment_memories_endpoint_supports_explicit_last_year_filter(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    today = datetime.now(timezone.utc).date()
    previous_year_date = today.replace(year=today.year - 1, day=1)
    previous_year_memory = moment_factory(
        logged_date=previous_year_date.isoformat(),
        logged_timezone="UTC",
        note="Previous year memory",
    )
    noise_memory = moment_factory(
        logged_date=today.isoformat(),
        logged_timezone="UTC",
        note="Current year noise",
    )

    response = api_client.request(
        "GET",
        "/moments/memories",
        token=api_user.access_token,
        params={"filter": "last_year", "limit": 20},
        expected=(200,),
    ).json()

    assert response["requested_filter"] == "last_year"
    assert response["applied_filter"] == "last_year"
    returned_ids = {item["id"] for item in response["items"]}
    assert previous_year_memory["id"] in returned_ids
    assert noise_memory["id"] not in returned_ids


def test_moment_calendar_filters_by_journal_and_reports_counts(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """The calendar summary can be scoped to one journal and counts per day."""
    journal_a = journal_factory(title="Journal A")
    journal_b = journal_factory(title="Journal B")

    # Two moments on the same day in journal A, one on another day in journal B.
    api_client.create_entry_with_moment(
        api_user.access_token,
        journal_id=journal_a["id"],
        title="A morning",
        content="first",
        logged_date_tz="2026-03-10",
        logged_timezone="UTC",
    )
    api_client.create_entry_with_moment(
        api_user.access_token,
        journal_id=journal_a["id"],
        title="A evening",
        content="second",
        logged_date_tz="2026-03-10",
        logged_timezone="UTC",
    )
    api_client.create_entry_with_moment(
        api_user.access_token,
        journal_id=journal_b["id"],
        title="B day",
        content="third",
        logged_date_tz="2026-03-12",
        logged_timezone="UTC",
    )

    params = {"start_date": "2026-03-01", "end_date": "2026-03-31"}

    unscoped = api_client.request(
        "GET", "/moments/calendar", token=api_user.access_token,
        params=params, expected=(200,),
    ).json()
    by_day = {item["logged_date_tz"]: item for item in unscoped}
    assert by_day["2026-03-10"]["moment_count"] == 2
    assert by_day["2026-03-12"]["moment_count"] == 1
    # No media attached, so every day reports a null thumbnail.
    assert by_day["2026-03-10"]["thumbnail_url"] is None

    scoped = api_client.request(
        "GET", "/moments/calendar", token=api_user.access_token,
        params={**params, "journal_id": journal_a["id"]}, expected=(200,),
    ).json()
    scoped_days = {item["logged_date_tz"]: item["moment_count"] for item in scoped}
    assert scoped_days == {"2026-03-10": 2}


def test_moment_calendar_requires_auth(api_client: JournivApiClient):
    api_client.request("GET", "/moments/calendar", expected=(401,))
