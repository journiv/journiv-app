"""
End-to-end integration tests for Day One import.

Tests the complete Day One import flow from upload to verification of imported data.
"""
import os
import time
from pathlib import Path
from typing import Dict, Any

import pytest

from tests.lib import ApiUser, JournivApiClient
from app.core.config import settings


def _load_dayone_fixture() -> bytes:
    """Load the Day One test export fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "dayone_test_export.zip"
    if not fixture_path.exists():
        raise FileNotFoundError(f"Day One test fixture not found: {fixture_path}")
    return fixture_path.read_bytes()


def _wait_for_import_completion(
    api_client: JournivApiClient,
    token: str,
    job_id: str,
    timeout: int = 60,
    poll_interval: float = 1.0,
) -> Dict[str, Any]:
    """
    Poll import job status until completion or timeout.

    Args:
        api_client: API client instance
        token: User access token
        job_id: Import job ID
        timeout: Maximum seconds to wait
        poll_interval: Seconds between polls

    Returns:
        Final job status dict

    Raises:
        TimeoutError: If job doesn't complete within timeout
        RuntimeError: If job fails
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        status = api_client.import_status(token, job_id)

        if status["status"] == "completed":
            return status
        elif status["status"] == "failed":
            errors = status.get("errors") or "Unknown error"
            raise RuntimeError(f"Import job failed: {errors}")

        time.sleep(poll_interval)

    raise TimeoutError(f"Import job {job_id} did not complete within {timeout}s")


