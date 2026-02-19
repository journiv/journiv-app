"""
Media upload integration tests.
"""
import io

from tests.integration.helpers import (
    UNKNOWN_UUID,
    EndpointCase,
    assert_requires_authentication,
    sample_jpeg_bytes,
    upload_sample_media,
)
from tests.lib import ApiUser, JournivApiClient, make_api_user


def _assert_media_exists(api_client: JournivApiClient, token: str, media_id: str) -> None:
    """Media may be ready (200) or still processing (400: not ready)."""
    sign_response = api_client.request(
        "GET",
        f"/media/{media_id}/sign",
        token=token,
        expected=(200, 400),
    )
    assert sign_response.status_code in (200, 400)
    if sign_response.status_code == 400:
        assert "not ready" in sign_response.json().get("detail", "").lower()


def test_media_upload_fetch_and_delete(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Uploading media returns metadata that can be fetched and deleted."""
    entry = entry_factory()
    moment_id = entry["moment_id"]
    uploaded = upload_sample_media(api_client, api_user.access_token, moment_id)
    assert uploaded["moment_id"] == moment_id
    assert uploaded["alt_text"] == "integration test image"

    media_id = uploaded["id"]
    _assert_media_exists(api_client, api_user.access_token, media_id)

    deleted = api_client.request(
        "DELETE",
        f"/media/{media_id}",
        token=api_user.access_token,
    ).json()
    assert deleted["media_id"] == media_id
    assert "deleted" in deleted["message"].lower()

    missing = api_client.request(
        "GET", f"/media/{media_id}/sign", token=api_user.access_token, expected=(404,)
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
        data={"moment_id": entry["moment_id"], "alt_text": "text file"},
    )
    assert response.status_code == 400


def test_media_download_supports_range(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Media downloads should honor HTTP Range requests."""
    entry = entry_factory()
    uploaded = upload_sample_media(api_client, api_user.access_token, entry["moment_id"])

    # Get signed URL first
    sign_response = api_client.request(
        "GET", f"/media/{uploaded['id']}/sign", token=api_user.access_token, expected=(200, 400)
    )
    if sign_response.status_code == 400:
        # Worker-less test runs can leave media in pending state.
        assert "not ready" in sign_response.json().get("detail", "").lower()
        return

    signed_url = sign_response.json()["signed_url"]

    # Use underlying client to fetch signed URL with Range header
    # Prepend service root to make it absolute
    full_url = f"{api_client._service_root}{signed_url}"
    response = api_client._client.get(
        full_url,
        headers={"Range": "bytes=0-9"}
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
    uploaded = upload_sample_media(api_client, api_user.access_token, entry["moment_id"])
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
                    "moment_id": UNKNOWN_UUID,
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
    uploaded = upload_sample_media(api_client, api_user.access_token, entry["moment_id"])
    assert_requires_authentication(
        api_client,
        [
            EndpointCase("GET", f"/media/{uploaded['id']}/sign"),
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
    Test that media files shared between moments are only deleted when all references are removed.

    Scenario:
    1. Upload same image to Moment A and Moment B (deduplication creates 1 file, 2 DB records)
    2. Delete Moment A - physical file should be preserved (Moment B still references it)
    3. Moment B's media should still be accessible
    4. Delete Moment B - physical file should now be deleted (no more references)
    """
    # Create two entries (moments)
    entry_a = entry_factory(title="Entry A")
    entry_b = entry_factory(title="Entry B")
    moment_a_id = entry_a["moment_id"]
    moment_b_id = entry_b["moment_id"]

    # Upload the same image to both moments
    # The backend should deduplicate and store only one physical file
    media_a = upload_sample_media(api_client, api_user.access_token, moment_a_id)
    media_b = upload_sample_media(api_client, api_user.access_token, moment_b_id)

    # Both media records should exist with different IDs but same checksum
    assert media_a["id"] != media_b["id"], "Media records should have different IDs"
    assert media_a["moment_id"] == moment_a_id
    assert media_b["moment_id"] == moment_b_id

    # Verify both media records are accessible
    _assert_media_exists(api_client, api_user.access_token, media_a["id"])
    _assert_media_exists(api_client, api_user.access_token, media_b["id"])

    # Delete Moment A directly (media is owned by moments)
    api_client.request(
        "DELETE",
        f"/moments/{moment_a_id}",
        token=api_user.access_token,
        expected=(200, 204),
    )

    # Verify media_a DB record is deleted (check via sign endpoint)
    missing_media_a = api_client.request(
        "GET", f"/media/{media_a['id']}/sign", token=api_user.access_token, expected=(404,)
    )
    assert missing_media_a.status_code == 404, "Media A record should be deleted"

    # CRITICAL: Verify media_b is STILL accessible (physical file preserved due to reference counting)
    sign_b_after_a_deleted = api_client.request(
        "GET",
        f"/media/{media_b['id']}/sign",
        token=api_user.access_token,
        expected=(200, 400),
    )
    assert sign_b_after_a_deleted.status_code in (200, 400), (
        "Media B should still be accessible after Moment A deletion because the physical file "
        "is shared and Moment B still references it"
    )

    # Now delete Moment B
    api_client.request(
        "DELETE",
        f"/moments/{moment_b_id}",
        token=api_user.access_token,
        expected=(200, 204),
    )

    # Verify media_b DB record is deleted
    missing_media_b = api_client.request(
        "GET", f"/media/{media_b['id']}/sign", token=api_user.access_token, expected=(404,)
    )
    assert missing_media_b.status_code == 404, "Media B record should be deleted"


def test_shared_media_deletion_via_media_endpoint(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """
    Test that deleting media directly (not via moment deletion) also preserves shared files.

    Scenario:
    1. Upload same image to Moment A and Moment B
    2. Delete media from Moment A directly via /media/{id} endpoint
    3. Moment B's media should still be accessible
    4. Delete media from Moment B - file should be deleted
    """
    entry_a = entry_factory(title="Entry A")
    entry_b = entry_factory(title="Entry B")

    # Upload same image to both moments
    media_a = upload_sample_media(api_client, api_user.access_token, entry_a["moment_id"])
    media_b = upload_sample_media(api_client, api_user.access_token, entry_b["moment_id"])

    # Delete media_a via media endpoint
    delete_media_a = api_client.request(
        "DELETE",
        f"/media/{media_a['id']}",
        token=api_user.access_token,
    )
    assert delete_media_a.status_code == 200

    # Verify media_b is STILL accessible
    sign_b = api_client.request(
        "GET",
        f"/media/{media_b['id']}/sign",
        token=api_user.access_token,
        expected=(200, 400),
    )
    assert sign_b.status_code in (200, 400), (
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
        "GET", f"/media/{media_b['id']}/sign", token=api_user.access_token, expected=(404,)
    )
    assert missing_media_b.status_code == 404


def test_duplicate_media_upload_same_moment(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """
    Test that uploading the same image multiple times to the same moment
    reuses the existing MomentMedia record instead of creating duplicates.
    """
    entry = entry_factory()
    moment_id = entry["moment_id"]

    # Upload the same image twice to the same moment
    image_bytes = sample_jpeg_bytes()
    first_upload = api_client.upload_media(
        api_user.access_token,
        moment_id=moment_id,
        filename="test-image.jpg",
        content=image_bytes,
        content_type="image/jpeg",
        alt_text="First upload",
    )

    # Upload the same image again to the same moment
    second_upload = api_client.upload_media(
        api_user.access_token,
        moment_id=moment_id,
        filename="test-image.jpg",
        content=image_bytes,
        content_type="image/jpeg",
        alt_text="Second upload",
    )

    # Both uploads should return the same media ID (reusing existing record)
    assert first_upload["id"] == second_upload["id"], (
        "Uploading the same image twice to the same moment should return "
        "the same media ID (reusing existing MomentMedia record)"
    )

    # Verify the media record exists (ready or pending)
    _assert_media_exists(api_client, api_user.access_token, first_upload["id"])

    # Verify only one media record exists for this moment
    # We fetch the moment to check its media list (assuming media is included in moment detail)
    moment_response = api_client.request(
        "GET",
        f"/moments/{moment_id}",
        token=api_user.access_token,
    )
    assert moment_response.status_code == 200
    moment_detail = moment_response.json()
    assert "media" in moment_detail, (
        f"Expected 'media' in moment detail response for moment {moment_id}"
    )
    media_list = moment_detail["media"]

    media_count = len(media_list)
    assert media_count == 1, (
        f"Moment should have exactly 1 media record, but found {media_count}"
    )

    # Verify the media ID matches what was returned from upload
    assert media_list[0]["id"] == first_upload["id"], (
        "Media ID in moment media list should match the uploaded media ID"
    )
