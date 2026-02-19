"""
Entry API integration coverage.
"""
from datetime import date, timedelta

from tests.integration.helpers import (
    UNKNOWN_UUID,
    EndpointCase,
    assert_requires_authentication,
)
from tests.lib import ApiUser, JournivApiClient


def test_entry_crud_and_pin_flow(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """End-to-end coverage for entry creation, updates, and pinning."""
    journal = journal_factory()
    created = api_client.create_entry_with_moment(
        api_user.access_token,
        journal_id=journal["id"],
        title="My first entry",
        content="Writing something meaningful.",
        logged_date=date.today().isoformat(),
        location_json={"name": "Home"},
        weather_json={"condition": "Sunny", "temp_c": 21.0},
        weather_summary="Sunny",
    )

    entry_id = created["id"]
    moment_id = created["moment_id"]
    assert created["journal_id"] == journal["id"]

    # Metadata is now on the moment
    moment = api_client.request(
        "GET",
        f"/moments/{moment_id}",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    assert moment["location_json"]["name"] == "Home"
    assert moment["weather_json"]["condition"] == "Sunny"
    assert moment["weather_summary"] == "Sunny"

    fetched = api_client.get_entry(api_user.access_token, entry_id)
    assert fetched["title"] == "My first entry"

    updated = api_client.update_entry(
        api_user.access_token,
        entry_id,
        {
            "title": "Updated title",
            "content": "Updated content",
        },
    )
    assert updated["title"] == "Updated title"

    # Verify moment metadata is preserved/independent
    updated_moment = api_client.update_moment(
        api_user.access_token,
        moment_id,
        {
            "location_json": {"name": "Office"},
        }
    )
    assert updated_moment["location_json"]["name"] == "Office"

    pinned = api_client.pin_moment(api_user.access_token, moment_id)
    assert pinned["is_pinned"] is True

    unpinned = api_client.unpin_moment(api_user.access_token, moment_id)
    assert unpinned["is_pinned"] is False

    api_client.delete_entry(api_user.access_token, entry_id)
    deleted = api_client.request(
        "GET", f"/entries/{entry_id}", token=api_user.access_token
    )
    assert deleted.status_code == 404


def test_entry_listing_supports_pagination(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """User entry listing honors limit/offset parameters."""
    entry_factory()
    entry_factory()
    first_page = api_client.list_entries(api_user.access_token, limit=1)
    second_page = api_client.list_entries(api_user.access_token, limit=1, offset=1)
    assert len(first_page) == 1
    assert len(second_page) == 1
    assert first_page[0]["id"] != second_page[0]["id"]


def test_update_moment_adjusts_metadata(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Updating moment metadata."""
    entry = entry_factory(title="Original title", content="Original body text")
    moment_id = entry["moment_id"]

    new_date = (date.today() - timedelta(days=3)).isoformat()
    payload = {
        "logged_date_tz": new_date,
        "weather_json": {"condition": "Rainy", "temp_c": 18.0},
        "weather_summary": "Rainy",
    }

    updated = api_client.update_moment(api_user.access_token, moment_id, payload)
    assert updated["logged_date_tz"] == new_date
    assert updated["weather_json"]["condition"] == "Rainy"
    assert updated["weather_summary"] == "Rainy"


def test_update_entry_can_change_journal(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
    entry_factory,
):
    """Updating an entry with a new journal_id should move it to the target journal."""
    source_journal = journal_factory(title="Source Journal")
    target_journal = journal_factory(title="Target Journal")
    entry = entry_factory(journal=source_journal, content="Test entry with five words here")

    response = api_client.request(
        "PUT",
        f"/entries/{entry['id']}",
        token=api_user.access_token,
        json={"journal_id": target_journal["id"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["journal_id"] == target_journal["id"]

    # Verify the entry was moved by fetching it again
    fetched = api_client.get_entry(api_user.access_token, entry["id"])
    assert fetched["journal_id"] == target_journal["id"]


def test_journal_stats_update_when_entry_moves_between_journals(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
    entry_factory,
):
    """When an entry is moved between journals, both journal stats should update correctly."""
    source_journal = journal_factory(title="Source Journal")
    target_journal = journal_factory(title="Target Journal")

    # Create entries in source journal with known word counts
    entry1 = entry_factory(
        journal=source_journal,
        title="Entry One",
        content="This entry has exactly five words"  # 6 words
    )
    entry_factory(
        journal=source_journal,
        title="Entry Two",
        content="Another test entry with more words here"  # 7 words
    )

    # Create one entry in target journal
    entry_factory(
        journal=target_journal,
        title="Target Entry",
        content="Initial target journal entry"  # 4 words
    )

    # Get initial journal stats
    source_journal_initial = api_client.request(
        "GET",
        f"/journals/{source_journal['id']}",
        token=api_user.access_token,
    ).json()

    target_journal_initial = api_client.request(
        "GET",
        f"/journals/{target_journal['id']}",
        token=api_user.access_token,
    ).json()

    # Verify initial state
    assert source_journal_initial["entry_count"] == 2
    assert target_journal_initial["entry_count"] == 1

    # Get the word count of the entry we're about to move
    entry_to_move = api_client.get_entry(api_user.access_token, entry1["id"])
    moved_entry_word_count = entry_to_move["word_count"]

    # Move entry1 from source to target journal
    api_client.update_entry(
        api_user.access_token,
        entry1["id"],
        {"journal_id": target_journal["id"]},
    )

    # Get updated journal stats
    source_journal_after = api_client.request(
        "GET",
        f"/journals/{source_journal['id']}",
        token=api_user.access_token,
    ).json()

    target_journal_after = api_client.request(
        "GET",
        f"/journals/{target_journal['id']}",
        token=api_user.access_token,
    ).json()

    # Verify source journal stats decreased
    assert source_journal_after["entry_count"] == source_journal_initial["entry_count"] - 1
    assert source_journal_after["entry_count"] == 1
    assert source_journal_after["total_words"] == source_journal_initial["total_words"] - moved_entry_word_count

    # Verify target journal stats increased
    assert target_journal_after["entry_count"] == target_journal_initial["entry_count"] + 1
    assert target_journal_after["entry_count"] == 2
    assert target_journal_after["total_words"] == target_journal_initial["total_words"] + moved_entry_word_count

    # Verify the moved entry still has the same word count
    entry_after_move = api_client.get_entry(api_user.access_token, entry1["id"])
    assert entry_after_move["word_count"] == moved_entry_word_count


def test_cannot_move_entry_to_archived_journal(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
    entry_factory,
):
    """Moving an entry to an archived journal should fail with appropriate error."""
    source_journal = journal_factory(title="Source Journal")
    target_journal = journal_factory(title="Target Journal")
    entry = entry_factory(journal=source_journal)

    # Archive the target journal
    api_client.archive_journal(api_user.access_token, target_journal["id"])

    response = api_client.request(
        "PUT",
        f"/entries/{entry['id']}",
        token=api_user.access_token,
        json={"journal_id": target_journal["id"]},
    )

    assert response.status_code == 422

    # Verify entry stayed in source journal
    fetched = api_client.get_entry(api_user.access_token, entry["id"])
    assert fetched["journal_id"] == source_journal["id"]


def test_entry_search_and_date_range_filters(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
    entry_factory,
):
    """Search and date range endpoints should return deterministic subsets."""
    journal = journal_factory(title="Filter Journal")
    today = date.today()

    earlier = entry_factory(
        journal=journal,
        title="Weekly Review",
        content="Reflecting on goals and gratitude",
        logged_date=(today - timedelta(days=5)).isoformat(),
    )
    target = entry_factory(
        journal=journal,
        title="Unique Tracker",
        content="Contains UniqueSearchToken for lookup",
        logged_date=(today - timedelta(days=2)).isoformat(),
    )
    later = entry_factory(
        journal=journal,
        title="Weekend Recap",
        content="Relaxed weekend activities",
        logged_date=(today - timedelta(days=1)).isoformat(),
    )

    search_response = api_client.request(
        "GET",
        "/moments",
        token=api_user.access_token,
        params={"search": "UniqueSearchToken"},
    ).json()
    search_items = search_response["items"] if isinstance(search_response, dict) else []
    search_entry_ids = {
        item["entry"]["id"]
        for item in search_items
        if isinstance(item, dict) and item.get("entry")
    }
    assert search_entry_ids == {target["id"]}

    date_range = api_client.request(
        "GET",
        "/moments",
        token=api_user.access_token,
        params={
            "start_date": (today - timedelta(days=3)).isoformat(),
            "end_date": today.isoformat(),
            "journal_id": journal["id"],
        },
    ).json()
    date_items = date_range["items"] if isinstance(date_range, dict) else []
    returned_ids = {
        item["entry"]["id"]
        for item in date_items
        if isinstance(item, dict) and item.get("entry")
    }
    assert target["id"] in returned_ids
    assert later["id"] in returned_ids
    assert earlier["id"] not in returned_ids


def test_journal_listing_respects_pinned_flag(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
    entry_factory,
):
    """Journal-specific listing should surface pinned entries first and filter when requested."""
    journal = journal_factory(title="Pinned Journal")
    first_entry = entry_factory(journal=journal, title="First entry")
    pinned_entry = entry_factory(journal=journal, title="Pinned entry")

    api_client.pin_moment(api_user.access_token, pinned_entry["moment_id"])

    with_pinned = api_client.request(
        "GET",
        f"/entries/journal/{journal['id']}",
        token=api_user.access_token,
        params={"include_pinned": True},
    ).json()
    assert with_pinned[0]["id"] == pinned_entry["id"]
    assert any(entry["id"] == first_entry["id"] for entry in with_pinned)

    without_pinned = api_client.request(
        "GET",
        f"/entries/journal/{journal['id']}",
        token=api_user.access_token,
        params={"include_pinned": False},
    ).json()
    assert all(entry["id"] != pinned_entry["id"] for entry in without_pinned)


def test_entry_endpoints_require_auth(api_client: JournivApiClient):
    """Endpoints must reject anonymous callers."""
    today = date.today().isoformat()
    assert_requires_authentication(
        api_client,
        [
            EndpointCase("GET", "/entries/"),
            EndpointCase(
                "POST",
                "/entries/",
                json={
                    "title": "Unauthorized",
                    "content": "No token sent",
                    "journal_id": UNKNOWN_UUID,
                    "logged_date": today,
                },
            ),
            EndpointCase("GET", "/moments", params={"search": "test"}),
            EndpointCase(
                "GET",
                "/moments",
                params={"start_date": today, "end_date": today},
            ),
        ],
    )