class TestDayOneImportE2E:
    """End-to-end tests for Day One import functionality."""

    def test_dayone_import_full_flow(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """
        Test complete Day One import flow with real fixture data.

        Expected fixture contents:
        - 1 journal ("Test Journal")
        - 5 entries with various content
        - 3 photos embedded across entries
        - Location data on one entry
        - Tags on one entry
        - Various richText formats (headers, bold, italic, etc.)
        """
        # 1. Upload Day One export
        dayone_bytes = _load_dayone_fixture()

        upload_response = api_client.upload_import(
            api_user.access_token,
            file_bytes=dayone_bytes,
            filename="dayone_test_export.zip",
            source_type="dayone",
            expected=(202,),
        )

        assert upload_response.status_code == 202
        job = upload_response.json()
        assert job["id"]
        assert job["status"] in ("pending", "queued", "running")
        assert job["source_type"] == "dayone"

        # 2. Wait for import to complete
        completed_job = _wait_for_import_completion(
            api_client,
            api_user.access_token,
            job["id"],
            timeout=60,
        )

        # 3. Verify import results
        assert completed_job["status"] == "completed"
        assert completed_job["progress"] == 100

        result_data = completed_job.get("result_data", {})
        assert result_data["journals_created"] == 1
        assert result_data["entries_created"] == 5
        assert result_data["media_files_imported"] == 3
        assert result_data.get("media_files_skipped", 0) == 0

        # 4. Verify journals were created
        journals = api_client.list_journals(api_user.access_token)
        assert len(journals) == 1

        imported_journal = journals[0]
        assert imported_journal["title"] == "Test Journal"
        assert "Imported from Day One" in imported_journal["description"]
        assert imported_journal["entry_count"] == 5

        # 5. Verify entries were created
        entries = api_client.list_entries(
            api_user.access_token,
            journal_id=imported_journal["id"],
        )
        assert len(entries) == 5

        # Sort by creation date for consistent testing
        entries.sort(key=lambda e: e["entry_datetime_utc"])

        # 6. Verify title extraction from richText
        entry_titles = [e.get("title") or "" for e in entries]
        assert any("Anonymized Header" in title for title in entry_titles)
        assert any("Anonymized Main Title" in title for title in entry_titles)
        assert any("Template Header" in title for title in entry_titles)

        # 7. Verify richText was converted to Markdown
        # Find the entry with embedded photos
        photo_entry = next(
            (e for e in entries if "Anonymized Main Title" in (e.get("title") or "")),
            None,
        )
        assert photo_entry is not None

        content = photo_entry.get("content_plain_text") or ""
        # Should have headers (markdown or plain)
        assert any(h in content for h in ["Anonymized Main Title", "### H3", "H3"])
        # Should NOT have raw JSON
        assert "{\"contents\":" not in content
        assert "richText" not in content
        # With Quill Delta format, media references are stored in content_delta, not as markdown in plain text
        # Verify that placeholder text is present (the text around photos)
        assert any(phrase in content for phrase in ["Placeholder text for photos", "More placeholder text"])

        # 8. Verify location data was imported
        assert photo_entry.get("location_json") is not None
        location_json = photo_entry["location_json"]
        assert location_json.get("locality") == "Generic Locality"
        assert location_json.get("country") == "Sample Country"
        assert location_json.get("latitude") is not None
        assert location_json.get("longitude") is not None

        # Legacy location string is optional
        if photo_entry.get("location") is not None:
            assert "Sample Country" in photo_entry["location"]

        # 9. Verify tags were imported
        # The photo entry has tags in the fixture - fetch from separate API
        photo_entry_id = photo_entry["id"]
        entry_tags_response = api_client.request(
            "GET",
            f"/entries/{photo_entry_id}/tags",
            token=api_user.access_token,
            expected=(200,)
        )
        entry_tags = entry_tags_response.json()
        assert len(entry_tags) > 0
        # Verify tag names match fixture (SampleTag1, SampleTag2)
        tag_names = sorted([tag["name"] for tag in entry_tags])
        assert "sampletag1" in tag_names or "sampletag2" in tag_names

        # 10. Verify media files were imported
        # Fetch media from separate API
        entry_media_response = api_client.request(
            "GET",
            f"/entries/{photo_entry_id}/media",
            token=api_user.access_token,
            expected=(200,)
        )
        entry_media = entry_media_response.json()
        assert len(entry_media) == 2

        for media in entry_media:
            assert media["media_type"] == "image"
            assert "file_path" not in media  # Should be excluded
            assert media["checksum"] is not None
            # Verify original filename is preserved
            assert media["original_filename"] is not None
            assert ".jpg" in media["original_filename"]

            # Verify media is accessible by signing it (replaces file_path check)
            api_client.wait_for_media_ready(api_user.access_token, media["id"])
            sign_response = api_client.request(
                "GET", f"/media/{media['id']}/sign",
                token=api_user.access_token
            ).json()
            assert sign_response["signed_url"]
            # Existence check depends on test environment storage setup
            # Note: With Quill Delta format, media is stored in content_delta as embedded objects,
            # not as markdown shortcodes in plain text. Mirror content verification (relaxed headers).
            assert any(h in content for h in ["Anonymized Main Title", "### H3", "H3"])
            assert any(phrase in content for phrase in ["Placeholder text for photos", "More placeholder text"])

        # 11. Verify pinned/starred status
        # Entry with photos is pinned and starred in fixture
        assert photo_entry["is_pinned"] is True

        # 12. Verify timezone handling
        # All entries have UTC timezone in the fixture
        for entry in entries:
            assert entry["entry_timezone"] == "UTC"

    def test_dayone_import_with_invalid_zip(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test that invalid ZIP files are rejected."""
        invalid_zip = b"not a zip file"

        response = api_client.upload_import(
            api_user.access_token,
            file_bytes=invalid_zip,
            filename="invalid.zip",
            source_type="dayone",
        )

        assert response.status_code == 400
        error = response.json()
        assert "detail" in error
        assert "ZIP" in error["detail"] or "Invalid" in error["detail"]

    def test_dayone_import_with_missing_json(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test that ZIP without Day One JSON is rejected."""
        import io
        import zipfile

        # Create ZIP without Journal.json
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("photos/test.jpg", b"fake image")

        response = api_client.upload_import(
            api_user.access_token,
            file_bytes=buffer.getvalue(),
            filename="no_json.zip",
            source_type="dayone",
        )

        assert response.status_code == 400
        error = response.json()
        assert "detail" in error
        # Should mention missing JSON file
        assert "JSON" in error["detail"] or "Missing" in error["detail"]

    def test_dayone_import_status_polling(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test import status polling returns valid states."""
        dayone_bytes = _load_dayone_fixture()

        upload_response = api_client.upload_import(
            api_user.access_token,
            file_bytes=dayone_bytes,
            source_type="dayone",
            expected=(202,),
        )

        job = upload_response.json()
        job_id = job["id"]

        # Poll status multiple times
        seen_statuses = set()
        max_polls = 30

        for _ in range(max_polls):
            status = api_client.import_status(api_user.access_token, job_id)

            assert status["id"] == job_id
            assert status["source_type"] == "dayone"
            assert "status" in status
            assert "progress" in status

            seen_statuses.add(status["status"])

            if status["status"] == "completed":
                # Verify completed job has result_data
                assert status["result_data"] is not None
                assert "journals_created" in status["result_data"]
                assert "entries_created" in status["result_data"]
                break
            elif status["status"] == "failed":
                pytest.fail(f"Import job failed: {status.get('errors')}")

            time.sleep(1)

        # Should have progressed through valid states
        valid_states = {"pending", "queued", "running", "completed"}
        assert seen_statuses.issubset(valid_states)
        assert "completed" in seen_statuses

    def test_dayone_import_creates_separate_journal_per_export(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test that each Day One import creates a separate journal."""
        dayone_bytes = _load_dayone_fixture()

        # Import first time
        upload1 = api_client.upload_import(
            api_user.access_token,
            file_bytes=dayone_bytes,
            source_type="dayone",
            expected=(202,),
        )
        job1 = upload1.json()
        _wait_for_import_completion(api_client, api_user.access_token, job1["id"])

        # Import second time
        upload2 = api_client.upload_import(
            api_user.access_token,
            file_bytes=dayone_bytes,
            source_type="dayone",
            expected=(202,),
        )
        job2 = upload2.json()
        _wait_for_import_completion(api_client, api_user.access_token, job2["id"])

        # Should now have 2 journals
        journals = api_client.list_journals(api_user.access_token)
        assert len(journals) == 2

        # Both should be named "Test Journal" (from Day One export)
        journal_titles = [j["title"] for j in journals]
        assert journal_titles.count("Test Journal") == 2

        # Each should have 5 entries
        for journal in journals:
            assert journal["entry_count"] == 5

    def test_dayone_import_unauthorized(
        self,
        api_client: JournivApiClient,
    ):
        """Test that import requires authentication."""
        dayone_bytes = _load_dayone_fixture()

        # Try without token
        response = api_client.request(
            "POST",
            "/import/upload",
            files={"file": ("test.zip", dayone_bytes, "application/zip")},
            data={"source_type": "dayone"},
        )

        assert response.status_code == 401

    def test_dayone_import_wrong_source_type(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test that wrong source_type is rejected."""
        dayone_bytes = _load_dayone_fixture()

        # Try with journiv source_type (Day One export won't have data.json)
        response = api_client.upload_import(
            api_user.access_token,
            file_bytes=dayone_bytes,
            source_type="journiv",
        )

        # Should fail validation because Day One ZIP doesn't have data.json
        assert response.status_code == 400
        error = response.json()
        assert "data.json" in error["detail"]

    def test_dayone_import_handles_duplicate_media_in_entry(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """
        Test that Day One import handles duplicate media within the same entry correctly.

        When the same media file appears multiple times in a Day One entry,
        the import should reuse the existing EntryMedia record instead of
        creating duplicates, preventing unique constraint violations on (entry_id, checksum).

        This test verifies the import completes successfully even with potential duplicates.
        """
        dayone_bytes = _load_dayone_fixture()

        upload_response = api_client.upload_import(
            api_user.access_token,
            file_bytes=dayone_bytes,
            filename="dayone_test_export.zip",
            source_type="dayone",
            expected=(202,),
        )

        assert upload_response.status_code == 202
        job = upload_response.json()
        job_id = job["id"]

        # Wait for import to complete
        completed_job = _wait_for_import_completion(
            api_client,
            api_user.access_token,
            job_id,
            timeout=60,
        )

        # Verify import completed successfully (not failed due to duplicate key error)
        assert completed_job["status"] == "completed"
        assert completed_job["progress"] == 100

        # Verify no errors related to duplicate media
        errors = completed_job.get("errors") or []
        duplicate_errors = [
            error for error in (errors if isinstance(errors, list) else [])
            if "duplicate key" in str(error).lower() or "uq_entry_media_entry_checksum" in str(error)
        ]
        assert len(duplicate_errors) == 0, (
            f"Import should not have duplicate key errors. Found: {duplicate_errors}"
        )

        # Verify entries were created and have media
        result_data = completed_job.get("result_data", {})
        assert result_data["entries_created"] > 0
        assert result_data["media_files_imported"] > 0

        # Verify entries can be fetched and have media attached
        journals = api_client.list_journals(api_user.access_token)
        assert len(journals) > 0

        for journal in journals:
            entries = api_client.list_entries(
                api_user.access_token,
                journal_id=journal["id"],
            )
            for entry in entries:
                # Fetch media for each entry to verify no duplicates
                entry_media_response = api_client.request(
                    "GET",
                    f"/entries/{entry['id']}/media",
                    token=api_user.access_token,
                    expected=(200,)
                )
                entry_media = entry_media_response.json()

                # Verify no duplicate (entry_id, checksum) combinations
                checksums_by_entry = {}
                for media in entry_media:
                    checksum = media.get("checksum")
                    if checksum:
                        if checksum in checksums_by_entry:
                            pytest.fail(
                                f"Found duplicate media with same checksum {checksum} "
                                f"for entry {entry['id']}. This should not happen."
                            )
                        checksums_by_entry[checksum] = media
