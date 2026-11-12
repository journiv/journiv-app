"""Public HTTP integration coverage for journal-sharing permissions."""

from tests.lib import ApiUser, JournivApiClient, make_api_user


def test_owner_can_search_add_and_remove_a_journal_collaborator(
    api_client: JournivApiClient, api_user: ApiUser
) -> None:
    """Membership changes must be discoverable and take effect over HTTP."""
    collaborator = make_api_user(api_client)
    journal = api_client.create_journal(
        api_user.access_token, title="Shared journal", description="Owner's journal"
    )

    search = api_client.request(
        "GET",
        "/users/search",
        token=api_user.access_token,
        params={"q": collaborator.email[:8]},
        expected=(200,),
    ).json()
    assert any(user["id"] == collaborator.user_id for user in search)

    added = api_client.request(
        "POST",
        f"/journals/{journal['id']}/members",
        token=api_user.access_token,
        json={"user_id": collaborator.user_id, "permission": "readonly"},
        expected=(201,),
    ).json()
    assert added["user_id"] == collaborator.user_id
    assert added["permission"] == "readonly"

    visible = api_client.get_journal(collaborator.access_token, journal["id"])
    assert visible["access_level"] == "readonly"
    assert visible["owner_id"] == api_user.user_id

    non_owner_change = api_client.request(
        "POST",
        f"/journals/{journal['id']}/members",
        token=collaborator.access_token,
        json={"user_id": api_user.user_id, "permission": "readonly"},
    )
    assert non_owner_change.status_code == 404

    duplicate = api_client.request(
        "POST",
        f"/journals/{journal['id']}/members",
        token=api_user.access_token,
        json={"user_id": collaborator.user_id, "permission": "readonly"},
    )
    assert duplicate.status_code == 409

    api_client.request(
        "DELETE",
        f"/journals/{journal['id']}/members/{collaborator.user_id}",
        token=api_user.access_token,
        expected=(204,),
    )
    revoked = api_client.request(
        "GET", f"/journals/{journal['id']}", token=collaborator.access_token
    )
    assert revoked.status_code == 404


def test_member_needs_edit_permission_to_create_shared_journal_entries(
    api_client: JournivApiClient, api_user: ApiUser
) -> None:
    """Viewers may read a journal but cannot write entries until promoted."""
    collaborator = make_api_user(api_client)
    journal = api_client.create_journal(
        api_user.access_token, title="Collaborative journal", description="Shared"
    )
    api_client.request(
        "POST",
        f"/journals/{journal['id']}/members",
        token=api_user.access_token,
        json={"user_id": collaborator.user_id, "permission": "readonly"},
        expected=(201,),
    )
    moment = api_client.create_moment(collaborator.access_token)
    entry_payload = {
        "title": "Collaborator entry",
        "journal_id": journal["id"],
        "moment_id": moment["id"],
        "content_delta": {"ops": [{"insert": "Shared writing"}]},
    }

    readonly_write = api_client.request(
        "POST", "/entries/", token=collaborator.access_token, json=entry_payload
    )
    assert readonly_write.status_code == 404

    promoted = api_client.request(
        "PUT",
        f"/journals/{journal['id']}/members/{collaborator.user_id}",
        token=api_user.access_token,
        json={"permission": "edit"},
        expected=(200,),
    ).json()
    assert promoted["permission"] == "edit"

    created = api_client.request(
        "POST",
        "/entries/",
        token=collaborator.access_token,
        json=entry_payload,
        expected=(201,),
    ).json()
    assert created["created_by_user_id"] == collaborator.user_id
    assert created["author_name"]
