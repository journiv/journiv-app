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
