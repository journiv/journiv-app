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
