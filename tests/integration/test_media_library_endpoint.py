"""
Integration coverage for the media library endpoint (GET /media).

Populated-grid behaviour is exercised through the media upload path, which lives
with the other media tests. Here we pin the contract that does not need an
uploaded file: auth, pagination-parameter validation, filter acceptance and the
empty-account shape.
"""
from tests.lib import ApiUser, JournivApiClient


def test_media_library_requires_auth(api_client: JournivApiClient):
    api_client.request("GET", "/media", expected=(401,))


def test_media_library_empty_account_returns_empty_page(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    body = api_client.request(
        "GET", "/media", token=api_user.access_token, expected=(200,)
    ).json()
    assert body["items"] == []
    assert body["next_cursor_logged_at_utc"] is None
    assert body["next_cursor_id"] is None


def test_media_library_rejects_half_a_cursor(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    api_client.request(
        "GET",
        "/media",
        token=api_user.access_token,
        params={"cursor_id": "00000000-0000-0000-0000-000000000000"},
        expected=(400,),
    )


def test_media_library_accepts_filters(
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    journal = journal_factory(title="Filtered")
    body = api_client.request(
        "GET",
        "/media",
        token=api_user.access_token,
        params={"journal_id": journal["id"], "media_type": "image", "limit": 10},
        expected=(200,),
    ).json()
    assert body["items"] == []


def test_media_library_rejects_unknown_media_type(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    api_client.request(
        "GET",
        "/media",
        token=api_user.access_token,
        params={"media_type": "hologram"},
        expected=(422,),
    )
