"""
Integration coverage for /users endpoints.
"""
from tests.integration.helpers import EndpointCase, assert_requires_authentication
from tests.lib import ApiUser, JournivApiClient, make_api_user


def test_get_and_update_profile(api_client: JournivApiClient, api_user: ApiUser):
    """Users can retrieve and update their profile information."""
    profile = api_client.current_user(api_user.access_token)
    assert profile["id"] == api_user.user_id
    assert profile["email"] == api_user.email

    updated = api_client.update_profile(
        api_user.access_token,
        {"name": "Updated Test User"},
    )
    assert updated["name"] == "Updated Test User"


def test_settings_round_trip(api_client: JournivApiClient, api_user: ApiUser):
    """Settings endpoint should return and persist preferences."""
    current_settings = api_client.get_user_settings(api_user.access_token)
    assert "time_zone" in current_settings

    desired = {
        "time_zone": "America/New_York",
        "daily_prompt_enabled": False,
        "theme": "dark",
    }
    updated = api_client.update_user_settings(api_user.access_token, desired)

    assert updated["time_zone"] == desired["time_zone"]
    assert updated["daily_prompt_enabled"] is False
    assert updated["theme"] == "dark"


def test_account_deletion_revokes_access(api_client: JournivApiClient):
    """Deleting the account immediately revokes existing tokens."""
    user = make_api_user(api_client)

    response = api_client.delete_account(user.access_token)
    assert "deleted" in response["message"].lower()

    # Existing token should now be rejected
    unauthorized = api_client.request("GET", "/users/me", token=user.access_token)
    assert unauthorized.status_code == 401

    # Logging in again should also fail
    login_attempt = api_client.request(
        "POST",
        "/auth/login",
        json={"email": user.email, "password": user.password},
    )
    assert login_attempt.status_code == 401


def test_user_endpoints_require_authentication(api_client: JournivApiClient):
    """Endpoints under /users/me should reject missing tokens."""
    assert_requires_authentication(
        api_client,
        [
            EndpointCase("GET", "/users/me"),
            EndpointCase("PUT", "/users/me", json={"name": "Nope"}),
            EndpointCase("DELETE", "/users/me"),
            EndpointCase("GET", "/users/me/settings"),
            EndpointCase("PUT", "/users/me/settings", json={}),
        ],
    )
