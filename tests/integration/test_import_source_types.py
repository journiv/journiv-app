
import io
import zipfile

from tests.lib import ApiUser, JournivApiClient


def _tiny_dayone_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        # Day One expects Journal.json usually, but for upload validation just needs to be a valid zip
        archive.writestr("Journal.json", "{}")
    return buffer.getvalue()

class TestImportSourceTypes:
    """Integration tests for different import source types."""

    def test_upload_import_dayone_source(self, api_client: JournivApiClient, api_user: ApiUser):
        """Verify that 'dayone' is accepted as a valid source type."""
        zip_bytes = _tiny_dayone_zip()

        response = api_client.request(
            "POST",
            "/import/upload",
            token=api_user.access_token,
            files={"file": ("dayone.zip", io.BytesIO(zip_bytes), "application/zip")},
            data={"source_type": "dayone"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["source_type"] == "dayone"
        assert data["status"] in ["queued", "pending", "running"]

    def test_upload_import_invalid_source(self, api_client: JournivApiClient, api_user: ApiUser):
        """Verify that unknown source types are rejected."""
        zip_bytes = _tiny_dayone_zip()

        response = api_client.request(
            "POST",
            "/import/upload",
            token=api_user.access_token,
            files={"file": ("test.zip", io.BytesIO(zip_bytes), "application/zip")},
            data={"source_type": "invalid_source_123"},
        )

        assert response.status_code == 400
        assert "Invalid source type" in response.text
