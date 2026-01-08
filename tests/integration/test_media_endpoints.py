"""
Media upload integration tests.
"""
import io

from tests.integration.helpers import (
    EndpointCase,
    UNKNOWN_UUID,
    assert_requires_authentication,
    sample_jpeg_bytes,
)
from tests.lib import ApiUser, JournivApiClient, make_api_user


def _upload_sample_media(api_client: JournivApiClient, token: str, entry_id: str) -> dict:
    return api_client.upload_media(
        token,
        entry_id=entry_id,
        filename="integration-test.jpg",
        content=sample_jpeg_bytes(),
        content_type="image/jpeg",
        alt_text="integration test image",
    )


def test_media_upload_fetch_and_delete(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Uploading media returns metadata that can be fetched and deleted."""
    entry = entry_factory()
    uploaded = _upload_sample_media(api_client, api_user.access_token, entry["id"])
    assert uploaded["entry_id"] == entry["id"]
    assert uploaded["alt_text"] == "integration test image"

    media_id = uploaded["id"]
    download = api_client.get_media(api_user.access_token, media_id)
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("image/")

    deleted = api_client.request(
        "DELETE",
        f"/media/{media_id}",
        token=api_user.access_token,
    ).json()
    assert deleted["media_id"] == media_id
    assert "deleted" in deleted["message"].lower()

    missing = api_client.request(
        "GET", f"/media/{media_id}", token=api_user.access_token
    )
    assert missing.status_code == 404


def test_media_upload_rejects_invalid_type(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Uploading a file with an invalid MIME type should fail with 400."""
    entry = entry_factory()
    response = api_client.request(
        "POST",
        "/media/upload",
        token=api_user.access_token,
        files={"file": ("notes.txt", io.BytesIO(b"data"), "text/plain")},
        data={"entry_id": entry["id"], "alt_text": "text file"},
    )
    assert response.status_code == 400


def test_media_download_supports_range(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Media downloads should honor HTTP Range requests."""
    entry = entry_factory()
    uploaded = _upload_sample_media(api_client, api_user.access_token, entry["id"])

    response = api_client.request(
        "GET",
        f"/media/{uploaded['id']}",
        token=api_user.access_token,
        headers={"Range": "bytes=0-9"},
    )
    assert response.status_code == 206
    assert response.headers["content-range"].startswith("bytes 0-9/")
    assert response.headers["accept-ranges"] == "bytes"


def test_media_delete_requires_ownership(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Users cannot delete media owned by someone else."""
    entry = entry_factory()
    uploaded = _upload_sample_media(api_client, api_user.access_token, entry["id"])
    media_id = uploaded["id"]

    other_user = make_api_user(api_client)
    forbidden = api_client.request(
        "DELETE", f"/media/{media_id}", token=other_user.access_token
    )
    assert forbidden.status_code == 404

    api_client.request("DELETE", f"/media/{media_id}", token=api_user.access_token)

def test_media_upload_requires_auth(api_client: JournivApiClient):
    """Anonymous users cannot upload media."""
    assert_requires_authentication(
        api_client,
        [
            EndpointCase(
                "POST",
                "/media/upload",
                files={
                    "file": (
                        "test.jpg",
                        io.BytesIO(sample_jpeg_bytes()),
                        "image/jpeg",
                    )
                },
                data={
                    "entry_id": UNKNOWN_UUID,
                    "alt_text": "unauthorized",
                },
            ),
        ],
    )


def test_media_get_and_delete_require_auth(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    entry = entry_factory()
    uploaded = _upload_sample_media(api_client, api_user.access_token, entry["id"])
    assert_requires_authentication(
        api_client,
        [
            EndpointCase("GET", f"/media/{uploaded['id']}"),
            EndpointCase("DELETE", f"/media/{uploaded['id']}"),
        ],
    )
    api_client.request("DELETE", f"/media/{uploaded['id']}", token=api_user.access_token)


def test_shared_media_deletion_preserves_file_with_references(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """
    Test that media files shared between entries are only deleted when all references are removed.

    Scenario:
    1. Upload same image to Entry A and Entry B (deduplication creates 1 file, 2 DB records)
    2. Delete Entry A - physical file should be preserved (Entry B still references it)
    3. Entry B's media should still be accessible
    4. Delete Entry B - physical file should now be deleted (no more references)
    """
    # Create two entries
    entry_a = entry_factory(title="Entry A")
    entry_b = entry_factory(title="Entry B")

    # Upload the same image to both entries
    # The backend should deduplicate and store only one physical file
    media_a = _upload_sample_media(api_client, api_user.access_token, entry_a["id"])
    media_b = _upload_sample_media(api_client, api_user.access_token, entry_b["id"])

    # Both media records should exist with different IDs but same checksum
    assert media_a["id"] != media_b["id"], "Media records should have different IDs"
    assert media_a["entry_id"] == entry_a["id"]
    assert media_b["entry_id"] == entry_b["id"]

    # Verify both media files are accessible
    download_a = api_client.get_media(api_user.access_token, media_a["id"])
    assert download_a.status_code == 200
    download_b = api_client.get_media(api_user.access_token, media_b["id"])
    assert download_b.status_code == 200

    # Delete Entry A (which should delete media_a DB record but preserve the physical file)
    delete_entry_a = api_client.request(
        "DELETE",
        f"/entries/{entry_a['id']}",
        token=api_user.access_token,
    )
    assert delete_entry_a.status_code in (200, 204), "Entry deletion should succeed"

    # Verify media_a DB record is deleted
    missing_media_a = api_client.request(
        "GET", f"/media/{media_a['id']}", token=api_user.access_token
    )
    assert missing_media_a.status_code == 404, "Media A record should be deleted"

    # CRITICAL: Verify media_b is STILL accessible (physical file preserved due to reference counting)
    download_b_after_a_deleted = api_client.request(
        "GET", f"/media/{media_b['id']}", token=api_user.access_token
    )
    assert download_b_after_a_deleted.status_code == 200, (
        "Media B should still be accessible after Entry A deletion because the physical file "
        "is shared and Entry B still references it"
    )

    # Verify the content is identical (same physical file)
    assert download_b_after_a_deleted.content == download_b.content

    # Now delete Entry B (should delete media_b DB record AND the physical file)
    delete_entry_b = api_client.request(
        "DELETE",
        f"/entries/{entry_b['id']}",
        token=api_user.access_token,
    )
    assert delete_entry_b.status_code in (200, 204), "Entry deletion should succeed"

    # Verify media_b DB record is deleted
    missing_media_b = api_client.request(
        "GET", f"/media/{media_b['id']}", token=api_user.access_token
    )
    assert missing_media_b.status_code == 404, "Media B record should be deleted"


def test_shared_media_deletion_via_media_endpoint(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """
    Test that deleting media directly (not via entry deletion) also preserves shared files.

    Scenario:
    1. Upload same image to Entry A and Entry B
    2. Delete media from Entry A directly via /media/{id} endpoint
    3. Entry B's media should still be accessible
    4. Delete media from Entry B - file should be deleted
    """
    entry_a = entry_factory(title="Entry A")
    entry_b = entry_factory(title="Entry B")

    # Upload same image to both entries
    media_a = _upload_sample_media(api_client, api_user.access_token, entry_a["id"])
    media_b = _upload_sample_media(api_client, api_user.access_token, entry_b["id"])

    # Delete media_a via media endpoint
    delete_media_a = api_client.request(
        "DELETE",
        f"/media/{media_a['id']}",
        token=api_user.access_token,
    )
    assert delete_media_a.status_code == 200

    # Verify media_b is STILL accessible
    download_b = api_client.request(
        "GET", f"/media/{media_b['id']}", token=api_user.access_token
    )
    assert download_b.status_code == 200, (
        "Media B should still be accessible after deleting Media A "
        "because they share the same physical file"
    )

    # Delete media_b
    delete_media_b = api_client.request(
        "DELETE",
        f"/media/{media_b['id']}",
        token=api_user.access_token,
    )
    assert delete_media_b.status_code == 200

    # Now both should be gone
    missing_media_b = api_client.request(
        "GET", f"/media/{media_b['id']}", token=api_user.access_token
    )
    assert missing_media_b.status_code == 404


def test_duplicate_media_upload_same_entry(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """
    Test that uploading the same image multiple times to the same entry
    reuses the existing EntryMedia record instead of creating duplicates.

    This prevents unique constraint violations on (entry_id, checksum).
    """
    entry = entry_factory()

    # Upload the same image twice to the same entry
    image_bytes = sample_jpeg_bytes()
    first_upload = api_client.upload_media(
        api_user.access_token,
        entry_id=entry["id"],
        filename="test-image.jpg",
        content=image_bytes,
        content_type="image/jpeg",
        alt_text="First upload",
    )

    # Upload the same image again to the same entry
    second_upload = api_client.upload_media(
        api_user.access_token,
        entry_id=entry["id"],
        filename="test-image.jpg",
        content=image_bytes,
        content_type="image/jpeg",
        alt_text="Second upload",
    )

    # Both uploads should return the same media ID (reusing existing record)
    assert first_upload["id"] == second_upload["id"], (
        "Uploading the same image twice to the same entry should return "
        "the same media ID (reusing existing EntryMedia record)"
    )

    # Verify the media record is accessible
    media_response = api_client.get_media(api_user.access_token, first_upload["id"])
    assert media_response.status_code == 200

    # Verify only one media record exists for this entry
    entry_media_response = api_client.request(
        "GET",
        f"/entries/{entry['id']}/media",
        token=api_user.access_token,
    )
    assert entry_media_response.status_code == 200
    entry_media = entry_media_response.json()
    media_count = len(entry_media)
    assert media_count == 1, (
        f"Entry should have exactly 1 media record, but found {media_count}"
    )
    
    # Verify the media ID matches what was returned from upload
    assert entry_media[0]["id"] == first_upload["id"], (
        "Media ID in entry media list should match the uploaded media ID"
    )
