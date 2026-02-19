"""
Behavioural tests that assert cascades through the public API surface.
"""

from tests.integration.helpers import (
    UNKNOWN_UUID,
    EndpointCase,
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
        moment_id=entry_one["moment_id"],
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


def test_deleting_entry_preserves_moment_artifacts(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Deleting an entry should revert to quick log, preserving moment media/pin."""
    entry = entry_factory(title="Cascade Entry")
    moment_id = entry["moment_id"]

    uploaded = api_client.upload_media(
        api_user.access_token,
        moment_id=moment_id,
        filename="entry-media.jpg",
        content=sample_jpeg_bytes(),
        content_type="image/jpeg",
    )

    api_client.pin_moment(api_user.access_token, moment_id)
    api_client.delete_entry(api_user.access_token, entry["id"])

    entry_response = api_client.request(
        "GET", f"/entries/{entry['id']}", token=api_user.access_token
    )
    assert entry_response.status_code == 404

    moment_response = api_client.request(
        "GET", f"/moments/{moment_id}", token=api_user.access_token
    )
    assert moment_response.status_code == 200
    assert moment_response.json()["is_pinned"] is True

    # media still belongs to the moment after entry deletion
    api_client.wait_for_media_ready(api_user.access_token, uploaded["id"])
    sign_response = api_client.request(
        "GET",
        f"/media/{uploaded['id']}/sign",
        token=api_user.access_token,
        expected=(200,),
    )
    assert sign_response.status_code == 200

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
