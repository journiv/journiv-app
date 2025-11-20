"""
Behavioural tests that assert cascades through the public API surface.
"""
from datetime import date

from tests.integration.helpers import (
    EndpointCase,
    UNKNOWN_UUID,
    assert_requires_authentication,
    sample_jpeg_bytes,
)
from tests.lib import ApiUser, JournivApiClient


def test_deleting_journal_removes_entries_and_media(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
    entry_factory,
):
    """Deleting a journal should cascade entries and their media."""
    journal = journal_factory(title="Cascade Journal")
    entry_one = entry_factory(journal=journal, title="First entry")
    entry_two = entry_factory(journal=journal, title="Second entry")

    api_client.upload_media(
        api_user.access_token,
        entry_id=entry_one["id"],
        filename="photo.jpg",
        content=sample_jpeg_bytes(),
        content_type="image/jpeg",
    )

    entries_before = api_client.request(
        "GET",
        f"/entries/journal/{journal['id']}",
        token=api_user.access_token,
    ).json()
    assert len(entries_before) >= 2

    api_client.delete_journal(api_user.access_token, journal["id"])

    after_delete = api_client.request(
        "GET",
        f"/entries/journal/{journal['id']}",
        token=api_user.access_token,
    )
    assert after_delete.status_code in (404, 200)
    if after_delete.status_code == 200:
        assert after_delete.json() == []

    # Verify entries are gone
    for entry in (entry_one, entry_two):
        response = api_client.request(
            "GET", f"/entries/{entry['id']}", token=api_user.access_token
        )
        assert response.status_code == 404


def test_deleting_entry_removes_related_artifacts(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Deleting an entry should remove pins, media, and mood logs associated with it."""
    entry = entry_factory(title="Cascade Entry")
    moods = api_client.list_moods(api_user.access_token)
    if moods:
        api_client.create_mood_log(
            api_user.access_token,
            entry_id=entry["id"],
            mood_id=moods[0]["id"],
            logged_date=date.today().isoformat(),
            notes="Cascade mood",
        )

    api_client.upload_media(
        api_user.access_token,
        entry_id=entry["id"],
        filename="entry-media.jpg",
        content=sample_jpeg_bytes(),
        content_type="image/jpeg",
    )

    api_client.pin_entry(api_user.access_token, entry["id"])
    api_client.delete_entry(api_user.access_token, entry["id"])

    mood_logs = api_client.list_mood_logs(api_user.access_token)
    assert all(log["entry_id"] != entry["id"] for log in mood_logs)

    entries = api_client.list_entries(api_user.access_token, limit=50)
    assert all(item["id"] != entry["id"] for item in entries)


def test_cascade_operations_require_auth(api_client: JournivApiClient):
    """Requests that mutate cascading resources must require auth."""
    assert_requires_authentication(
        api_client,
        [
            EndpointCase("DELETE", f"/journals/{UNKNOWN_UUID}"),
            EndpointCase("DELETE", f"/entries/{UNKNOWN_UUID}"),
        ],
    )
