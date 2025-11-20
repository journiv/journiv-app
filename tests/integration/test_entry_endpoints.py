"""
Entry API integration coverage.
"""
from datetime import date, timedelta

from tests.integration.helpers import EndpointCase, UNKNOWN_UUID, assert_requires_authentication
from tests.lib import ApiUser, JournivApiClient


def test_entry_crud_and_pin_flow(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """End-to-end coverage for entry creation, updates, and pinning."""
    journal = journal_factory()
    created = api_client.create_entry(
        api_user.access_token,
        journal_id=journal["id"],
        title="My first entry",
        content="Writing something meaningful.",
        entry_date=date.today().isoformat(),
        location="Home",
        weather="Sunny",
    )

    entry_id = created["id"]
    assert created["journal_id"] == journal["id"]
    assert created["location"] == "Home"
    assert created["weather"] == "Sunny"

    fetched = api_client.get_entry(api_user.access_token, entry_id)
    assert fetched["title"] == "My first entry"

    updated = api_client.update_entry(
        api_user.access_token,
        entry_id,
        {"title": "Updated title", "content": "Updated content", "location": "Office"},
    )
    assert updated["title"] == "Updated title"
    assert updated["location"] == "Office"

    pinned = api_client.pin_entry(api_user.access_token, entry_id)
    assert pinned["is_pinned"] is True

    unpinned = api_client.unpin_entry(api_user.access_token, entry_id)
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


def test_update_entry_adjusts_metadata(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Updating entry content/date should recalculate metadata fields."""
    entry = entry_factory(title="Original title", content="Original body text")
    new_date = (date.today() - timedelta(days=3)).isoformat()
    payload = {
        "title": "Edited title",
        "content": "This entry has four words.",
        "entry_date": new_date,
        "weather": "Rainy",
    }

    updated = api_client.update_entry(api_user.access_token, entry["id"], payload)
    assert updated["title"] == "Edited title"
    assert updated["entry_date"] == new_date
    assert updated["weather"] == "Rainy"
    assert updated["word_count"] == 5


def test_update_entry_cannot_change_journal(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
    entry_factory,
):
    """Updating an entry with a new journal_id should keep it with the original journal."""
    source_journal = journal_factory(title="Source Journal")
    target_journal = journal_factory(title="Target Journal")
    entry = entry_factory(journal=source_journal)

    response = api_client.request(
        "PUT",
        f"/entries/{entry['id']}",
        token=api_user.access_token,
        json={"journal_id": target_journal["id"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["journal_id"] == source_journal["id"]

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
        entry_date=(today - timedelta(days=5)).isoformat(),
    )
    target = entry_factory(
        journal=journal,
        title="Unique Tracker",
        content="Contains UniqueSearchToken for lookup",
        entry_date=(today - timedelta(days=2)).isoformat(),
    )
    later = entry_factory(
        journal=journal,
        title="Weekend Recap",
        content="Relaxed weekend activities",
        entry_date=(today - timedelta(days=1)).isoformat(),
    )

    search_response = api_client.request(
        "GET",
        "/entries/search",
        token=api_user.access_token,
        params={"q": "UniqueSearchToken"},
    ).json()
    search_items = (
        search_response["items"]
        if isinstance(search_response, dict) and "items" in search_response
        else search_response
    )
    assert {entry["id"] for entry in search_items} == {target["id"]}

    date_range = api_client.request(
        "GET",
        "/entries/date-range",
        token=api_user.access_token,
        params={
            "start_date": (today - timedelta(days=3)).isoformat(),
            "end_date": today.isoformat(),
            "journal_id": journal["id"],
        },
    ).json()
    returned_ids = {entry["id"] for entry in date_range}
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

    api_client.pin_entry(api_user.access_token, pinned_entry["id"])

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
                    "entry_date": today,
                },
            ),
            EndpointCase("GET", "/entries/search", params={"q": "test"}),
            EndpointCase(
                "GET",
                "/entries/date-range",
                params={"start_date": today, "end_date": today},
            ),
        ],
    )
