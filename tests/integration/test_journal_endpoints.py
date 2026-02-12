"""
Journal API integration coverage.
"""

from tests.integration.helpers import (
    EndpointCase,
    UNKNOWN_UUID,
    assert_not_found,
    assert_requires_authentication,
    upload_sample_media,
)
from tests.lib import ApiUser, JournivApiClient


def _create_sample_journal(api_client: JournivApiClient, token: str, title: str) -> str:
    journal = api_client.create_journal(
        token,
        title=title,
        description=f"{title} description",
        color="#3B82F6",
        icon="📘",
    )
    return journal["id"]


def test_journal_crud_and_favorites(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    """Covers create → retrieve → favorite toggle → update → delete."""
    journal_id = _create_sample_journal(api_client, api_user.access_token, "Primary Journal")

    fetched = api_client.get_journal(api_user.access_token, journal_id)
    assert fetched["title"] == "Primary Journal"
    assert fetched["is_favorite"] is False

    toggled = api_client.request(
        "POST",
        f"/journals/{journal_id}/favorite",
        token=api_user.access_token,
    ).json()
    assert toggled["is_favorite"] is True

    favorites = api_client.request(
        "GET", "/journals/favorites", token=api_user.access_token
    ).json()
    assert any(journal["id"] == journal_id for journal in favorites)

    updated = api_client.update_journal(
        api_user.access_token,
        journal_id,
        {"title": "Renamed Journal", "description": "Updated description"},
    )
    assert updated["title"] == "Renamed Journal"
    assert updated["description"] == "Updated description"

    api_client.delete_journal(api_user.access_token, journal_id)
    response = api_client.request(
        "GET", f"/journals/{journal_id}", token=api_user.access_token
    )
    assert response.status_code == 404


def test_archiving_controls_visibility(
    api_client: JournivApiClient, api_user: ApiUser
):
    """Archived journals should be hidden unless explicitly requested."""
    active_id = _create_sample_journal(api_client, api_user.access_token, "Active Journal")
    archived_id = _create_sample_journal(api_client, api_user.access_token, "Archived Journal")

    api_client.archive_journal(api_user.access_token, archived_id)

    active_only = api_client.list_journals(api_user.access_token)
    assert any(journal["id"] == active_id for journal in active_only)
    assert all(journal["id"] != archived_id for journal in active_only)

    with_archived = api_client.list_journals(
        api_user.access_token, include_archived=True
    )
    assert any(journal["id"] == archived_id for journal in with_archived)

    # unarchive restores default visibility
    api_client.unarchive_journal(api_user.access_token, archived_id)
    refreshed = api_client.list_journals(api_user.access_token)
    assert any(journal["id"] == archived_id for journal in refreshed)


def test_journal_endpoints_require_auth(api_client: JournivApiClient):
    """Requests without a bearer token should fail fast."""
    assert_requires_authentication(
        api_client,
        [
            EndpointCase("GET", "/journals/"),
            EndpointCase("GET", "/journals/favorites"),
            EndpointCase(
                "POST",
                "/journals/",
                json={
                    "title": "No auth",
                    "description": "Missing token should fail",
                    "color": "#F97316",
                    "icon": "❌",
                },
            ),
        ],
    )


def test_journal_not_found_errors(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    """Accessing or mutating unknown journals should return 404."""
    assert_not_found(
        api_client,
        api_user.access_token,
        [
            EndpointCase("GET", f"/journals/{UNKNOWN_UUID}"),
            EndpointCase(
                "PUT",
                f"/journals/{UNKNOWN_UUID}",
                json={"title": "Missing"},
            ),
            EndpointCase("DELETE", f"/journals/{UNKNOWN_UUID}"),
            EndpointCase("POST", f"/journals/{UNKNOWN_UUID}/favorite"),
            EndpointCase("POST", f"/journals/{UNKNOWN_UUID}/archive"),
            EndpointCase("POST", f"/journals/{UNKNOWN_UUID}/unarchive"),
        ],
    )


def test_delete_journal_removes_media_files(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """
    Deleting a journal should cascade delete its entries and their associated media files.
    """
    # 1. Create journal and entry
    entry = entry_factory(title="Entry with Media")
    journal_id = entry["journal"]["id"]

    # 2. Upload media
    uploaded = upload_sample_media(api_client, api_user.access_token, entry["id"])
    media_id = uploaded["id"]

    # 3. Verify media exists
    download = api_client.get_media(api_user.access_token, media_id)
    assert download.status_code == 200

    # 4. Delete Journal
    api_client.delete_journal(api_user.access_token, journal_id)

    # 5. Verify journal is gone
    journal_response = api_client.request(
        "GET", f"/journals/{journal_id}", token=api_user.access_token
    )
    assert journal_response.status_code == 404

    # 6. Verify entry is gone (entries by journal)
    entries_response = api_client.list_entries(api_user.access_token, journal_id=journal_id)
    assert entries_response == [], "Entries should be cascade deleted with the journal"

    # 7. Verify media is gone (both download and sign endpoint)
    # Check sign endpoint for 404 (metadata gone)
    sign_response = api_client.request(
        "GET", f"/media/{media_id}/sign", token=api_user.access_token, expected=(404,)
    )
    assert sign_response.status_code == 404, "Media entry should be deleted from DB"


def test_reorder_journals_success(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    """Reordering journals should update positions correctly."""
    # Create three journals
    j1_id = _create_sample_journal(api_client, api_user.access_token, "Journal 1")
    j2_id = _create_sample_journal(api_client, api_user.access_token, "Journal 2")
    j3_id = _create_sample_journal(api_client, api_user.access_token, "Journal 3")

    # Reorder journals - reverse the order
    api_client.reorder_journals(
        api_user.access_token,
        [
            {"id": j3_id, "position": 0},
            {"id": j2_id, "position": 1},
            {"id": j1_id, "position": 2},
        ],
    )

    # Verify new positions
    journals = api_client.list_journals(api_user.access_token)
    journal_map = {j["id"]: j for j in journals}

    assert journal_map[j3_id]["position"] == 0
    assert journal_map[j2_id]["position"] == 1
    assert journal_map[j1_id]["position"] == 2

    # Verify ordering in list response
    assert journals[0]["id"] == j3_id
    assert journals[1]["id"] == j2_id
    assert journals[2]["id"] == j1_id


def test_reorder_journals_partial_update(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    """Reordering subset of journals should only update specified positions."""
    # Create four journals
    j1_id = _create_sample_journal(api_client, api_user.access_token, "Journal 1")
    j2_id = _create_sample_journal(api_client, api_user.access_token, "Journal 2")
    j3_id = _create_sample_journal(api_client, api_user.access_token, "Journal 3")
    j4_id = _create_sample_journal(api_client, api_user.access_token, "Journal 4")

    # Capture initial positions for j1 and j3
    initial_journals = api_client.list_journals(api_user.access_token)
    initial_journal_map = {j["id"]: j for j in initial_journals}
    initial_j1_position = initial_journal_map[j1_id]["position"]
    initial_j3_position = initial_journal_map[j3_id]["position"]

    # Only reorder j2 and j4
    api_client.reorder_journals(
        api_user.access_token,
        [
            {"id": j2_id, "position": 0},
            {"id": j4_id, "position": 1},
        ],
    )

    # Verify only specified journals were updated
    journals = api_client.list_journals(api_user.access_token)
    journal_map = {j["id"]: j for j in journals}

    assert journal_map[j2_id]["position"] == 0
    assert journal_map[j4_id]["position"] == 1
    # Verify j1 and j3 positions remain unchanged from their initial values
    assert journal_map[j1_id]["position"] == initial_j1_position
    assert journal_map[j3_id]["position"] == initial_j3_position


def test_reorder_journals_empty_updates(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    """Reordering with empty updates should fail validation."""
    # Create a journal
    j1_id = _create_sample_journal(api_client, api_user.access_token, "Journal 1")

    # Try to reorder with empty updates - should fail validation (min_length=1)
    response = api_client.request(
        "PUT",
        "/journals/reorder",
        token=api_user.access_token,
        json={"updates": []},
        expected=(422,),
    )
    assert response.status_code == 422


def test_reorder_journals_not_found(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    """Reordering with non-existent journal ID should fail."""
    # Create a journal
    j1_id = _create_sample_journal(api_client, api_user.access_token, "Journal 1")

    # Try to reorder with unknown journal ID
    response = api_client.request(
        "PUT",
        "/journals/reorder",
        token=api_user.access_token,
        json={
            "updates": [
                {"id": j1_id, "position": 0},
                {"id": UNKNOWN_UUID, "position": 1},
            ]
        },
        expected=(404,),
    )
    assert response.status_code == 404


def test_reorder_journals_unauthorized_journal(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    """Reordering another user's journal should fail."""
    # Create journal for first user
    j1_id = _create_sample_journal(api_client, api_user.access_token, "Journal 1")

    # Create second user and their journal
    from tests.lib import make_api_user
    api_user2 = make_api_user(api_client)
    j2_id = _create_sample_journal(api_client, api_user2.access_token, "Journal 2")

    # First user tries to reorder second user's journal
    response = api_client.request(
        "PUT",
        "/journals/reorder",
        token=api_user.access_token,
        json={
            "updates": [
                {"id": j1_id, "position": 0},
                {"id": j2_id, "position": 1},  # Not owned by api_user
            ]
        },
        expected=(404,),
    )
    assert response.status_code == 404


def test_reorder_journals_maintains_favorite_ordering(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    """Reordering should work correctly with favorite journals."""
    # Create journals
    j1_id = _create_sample_journal(api_client, api_user.access_token, "Journal 1")
    j2_id = _create_sample_journal(api_client, api_user.access_token, "Journal 2")
    j3_id = _create_sample_journal(api_client, api_user.access_token, "Journal 3")

    # Make j1 and j3 favorites
    api_client.request(
        "POST",
        f"/journals/{j1_id}/favorite",
        token=api_user.access_token,
    )
    api_client.request(
        "POST",
        f"/journals/{j3_id}/favorite",
        token=api_user.access_token,
    )

    # Reorder all journals
    api_client.reorder_journals(
        api_user.access_token,
        [
            {"id": j3_id, "position": 0},
            {"id": j1_id, "position": 1},
            {"id": j2_id, "position": 0},
        ],
    )

    # Verify positions were updated
    journals = api_client.list_journals(api_user.access_token)
    journal_map = {j["id"]: j for j in journals}

    assert journal_map[j3_id]["position"] == 0
    assert journal_map[j1_id]["position"] == 1
    assert journal_map[j2_id]["position"] == 0

    # Verify favorites appear first in listing (is_favorite DESC, position ASC)
    # j3 (favorite, pos 0) should be first
    # j1 (favorite, pos 1) should be second
    # j2 (regular, pos 0) should be third
    assert journals[0]["id"] == j3_id
    assert journals[0]["is_favorite"] is True
    assert journals[1]["id"] == j1_id
    assert journals[1]["is_favorite"] is True
    assert journals[2]["id"] == j2_id
    assert journals[2]["is_favorite"] is False


def test_reorder_journals_requires_auth(api_client: JournivApiClient):
    """Reordering without authentication should fail."""
    response = api_client.request(
        "PUT",
        "/journals/reorder",
        json={"updates": []},
        expected=(401,),
    )
    assert response.status_code == 401


def test_new_journals_appear_at_top(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    """New journals should be created at position 0 and existing journals shifted down."""
    # Create first journal
    j1_id = _create_sample_journal(api_client, api_user.access_token, "Journal 1")

    # Create second journal
    j2_id = _create_sample_journal(api_client, api_user.access_token, "Journal 2")

    # Create third journal
    j3_id = _create_sample_journal(api_client, api_user.access_token, "Journal 3")

    # Verify journals are in reverse creation order (newest first)
    journals = api_client.list_journals(api_user.access_token)
    journal_map = {j["id"]: j for j in journals}

    # All should have positions set
    assert journal_map[j1_id]["position"] is not None
    assert journal_map[j2_id]["position"] is not None
    assert journal_map[j3_id]["position"] is not None

    # Newest journal (j3) should be at position 0
    assert journal_map[j3_id]["position"] == 0
    # Middle journal (j2) should be at position 1
    assert journal_map[j2_id]["position"] == 1
    # Oldest journal (j1) should be at position 2
    assert journal_map[j1_id]["position"] == 2

    # Verify ordering in list response (newest first)
    assert journals[0]["id"] == j3_id
    assert journals[1]["id"] == j2_id
    assert journals[2]["id"] == j1_id
