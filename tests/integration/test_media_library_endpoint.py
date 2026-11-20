"""
Integration coverage for the media library endpoint (GET /media).

Populated-grid behaviour is exercised through the media upload path, which lives
with the other media tests. Here we pin the contract that does not need an
uploaded file: auth, pagination-parameter validation, filter acceptance and the
empty-account shape.
"""
import time

from tests.integration.helpers import upload_sample_media
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


def test_media_library_filters_by_entity_scope(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    """The Media grid of a scoped Timeline shows only that scope's media."""
    activity = api_client.create_activity(api_user.access_token, name="Climbing")
    in_scope = moment_factory(
        note="At the crag", mood_activity=[{"activity_id": activity["id"]}]
    )
    out_of_scope = moment_factory(note="At home")
    in_media = upload_sample_media(
        api_client, api_user.access_token, in_scope["id"], filename="crag.jpg"
    )
    out_media = upload_sample_media(
        api_client, api_user.access_token, out_of_scope["id"], filename="home.jpg"
    )

    def library(**params):
        return api_client.request(
            "GET", "/media", token=api_user.access_token,
            params=params, expected=(200,),
        ).json()["items"]

    # Only completed media is listed; processing may finish asynchronously.
    deadline = time.monotonic() + 30
    while len(library()) < 2 and time.monotonic() < deadline:
        time.sleep(0.5)
    assert {item["id"] for item in library()} == {in_media["id"], out_media["id"]}

    scoped = library(activity_ids=[activity["id"]])
    assert [item["id"] for item in scoped] == [in_media["id"]]
    assert [item["moment_id"] for item in scoped] == [in_scope["id"]]
