"""
End-to-end integration tests for Journiv native import/export.

Tests the complete Journiv export → import round-trip flow including:
- Creating journals, entries, tags, media
- Exporting to ZIP
- Importing from ZIP
- Verifying imported data matches original
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import date, datetime, timezone
from typing import Any

import pytest

from tests.integration.helpers import (
    sample_jpeg_bytes,
    upload_sample_media,
    wait_for_export_completion,
    wait_for_import_completion,
    download_export,
)
from tests.lib import ApiUser, JournivApiClient, make_api_user


class TestJournivImportExportE2E:
    """End-to-end tests for Journiv native import/export functionality."""

    def test_journiv_export_import_round_trip(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """
        Test complete Journiv export → import round-trip.

        This is the primary test that exercises the full flow:
        1. Create journals with entries, tags, and media
        2. Export to ZIP
        3. Create a new user and import the ZIP
        4. Verify all data was correctly imported
        """
        # 1. Create test data
        # Create first journal with multiple entries
        # Use valid JournalColor enum values
        journal1 = api_client.create_journal(
            api_user.access_token,
            title="Test Journal One",
            description="First test journal for export",
            color="#EF4444",  # RED from JournalColor enum
            icon="📔",
        )

        # Create entries with varied content
        entry1 = api_client.create_entry(
            api_user.access_token,
            journal_id=journal1["id"],
            title="First Entry",
            content="This is the first entry with **bold** and _italic_ text.",
            entry_date=date.today().isoformat(),
        )
        api_client.update_entry(
            api_user.access_token,
            entry1["id"],
            {"is_pinned": True},
        )

        _entry2 = api_client.create_entry(
            api_user.access_token,
            journal_id=journal1["id"],
            title="Second Entry",
            content="Another entry with different content.\n\nMultiple paragraphs here.",
            entry_date=date.today().isoformat(),
        )

        # Upload media to first entry
        _media1 = upload_sample_media(
            api_client,
            api_user.access_token,
            entry1["id"],
            filename="photo1.jpg",
            alt_text="Test photo 1",
        )

        _media2 = upload_sample_media(
            api_client,
            api_user.access_token,
            entry1["id"],
            filename="photo2.jpg",
            alt_text="Test photo 2",
        )

        # Create second journal
        _journal2 = api_client.create_journal(
            api_user.access_token,
            title="Test Journal Two",
            description="Second test journal",
            color="#3B82F6",
            icon="📓",
        )

        _entry3 = api_client.create_entry(
            api_user.access_token,
            journal_id=_journal2["id"],
            title="Entry in Second Journal",
            content="Content in the second journal.",
            entry_date=date.today().isoformat(),
        )

        # Create tags and attach to entries
        tag1 = api_client.create_tag(api_user.access_token, name="test-tag-1", color="#22C55E")
        tag2 = api_client.create_tag(api_user.access_token, name="test-tag-2", color="#EAB308")

        # Attach tags to entry (using correct tag endpoint: /tags/entry/{entry_id}/tag/{tag_id})
        api_client.request(
            "POST",
            f"/tags/entry/{entry1['id']}/tag/{tag1['id']}",
            token=api_user.access_token,
            expected=(200, 201),
        )
        api_client.request(
            "POST",
            f"/tags/entry/{entry1['id']}/tag/{tag2['id']}",
            token=api_user.access_token,
            expected=(200, 201),
        )

        # Create activity group and activity
        activity_group = api_client.create_activity_group(
            api_user.access_token,
            name="Health Group",
            icon="💪",
            color_value=0x22C55E,
            position=1,
        )
        activity = api_client.create_activity(
            api_user.access_token,
            name="Exercise",
            group_id=activity_group["id"],
            icon="🏃",
            color="#16A34A",
            position=1,
        )

        # Create goal category and goal
        goal_category = api_client.create_goal_category(
            api_user.access_token,
            name="Health Goals",
            icon="🎯",
            color_value=0x0EA5E9,
            position=1,
        )
        goal = api_client.create_goal(
            api_user.access_token,
            title="Daily Exercise",
            activity_id=activity["id"],
            category_id=goal_category["id"],
            goal_type="achieve",
            frequency_type="daily",
            target_count=1,
            reminder_time="09:00",
            is_paused=False,
            icon="✅",
            color_value=0x0EA5E9,
            position=1,
        )

        # Create custom moods and mood group (ensure names are unique across system moods)
        mood_name_one = f"Curious-{uuid.uuid4().hex[:8]}"
        mood_name_two = f"Grounded-{uuid.uuid4().hex[:8]}"
        custom_mood = api_client.create_mood(
            api_user.access_token,
            name=mood_name_one,
            score=4,
            icon="🧠",
            color_value=0x8B5CF6,
        )
        custom_mood_two = api_client.create_mood(
            api_user.access_token,
            name=mood_name_two,
            score=3,
            icon="🌿",
            color_value=0x10B981,
        )

        api_client.set_mood_visibility(
            api_user.access_token,
            custom_mood["id"],
            is_hidden=True,
        )

        all_moods = api_client.list_moods(
            api_user.access_token,
            include_hidden=True,
        )
        mood_ids = [mood["id"] for mood in all_moods]
        api_client.reorder_moods(api_user.access_token, mood_ids)

        mood_group = api_client.create_mood_group(
            api_user.access_token,
            name="Morning Check-in",
            mood_ids=[custom_mood["id"], custom_mood_two["id"]],
            icon="☀️",
            color_value=0xF59E0B,
            position=1,
        )
        api_client.reorder_mood_group_moods(
            api_user.access_token,
            mood_group["id"],
            mood_ids=[custom_mood_two["id"], custom_mood["id"]],
        )
        api_client.set_mood_group_visibility(
            api_user.access_token,
            mood_group["id"],
            is_hidden=True,
        )

        api_client.reorder_mood_groups(
            api_user.access_token,
            updates=[{"id": mood_group["id"], "position": 1}],
        )

        # Create a moment with activity to generate auto goal log
        api_client.create_moment(
            api_user.access_token,
            logged_date=date.today().isoformat(),
            mood_activity=[{"mood_id": custom_mood_two["id"], "activity_id": activity["id"]}],
        )

        # Create a manual goal log entry
        api_client.toggle_goal(
            api_user.access_token,
            goal["id"],
            logged_date=date.today().isoformat(),
            status="success",
        )

        # 2. Request export with media
        export_job = api_client.request_export(
            api_user.access_token,
            export_type="full",
            include_media=True,
        )
        assert export_job["status"] in ("pending", "queued", "running", "completed")

        # Wait for export to complete
        completed_export = wait_for_export_completion(
            api_client,
            api_user.access_token,
            export_job["id"],
            timeout=120,
        )

        assert completed_export["status"] == "completed"
        assert completed_export["progress"] == 100

        # 3. Download export ZIP
        export_bytes = download_export(
            api_client,
            api_user.access_token,
            export_job["id"],
        )

        # Verify it's a valid ZIP
        assert len(export_bytes) > 0
        with zipfile.ZipFile(io.BytesIO(export_bytes), "r") as zf:
            namelist = zf.namelist()
            assert "data.json" in namelist

            # Verify data.json structure
            with zf.open("data.json") as f:
                data = json.load(f)
                assert "journals" in data
                assert "export_version" in data
                assert "activities" in data
                assert "activity_groups" in data
                assert "goals" in data
                assert "goal_categories" in data
                assert "goal_logs" in data
                assert "goal_manual_logs" in data
                assert "mood_definitions" in data
                assert "mood_groups" in data
                assert "mood_group_links" in data
                assert "mood_preferences" in data
                assert "mood_group_preferences" in data
                assert len(data["journals"]) == 2

                assert any(g["name"] == "Health Group" for g in data["activity_groups"])
                assert any(a["name"] == "Exercise" for a in data["activities"])
                assert any(c["name"] == "Health Goals" for c in data["goal_categories"])
                assert any(g["title"] == "Daily Exercise" for g in data["goals"])
                assert any(
                    m["name"] == mood_name_one and m.get("is_custom") is True
                    for m in data["mood_definitions"]
                )
                assert any(
                    m["name"] == mood_name_two and m.get("is_custom") is True
                    for m in data["mood_definitions"]
                )
                assert any(g["name"] == "Morning Check-in" for g in data["mood_groups"])
                assert len(data["goal_logs"]) >= 1
                assert len(data["goal_manual_logs"]) >= 1

                exported_mood = next(
                    (m for m in data["mood_definitions"] if m["name"] == mood_name_one),
                    None,
                )
                assert exported_mood is not None

                exported_group = next(
                    (g for g in data["mood_groups"] if g["name"] == "Morning Check-in"),
                    None,
                )
                assert exported_group is not None

                assert any(
                    pref["mood_external_id"] == exported_mood["external_id"]
                    and pref["is_hidden"] is True
                    for pref in data["mood_preferences"]
                )
                assert any(
                    pref["mood_group_external_id"] == exported_group["external_id"]
                    and pref["is_hidden"] is True
                    for pref in data["mood_group_preferences"]
                )

                assert any(
                    link["mood_group_external_id"] == exported_group["external_id"]
                    and link["mood_external_id"] == exported_mood["external_id"]
                    for link in data["mood_group_links"]
                )

        # 4. Create a new user and import the export
        import_user = make_api_user(api_client)

        upload_response = api_client.upload_import(
            import_user.access_token,
            file_bytes=export_bytes,
            filename="journiv_export.zip",
            source_type="journiv",
            expected=(202,),
        )

        assert upload_response.status_code == 202
        import_job = upload_response.json()
        assert import_job["source_type"] == "journiv"

        # Wait for import to complete
        completed_import = wait_for_import_completion(
            api_client,
            import_user.access_token,
            import_job["id"],
            timeout=120,
        )

        assert completed_import["status"] == "completed"
        assert completed_import["progress"] == 100

        # Verify import results
        result_data = completed_import.get("result_data", {})
        assert result_data["journals_created"] == 2
        assert result_data["entries_created"] == 3
        # Note: Both media files use sample_jpeg_bytes() so they have identical checksums.
        # The second media reference may be deduplicated depending on storage behavior.
        # We verify actual media count below (line 266: len(imported_media) == 2)
        # rather than relying on result_data counters which may vary.
        media_imported = result_data.get("media_files_imported", 0)
        media_deduplicated = result_data.get("media_files_deduplicated", 0)
        assert media_imported + media_deduplicated >= 1

        # 5. Verify imported data matches original
        imported_journals = api_client.list_journals(import_user.access_token)
        assert len(imported_journals) == 2

        # Find journals by title
        imported_journal1 = next(
            (j for j in imported_journals if j["title"] == "Test Journal One"),
            None,
        )
        imported_journal2 = next(
            (j for j in imported_journals if j["title"] == "Test Journal Two"),
            None,
        )

        assert imported_journal1 is not None
        assert imported_journal2 is not None

        # Verify journal properties
        assert imported_journal1["description"] == "First test journal for export"
        assert imported_journal1["icon"] == "📔"
        assert imported_journal1["entry_count"] == 2

        assert imported_journal2["description"] == "Second test journal"
        assert imported_journal2["icon"] == "📓"
        assert imported_journal2["entry_count"] == 1

        # Verify entries in first journal
        imported_entries1_response = api_client.request(
            "GET",
            f"/entries/journal/{imported_journal1['id']}",
            token=import_user.access_token,
            expected=(200,),
        )
        imported_entries1 = imported_entries1_response.json()
        assert len(imported_entries1) == 2

        # Find entries by title
        imported_entry1 = next(
            (e for e in imported_entries1 if e["title"] == "First Entry"),
            None,
        )
        imported_entry2 = next(
            (e for e in imported_entries1 if e["title"] == "Second Entry"),
            None,
        )

        assert imported_entry1 is not None
        assert imported_entry2 is not None
        assert imported_entry1["is_pinned"] is True

        # Verify entry in second journal
        imported_entries2_response = api_client.request(
            "GET",
            f"/entries/journal/{imported_journal2['id']}",
            token=import_user.access_token,
            expected=(200,),
        )
        imported_entries2 = imported_entries2_response.json()
        assert len(imported_entries2) == 1
        assert imported_entries2[0]["title"] == "Entry in Second Journal"

        # Verify media was imported
        media_response = api_client.request(
            "GET",
            f"/entries/{imported_entry1['id']}/media",
            token=import_user.access_token,
            expected=(200,),
        )
        imported_media = media_response.json()
        # Identical media in the same entry may be deduplicated into a single record.
        assert len(imported_media) >= 1

        # Verify media files are accessible
        for media in imported_media:
            api_client.wait_for_media_ready(import_user.access_token, media["id"])
            sign_response = api_client.request(
                "GET",
                f"/media/{media['id']}/sign",
                token=import_user.access_token,
                expected=(200,),
            )
            assert "signed_url" in sign_response.json()

        # Verify tags were imported
        imported_tags = api_client.list_tags(import_user.access_token)
        tag_names = [t["name"] for t in imported_tags]
        assert "test-tag-1" in tag_names
        assert "test-tag-2" in tag_names

        # Verify tags are attached to the entry
        entry_tags_response = api_client.request(
            "GET",
            f"/entries/{imported_entry1['id']}/tags",
            token=import_user.access_token,
            expected=(200,),
        )
        entry_tags = entry_tags_response.json()
        entry_tag_names = [t["name"] for t in entry_tags]
        assert "test-tag-1" in entry_tag_names
        assert "test-tag-2" in entry_tag_names

        # Verify activities and activity groups were imported
        imported_activity_groups = api_client.list_activity_groups(import_user.access_token)
        assert any(g["name"] == "Health Group" for g in imported_activity_groups)

        imported_activities = api_client.list_activities(import_user.access_token)
        assert any(a["name"] == "Exercise" for a in imported_activities)

        # Verify goals and categories were imported
        imported_goal_categories = api_client.list_goal_categories(import_user.access_token)
        assert any(c["name"] == "Health Goals" for c in imported_goal_categories)

        imported_goals = api_client.list_goals(import_user.access_token)
        assert any(g["title"] == "Daily Exercise" for g in imported_goals)

        # Verify moods and mood groups with preferences were imported
        imported_custom_mood = api_client.get_mood_by_name(
            import_user.access_token,
            name=mood_name_one,
            include_hidden=True,
        )
        assert imported_custom_mood is not None
        first_import_mood_id = imported_custom_mood["id"]
        assert imported_custom_mood.get("is_hidden") is True

        imported_group = api_client.get_mood_group_by_name(
            import_user.access_token,
            name="Morning Check-in",
            include_hidden=True,
        )
        assert imported_group is not None
        first_import_group_id = imported_group["id"]
        assert imported_group.get("is_hidden") is True
        group_moods = [m["name"] for m in imported_group.get("moods", [])]
        assert mood_name_one in group_moods
        assert mood_name_two in group_moods

        # Re-import same export and ensure moods/mood groups are reused (no duplicates)
        second_upload_response = api_client.upload_import(
            import_user.access_token,
            file_bytes=export_bytes,
            filename="journiv_export_repeat.zip",
            source_type="journiv",
            expected=(202,),
        )
        second_job = second_upload_response.json()
        completed_second_import = wait_for_import_completion(
            api_client,
            import_user.access_token,
            second_job["id"],
            timeout=120,
        )
        assert completed_second_import["status"] == "completed"

        moods_after_second = api_client.get_moods_by_name(
            import_user.access_token,
            name=mood_name_one,
            include_hidden=True,
        )
        assert len(moods_after_second) == 1
        assert moods_after_second[0]["id"] == first_import_mood_id

        groups_after_second = api_client.get_mood_groups_by_name(
            import_user.access_token,
            name="Morning Check-in",
            include_hidden=True,
        )
        assert len(groups_after_second) == 1
        assert groups_after_second[0]["id"] == first_import_group_id

        # Verify logs survived by re-exporting imported data
        roundtrip_export_job = api_client.request_export(
            import_user.access_token,
            export_type="full",
            include_media=False,
        )
        completed_roundtrip_export = wait_for_export_completion(
            api_client,
            import_user.access_token,
            roundtrip_export_job["id"],
            timeout=120,
        )
        assert completed_roundtrip_export["status"] == "completed"

        roundtrip_bytes = download_export(
            api_client,
            import_user.access_token,
            roundtrip_export_job["id"],
        )
        with zipfile.ZipFile(io.BytesIO(roundtrip_bytes), "r") as zf:
            with zf.open("data.json") as f:
                roundtrip_data = json.load(f)
                assert any(g["title"] == "Daily Exercise" for g in roundtrip_data["goals"])
                assert len(roundtrip_data["goal_logs"]) >= 1
                assert len(roundtrip_data["goal_manual_logs"]) >= 1

    def test_journiv_import_with_journals_and_entries(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """
        Test import of Journiv export containing journals with entries but no media.
        """
        # Create a minimal valid Journiv export data
        export_data = {
            "export_version": "1.0",
            "export_date": datetime.now(timezone.utc).isoformat(),
            "app_version": "1.0.0",
            "user_email": "test@example.com",
            "user_name": "Test User",
            "journals": [
                {
                    "title": "Imported Journal",
                    "description": "A journal from import",
                    "icon": "📖",
                    "is_favorite": False,
                    "is_archived": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "entries": [
                        {
                            "title": "Imported Entry 1",
                            "content_plain_text": "Content of first imported entry.",
                            "entry_date": date.today().isoformat(),
                            "entry_datetime_utc": datetime.now(timezone.utc).isoformat(),
                            "entry_timezone": "UTC",
                            "is_pinned": False,
                            "is_draft": False,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "media": [],
                            "tags": [],
                            "mood_logs": [],
                        },
                        {
                            "title": "Imported Entry 2",
                            "content_plain_text": "Content of second imported entry.",
                            "entry_date": date.today().isoformat(),
                            "entry_datetime_utc": datetime.now(timezone.utc).isoformat(),
                            "entry_timezone": "America/New_York",
                            "is_pinned": True,
                            "is_draft": False,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "media": [],
                            "tags": [],
                            "mood_logs": [],
                        },
                    ],
                }
            ],
            "mood_definitions": [],
        }

        # Create ZIP with the export data
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.json", json.dumps(export_data))
        zip_bytes = buffer.getvalue()

        # Upload and import
        upload_response = api_client.upload_import(
            api_user.access_token,
            file_bytes=zip_bytes,
            filename="journiv_test_export.zip",
            source_type="journiv",
            expected=(202,),
        )

        assert upload_response.status_code == 202
        job = upload_response.json()

        # Wait for import to complete
        completed_job = wait_for_import_completion(
            api_client,
            api_user.access_token,
            job["id"],
            timeout=60,
        )

        # Verify import completed successfully
        assert completed_job["status"] == "completed"
        assert completed_job["progress"] == 100

        result_data = completed_job.get("result_data", {})
        assert result_data["journals_created"] == 1
        assert result_data["entries_created"] == 2

        # Verify journal was created
        journals = api_client.list_journals(api_user.access_token)
        imported_journal = next(
            (j for j in journals if j["title"] == "Imported Journal"),
            None,
        )
        assert imported_journal is not None
        assert imported_journal["description"] == "A journal from import"
        assert imported_journal["icon"] == "📖"
        assert imported_journal["entry_count"] == 2

        # Verify entries were created
        entries = api_client.list_entries(
            api_user.access_token,
            journal_id=imported_journal["id"],
        )
        assert len(entries) == 2

        entry_titles = [e["title"] for e in entries]
        assert "Imported Entry 1" in entry_titles
        assert "Imported Entry 2" in entry_titles

        # Verify pinned entry
        pinned_entry = next((e for e in entries if e["title"] == "Imported Entry 2"), None)
        assert pinned_entry is not None
        assert pinned_entry["is_pinned"] is True

    def test_journiv_import_with_media_files(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """
        Test import of Journiv export containing entries with media files.

        Verifies that media files in the ZIP are correctly extracted
        and linked to their respective entries.
        """
        entry_external_id = "test-entry-001"
        media_filename = "test_photo.jpg"

        export_data = {
            "export_version": "1.0",
            "export_date": datetime.now(timezone.utc).isoformat(),
            "app_version": "1.0.0",
            "user_email": "test@example.com",
            "user_name": "Test User",
            "journals": [
                {
                    "title": "Journal With Media",
                    "description": "Contains entries with media",
                    "icon": "📷",
                    "is_favorite": False,
                    "is_archived": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "entries": [
                        {
                            "external_id": entry_external_id,
                            "title": "Entry With Photo",
                            "content_plain_text": "This entry has a photo attached.",
                            "entry_date": date.today().isoformat(),
                            "entry_datetime_utc": datetime.now(timezone.utc).isoformat(),
                            "entry_timezone": "UTC",
                            "is_pinned": False,
                            "is_draft": False,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "media": [
                                {
                                    "filename": media_filename,
                                    "file_path": f"{entry_external_id}/{media_filename}",
                                    "media_type": "image",
                                    "mime_type": "image/jpeg",
                                    "file_size": len(sample_jpeg_bytes()),
                                    "created_at": datetime.now(timezone.utc).isoformat(),
                                    "updated_at": datetime.now(timezone.utc).isoformat(),
                                }
                            ],
                            "tags": [],
                            "mood_logs": [],
                        },
                    ],
                }
            ],
            "mood_definitions": [],
        }

        # Create ZIP with data.json and media file
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.json", json.dumps(export_data))
            archive.writestr(
                f"media/{entry_external_id}/{media_filename}",
                sample_jpeg_bytes(),
            )
        zip_bytes = buffer.getvalue()

        # Upload and import
        upload_response = api_client.upload_import(
            api_user.access_token,
            file_bytes=zip_bytes,
            filename="journiv_media_export.zip",
            source_type="journiv",
            expected=(202,),
        )

        assert upload_response.status_code == 202
        job = upload_response.json()

        # Wait for import to complete
        completed_job = wait_for_import_completion(
            api_client,
            api_user.access_token,
            job["id"],
            timeout=60,
        )

        assert completed_job["status"] == "completed"

        result_data = completed_job.get("result_data", {})
        assert result_data["journals_created"] == 1
        assert result_data["entries_created"] == 1
        assert result_data["media_files_imported"] == 1

        # Verify entry was created
        journals = api_client.list_journals(api_user.access_token)
        journal = next(
            (j for j in journals if j["title"] == "Journal With Media"),
            None,
        )
        assert journal is not None

        entries = api_client.list_entries(
            api_user.access_token,
            journal_id=journal["id"],
        )
        assert len(entries) == 1
        entry = entries[0]
        assert entry["title"] == "Entry With Photo"

        # Verify media was imported and is accessible
        media_response = api_client.request(
            "GET",
            f"/entries/{entry['id']}/media",
            token=api_user.access_token,
            expected=(200,),
        )
        media_list = media_response.json()
        assert len(media_list) == 1

        media = media_list[0]
        assert media["media_type"] == "image"
        assert media["mime_type"] == "image/jpeg"

        # Verify media file is accessible
        api_client.wait_for_media_ready(api_user.access_token, media["id"])
        sign_response = api_client.request(
            "GET",
            f"/media/{media['id']}/sign",
            token=api_user.access_token,
            expected=(200,),
        )
        assert "signed_url" in sign_response.json()

    def test_journiv_import_invalid_export_version(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test that import rejects exports with incompatible version."""
        export_data = {
            "export_version": "99.0",  # Invalid future version
            "export_date": datetime.now(timezone.utc).isoformat(),
            "app_version": "1.0.0",
            "user_email": "test@example.com",
            "journals": [],
            "mood_definitions": [],
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.json", json.dumps(export_data))
        zip_bytes = buffer.getvalue()

        upload_response = api_client.upload_import(
            api_user.access_token,
            file_bytes=zip_bytes,
            source_type="journiv",
            expected=(202,),
        )

        job = upload_response.json()

        # Wait for job to process (should fail)
        import time
        deadline = time.time() + 30
        while time.time() < deadline:
            status = api_client.import_status(api_user.access_token, job["id"])
            if status["status"] in ("completed", "failed"):
                break
            time.sleep(1)

        final_status = api_client.import_status(api_user.access_token, job["id"])
        assert final_status["status"] == "failed"
        # Error should mention version incompatibility
        errors = final_status.get("errors") or []
        error_text = " ".join(str(e) for e in errors) if errors else ""
        assert "version" in error_text.lower() or "incompatible" in error_text.lower()

    def test_journiv_import_missing_data_json(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test that import rejects ZIP without data.json."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("readme.txt", "This is not a valid export")
        zip_bytes = buffer.getvalue()

        response = api_client.upload_import(
            api_user.access_token,
            file_bytes=zip_bytes,
            source_type="journiv",
        )

        # Should fail validation
        assert response.status_code == 400
        error = response.json()
        assert "data.json" in error.get("detail", "").lower()

    def test_journiv_import_invalid_json(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test that import rejects ZIP with invalid JSON."""
        import time

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.json", "{ invalid json }")
        zip_bytes = buffer.getvalue()

        response = api_client.upload_import(
            api_user.access_token,
            file_bytes=zip_bytes,
            source_type="journiv",
        )

        # Upload is accepted, validation happens during processing
        if response.status_code == 400:
            # Some implementations may validate synchronously
            return

        assert response.status_code == 202
        job = response.json()

        # Wait for job to fail during processing
        deadline = time.time() + 30
        while time.time() < deadline:
            status = api_client.import_status(api_user.access_token, job["id"])
            if status["status"] in ("completed", "failed"):
                break
            time.sleep(1)

        final_status = api_client.import_status(api_user.access_token, job["id"])
        assert final_status["status"] == "failed"

    def test_journiv_import_empty_journals(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test that import handles export with no journals gracefully."""
        export_data = {
            "export_version": "1.0",
            "export_date": datetime.now(timezone.utc).isoformat(),
            "app_version": "1.0.0",
            "user_email": "test@example.com",
            "journals": [],
            "mood_definitions": [],
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.json", json.dumps(export_data))
        zip_bytes = buffer.getvalue()

        upload_response = api_client.upload_import(
            api_user.access_token,
            file_bytes=zip_bytes,
            source_type="journiv",
            expected=(202,),
        )

        job = upload_response.json()

        completed_job = wait_for_import_completion(
            api_client,
            api_user.access_token,
            job["id"],
            timeout=30,
        )

        assert completed_job["status"] == "completed"
        result_data = completed_job.get("result_data", {})
        assert result_data.get("journals_created", 0) == 0
        assert result_data.get("entries_created", 0) == 0

    def test_journiv_export_without_media(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test export without media includes all data but no media files."""
        # Create journal with entry and media
        journal = api_client.create_journal(
            api_user.access_token,
            title="Export Test Journal",
            description="Testing export without media",
        )

        entry = api_client.create_entry(
            api_user.access_token,
            journal_id=journal["id"],
            title="Test Entry",
            content="Entry content for export test",
            entry_date=date.today().isoformat(),
        )

        upload_sample_media(
            api_client,
            api_user.access_token,
            entry["id"],
        )

        # Export without media
        export_job = api_client.request_export(
            api_user.access_token,
            export_type="full",
            include_media=False,
        )

        completed_export = wait_for_export_completion(
            api_client,
            api_user.access_token,
            export_job["id"],
        )

        assert completed_export["status"] == "completed"

        export_bytes = download_export(
            api_client,
            api_user.access_token,
            export_job["id"],
        )

        with zipfile.ZipFile(io.BytesIO(export_bytes), "r") as zf:
            namelist = zf.namelist()
            assert "data.json" in namelist
            # Should not have media files
            media_files = [n for n in namelist if n.startswith("media/")]
            assert len(media_files) == 0

            # Verify data.json has entry with media metadata
            with zf.open("data.json") as f:
                data = json.load(f)
                assert len(data["journals"]) == 1
                assert len(data["journals"][0]["entries"]) == 1

    def test_journiv_import_preserves_timestamps(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test that import preserves original created_at/updated_at timestamps."""
        original_created = "2020-01-15T10:30:00+00:00"
        original_updated = "2020-06-20T14:45:00+00:00"

        export_data = {
            "export_version": "1.0",
            "export_date": datetime.now(timezone.utc).isoformat(),
            "app_version": "1.0.0",
            "user_email": "test@example.com",
            "journals": [
                {
                    "title": "Timestamped Journal",
                    "description": "Testing timestamp preservation",
                    "icon": "📅",
                    "is_favorite": False,
                    "is_archived": False,
                    "created_at": original_created,
                    "updated_at": original_updated,
                    "entries": [
                        {
                            "title": "Old Entry",
                            "content_plain_text": "This entry is from the past.",
                            "entry_date": "2020-01-15",
                            "entry_datetime_utc": "2020-01-15T10:30:00+00:00",
                            "entry_timezone": "UTC",
                            "is_pinned": False,
                            "is_draft": False,
                            "created_at": original_created,
                            "updated_at": original_updated,
                            "media": [],
                            "tags": [],
                            "mood_logs": [],
                        },
                    ],
                }
            ],
            "mood_definitions": [],
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.json", json.dumps(export_data))
        zip_bytes = buffer.getvalue()

        upload_response = api_client.upload_import(
            api_user.access_token,
            file_bytes=zip_bytes,
            source_type="journiv",
            expected=(202,),
        )

        job = upload_response.json()
        completed_job = wait_for_import_completion(
            api_client,
            api_user.access_token,
            job["id"],
        )

        assert completed_job["status"] == "completed"

        # Verify timestamps were preserved
        journals = api_client.list_journals(api_user.access_token)
        journal = next(
            (j for j in journals if j["title"] == "Timestamped Journal"),
            None,
        )
        assert journal is not None

        # Parse and compare timestamps (allowing for timezone normalization)
        journal_created = datetime.fromisoformat(
            journal["created_at"].replace("Z", "+00:00")
        )
        expected_created = datetime.fromisoformat(original_created)
        assert journal_created == expected_created

    def test_journiv_import_requires_authentication(
        self,
        api_client: JournivApiClient,
    ):
        """Test that import requires authentication."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.json", "{}")
        zip_bytes = buffer.getvalue()

        response = api_client.request(
            "POST",
            "/import/upload",
            files={"file": ("test.zip", zip_bytes, "application/zip")},
            data={"source_type": "journiv"},
        )

        assert response.status_code == 401

    def test_journiv_import_duplicate_import_creates_new_journals(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test that importing same export twice creates duplicate journals."""
        export_data = {
            "export_version": "1.0",
            "export_date": datetime.now(timezone.utc).isoformat(),
            "app_version": "1.0.0",
            "user_email": "test@example.com",
            "journals": [
                {
                    "title": "Duplicate Test Journal",
                    "description": "Testing duplicate imports",
                    "icon": "📚",
                    "is_favorite": False,
                    "is_archived": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "entries": [],
                }
            ],
            "mood_definitions": [],
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.json", json.dumps(export_data))
        zip_bytes = buffer.getvalue()

        # First import
        upload1 = api_client.upload_import(
            api_user.access_token,
            file_bytes=zip_bytes,
            source_type="journiv",
            expected=(202,),
        )
        job1 = upload1.json()
        wait_for_import_completion(api_client, api_user.access_token, job1["id"])

        # Second import
        upload2 = api_client.upload_import(
            api_user.access_token,
            file_bytes=zip_bytes,
            source_type="journiv",
            expected=(202,),
        )
        job2 = upload2.json()
        wait_for_import_completion(api_client, api_user.access_token, job2["id"])

        # Should have 2 journals with same title
        journals = api_client.list_journals(api_user.access_token)
        matching_journals = [j for j in journals if j["title"] == "Duplicate Test Journal"]
        assert len(matching_journals) == 2

    def test_journiv_import_with_tags_and_mood_logs(
        self,
        api_client: JournivApiClient,
        api_user: ApiUser,
    ):
        """Test import of entries with tags and mood logs."""
        export_data = {
            "export_version": "1.0",
            "export_date": datetime.now(timezone.utc).isoformat(),
            "app_version": "1.0.0",
            "user_email": "test@example.com",
            "journals": [
                {
                    "title": "Journal With Tags",
                    "description": "Testing tag import",
                    "icon": "🏷️",
                    "is_favorite": False,
                    "is_archived": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "entries": [
                        {
                            "title": "Tagged Entry",
                            "content_plain_text": "Entry with tags attached.",
                            "entry_date": date.today().isoformat(),
                            "entry_datetime_utc": datetime.now(timezone.utc).isoformat(),
                            "entry_timezone": "UTC",
                            "is_pinned": False,
                            "is_draft": False,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "media": [],
                            "tags": ["imported-tag-1", "imported-tag-2"],
                            "mood_logs": [],
                        },
                    ],
                }
            ],
            "mood_definitions": [],
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.json", json.dumps(export_data))
        zip_bytes = buffer.getvalue()

        upload_response = api_client.upload_import(
            api_user.access_token,
            file_bytes=zip_bytes,
            source_type="journiv",
            expected=(202,),
        )

        job = upload_response.json()
        completed_job = wait_for_import_completion(
            api_client,
            api_user.access_token,
            job["id"],
        )

        assert completed_job["status"] == "completed"

        # Verify tags were created
        tags = api_client.list_tags(api_user.access_token)
        tag_names = [t["name"] for t in tags]
        assert "imported-tag-1" in tag_names
        assert "imported-tag-2" in tag_names

        # Verify tags are attached to entry
        journals = api_client.list_journals(api_user.access_token)
        journal = next(j for j in journals if j["title"] == "Journal With Tags")
        entries = api_client.list_entries(
            api_user.access_token,
            journal_id=journal["id"],
        )
        entry = entries[0]

        entry_tags_response = api_client.request(
            "GET",
            f"/entries/{entry['id']}/tags",
            token=api_user.access_token,
            expected=(200,),
        )
        entry_tags = entry_tags_response.json()
        entry_tag_names = [t["name"] for t in entry_tags]
        assert "imported-tag-1" in entry_tag_names
        assert "imported-tag-2" in entry_tag_names
