"""
End-to-end account deletion scenarios.
"""
from datetime import date

from tests.integration.helpers import (
    EndpointCase,
    assert_requires_authentication,
    assert_status_codes,
)
from tests.lib import ApiUser, JournivApiClient


def test_account_deletion_removes_all_access(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
    entry_factory,
):
    """Deleting the account should revoke access and make data inaccessible."""
    journal = journal_factory(title="Goodbye Journal")
    entry = entry_factory(journal=journal, title="Last entry")
    tag = api_client.create_tag(api_user.access_token, name="farewell")
    moods = api_client.list_moods(api_user.access_token)
    if moods:
        api_client.create_mood_log(
            api_user.access_token,
            entry_id=entry["id"],
            mood_id=moods[0]["id"],
            logged_date=date.today().isoformat(),
            notes="Log before deletion",
        )

    deletion = api_client.delete_account(api_user.access_token)
    assert "deleted" in deletion["message"].lower()

    # The previous access token should now fail for every endpoint.
    protected_cases = [
        EndpointCase("GET", "/users/me"),
        EndpointCase("GET", "/journals/"),
        EndpointCase("GET", "/entries/"),
        EndpointCase("GET", "/tags/"),
        EndpointCase("GET", "/moods/"),
        EndpointCase("GET", "/moods/logs"),
        EndpointCase("GET", "/prompts/"),
        EndpointCase("GET", "/analytics/writing-streak"),
        EndpointCase("GET", "/analytics/productivity"),
        EndpointCase("GET", "/analytics/journals"),
        EndpointCase("GET", "/media/formats"),
        EndpointCase("GET", "/import/"),
        EndpointCase("GET", "/export/"),
    ]
    assert_status_codes(
        api_client,
        protected_cases,
        token=api_user.access_token,
        expected_status=(401,),
    )

    # Attempting to login again should fail.
    login = api_client.request(
        "POST",
        "/auth/login",
        json={"email": api_user.email, "password": api_user.password},
    )
    assert login.status_code == 401


def test_account_deletion_requires_auth(api_client: JournivApiClient):
    """Deleting an account without a token must return 401."""
    assert_requires_authentication(
        api_client,
        [EndpointCase("DELETE", "/users/me")],
    )
