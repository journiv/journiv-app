"""
Moment-Entry Lifecycle Integration Tests.
"""
from datetime import date
import pytest

from tests.lib import ApiUser, JournivApiClient
from tests.integration.helpers import sample_jpeg_bytes


def test_cascade_deletion(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
    moment_factory,
):
    """Deleting a Moment should cascade delete its Entry."""
    journal = journal_factory()

    # Create moment with entry
    moment = moment_factory(
        entry={
            "title": "Cascade Test",
            "content": "This entry should be deleted.",
            "journal_id": journal["id"],
        }
    )
    moment_id = moment["id"]
    entry_id = moment["entry"]["id"]

    # Verify both exist
    assert api_client.request("GET", f"/moments/{moment_id}", token=api_user.access_token).status_code == 200
    assert api_client.request("GET", f"/entries/{entry_id}", token=api_user.access_token).status_code == 200

    # Delete moment
    api_client.request("DELETE", f"/moments/{moment_id}", token=api_user.access_token, expected=(204,))

    # Verify both are gone
    assert api_client.request("GET", f"/moments/{moment_id}", token=api_user.access_token).status_code == 404
    assert api_client.request("GET", f"/entries/{entry_id}", token=api_user.access_token).status_code == 404


def test_revert_to_quick_log(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
    moment_factory,
):
    """Deleting an Entry should NOT delete the Moment (Revert to Quick Log)."""
    journal = journal_factory()

    # Create moment with entry
    moment = moment_factory(
        entry={
            "title": "Revert Test",
            "content": "Delete this entry, keep moment.",
            "journal_id": journal["id"],
        },
        note="This note should persist",
    )
    moment_id = moment["id"]
    entry_id = moment["entry"]["id"]

    # Delete entry
    api_client.request("DELETE", f"/entries/{entry_id}", token=api_user.access_token, expected=(204,))

    # Verify entry is gone but moment persists
    assert api_client.request("GET", f"/entries/{entry_id}", token=api_user.access_token).status_code == 404

    persisted_moment = api_client.request("GET", f"/moments/{moment_id}", token=api_user.access_token).json()
    assert persisted_moment["id"] == moment_id
    assert persisted_moment["note"] == "This note should persist"
    assert persisted_moment["entry"] is None


def test_smart_default_creation(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    """
    Creating a moment with 'entry' field creates both.
    Creating a moment without 'entry' field creates moment only.
    """
    journal = journal_factory()

    # 1. With entry text -> Moment + Entry
    response_with_entry = api_client.create_moment(
        api_user.access_token,
        entry={
            "title": "Smart Default Entry",
            "content": "Has text.",
            "journal_id": journal["id"],
        },
        note="Attached note"
    )
    assert response_with_entry["entry"] is not None
    assert response_with_entry["entry"]["title"] == "Smart Default Entry"
    assert response_with_entry["note"] == "Attached note"

    # 2. Without entry text -> Moment Only
    response_moment_only = api_client.create_moment(
        api_user.access_token,
        note="Just a note, no entry",
        # No 'entry' dictionary passed
    )
    assert response_moment_only["entry"] is None
    assert response_moment_only["note"] == "Just a note, no entry"


def test_revert_to_quick_log_preserves_context(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
    journal_factory,
):
    """
    Regression Test:
    Deleting an Entry should preserve associated Context (Mood, Activity, Media).
    """
    # 0. Create Journal
    journal = journal_factory()

    # 1. Setup Context: Mood, Activity
    mood = api_client.create_mood(api_user.access_token, name="TestMood", icon="🧪")
    response = api_client.request(
        "POST", "/activities", token=api_user.access_token, json={"name": "Running", "icon": "🏃"}
    )
    assert response.status_code in (200, 201)
    activity = response.json()

    # 2. Create Detailed Entry with Context
    moment = moment_factory(
        entry={
            "title": "Rich Entry",
            "content": "Has deep context.",
            "journal_id": journal["id"],
        },
        primary_mood_id=mood["id"],
        mood_activity=[{"mood_id": mood["id"], "activity_id": activity["id"]}], # Mood + Activity together
    )
    moment_id = moment["id"]
    entry_id = moment["entry"]["id"]

    # 3. Add Media
    api_client.upload_media(
        api_user.access_token,
        moment_id=moment_id,
        filename="context.jpg",
        content=sample_jpeg_bytes(),
        content_type="image/jpeg",
    )

    # 4. Verify Initial State
    initial_moment = api_client.request("GET", f"/moments/{moment_id}", token=api_user.access_token).json()
    assert initial_moment["entry"]["id"] == entry_id
    assert initial_moment["primary_mood_id"] == mood["id"]
    assert initial_moment["media_count"] == 1

    # 5. Delete Entry
    api_client.request("DELETE", f"/entries/{entry_id}", token=api_user.access_token, expected=(204,))

    # 6. Verify Entry is Gone
    api_client.request("GET", f"/entries/{entry_id}", token=api_user.access_token, expected=(404,))

    # 7. Verify Moment Persists with Context
    final_moment = api_client.request("GET", f"/moments/{moment_id}", token=api_user.access_token).json()
    assert final_moment["id"] == moment_id
    assert final_moment["entry"] is None
    assert final_moment["primary_mood_id"] == mood["id"], "Mood should persist"
    assert final_moment["media_count"] == 1, "Media should persist"
    assert "mood_activity" in final_moment, "mood_activity should be present in moment response"
    has_activity = False
    for ma in final_moment["mood_activity"]:
        act = ma.get("activity")
        if act and act.get("id") == activity["id"]:
            has_activity = True
            break
    assert has_activity, "Activity should persist"
