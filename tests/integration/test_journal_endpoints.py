"""
Journal API integration coverage.
"""

from tests.integration.helpers import (
    EndpointCase,
    UNKNOWN_UUID,
    assert_not_found,
    assert_requires_authentication,
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
