"""
End-to-end integration tests for Daylio import using real fixture exports.
"""

from __future__ import annotations

import base64
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.data_transfer.daylio.mappers import DaylioToJournivMapper
from app.data_transfer.daylio.models import DaylioBackup
from tests.integration.helpers import wait_for_import_completion
from tests.lib import ApiUser, JournivApiClient

_PREDEFINED_DAYLIO_MOOD_NAMES = {
    1: "Rad",
    2: "Good",
    3: "Meh",
    4: "Bad",
    5: "Awful",
}

_DAYLIO_TO_JOURNIV_OVERRIDES = {
    "rad": "Awesome",
}

_DAYLIO_FIXTURE_FILES = (
    "android_backup.daylio",
    "ios_backup.daylio",
)


def _fixture_path(filename: str) -> Path:
    return Path(__file__).parent.parent / "fixtures" / filename


def _load_daylio_backup_from_fixture(fixture_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(fixture_path) as archive:
        raw = archive.read("backup.daylio")
    return json.loads(base64.b64decode(raw))


def _total_goal_logs(
    api_client: JournivApiClient,
    token: str,
    goals: list[dict[str, Any]],
) -> int:
    total = 0
    for goal in goals:
        total += len(api_client.list_goal_logs(token, goal["id"], limit=365))
    return total


def _should_create_entry(day_entry: dict[str, Any]) -> bool:
    note = (day_entry.get("note") or "").strip()
    note_title = (day_entry.get("note_title") or "").strip()
    has_assets = bool(day_entry.get("assets"))
    return bool(note or note_title or has_assets)


def _should_create_moment(day_entry: dict[str, Any]) -> bool:
    return day_entry.get("mood") is not None or bool(day_entry.get("tags"))


def _normalize_daylio_mood_name(name: str) -> str:
    return _DAYLIO_TO_JOURNIV_OVERRIDES.get(name.strip().lower(), name.strip())


def _expected_mood_name_for_entry(
    day_entry: dict[str, Any],
    custom_moods_by_id: dict[int, dict[str, Any]],
) -> str | None:
    mood_ref = day_entry.get("mood")
    if mood_ref is None:
        return None

    mood_obj = custom_moods_by_id.get(mood_ref)
    if mood_obj:
        custom_name = (mood_obj.get("custom_name") or "").strip()
        if custom_name:
            return _normalize_daylio_mood_name(custom_name)
        predefined_id = mood_obj.get("predefined_name_id")
        predefined_name = _PREDEFINED_DAYLIO_MOOD_NAMES.get(predefined_id)
        if predefined_name:
            return _normalize_daylio_mood_name(predefined_name)
        return None

    predefined_name = _PREDEFINED_DAYLIO_MOOD_NAMES.get(mood_ref)
    if predefined_name:
        return _normalize_daylio_mood_name(predefined_name)
    return None


@pytest.mark.parametrize("fixture_name", _DAYLIO_FIXTURE_FILES)
def test_daylio_import_from_real_fixture_file(
    fixture_name: str,
    api_client: JournivApiClient,
    api_user: ApiUser,
) -> None:
    fixture_path = _fixture_path(fixture_name)
    if not fixture_path.exists():
        pytest.skip(f"Daylio fixture not found: {fixture_path}")

    fixture_bytes = fixture_path.read_bytes()
    backup = _load_daylio_backup_from_fixture(fixture_path)
    backup_model = DaylioBackup.model_validate(backup)

    day_entries = backup.get("dayEntries", [])
    custom_moods_by_id = {m["id"]: m for m in backup.get("customMoods", [])}

    expected_entries = sum(1 for entry in day_entries if _should_create_entry(entry))
    expected_moments = sum(
        1
        for entry in day_entries
        if _should_create_entry(entry) or _should_create_moment(entry)
    )
    expected_asset_refs = sum(len(entry.get("assets") or []) for entry in day_entries)
    mapper_ctx = DaylioToJournivMapper._build_context(backup_model)
    mapper_import_timestamp = datetime.now(tz=timezone.utc)
    expected_goals = len(
        DaylioToJournivMapper._map_goals(
            backup_model,
            mapper_import_timestamp,
            mapper_ctx,
        )
    )
    expected_goal_logs = len(
        DaylioToJournivMapper._merge_goal_logs(
            daily_logs=DaylioToJournivMapper._map_goal_logs(
                backup_model,
                mapper_import_timestamp,
            ),
            weekly_logs=DaylioToJournivMapper._map_goal_success_weeks(
                backup_model,
                mapper_import_timestamp,
            ),
        )
    )
    expected_linked_goal_logs = sum(
        1
        for log in DaylioToJournivMapper._map_goal_logs(
            backup_model,
            mapper_import_timestamp,
        )
        if log.moment_external_id
    )
    pre_import_goals = api_client.list_goals(api_user.access_token)
    pre_import_total_goal_logs = _total_goal_logs(
        api_client,
        api_user.access_token,
        pre_import_goals,
    )

    expected_mood_names = {
        mood_name
        for entry in day_entries
        if _should_create_entry(entry) or _should_create_moment(entry)
        if (mood_name := _expected_mood_name_for_entry(entry, custom_moods_by_id))
        is not None
    }

    upload_response = api_client.upload_import(
        api_user.access_token,
        file_bytes=fixture_bytes,
        filename=fixture_name,
        source_type="daylio",
        expected=(202,),
    )
    job = upload_response.json()
    assert job["source_type"] == "daylio"
    assert job["id"]

    completed_job = wait_for_import_completion(
        api_client,
        api_user.access_token,
        job["id"],
        timeout=90,
    )

    assert completed_job["status"] == "completed"
    assert completed_job["progress"] == 100

    result_data = completed_job.get("result_data", {})
    assert result_data["journals_created"] == 1
    assert result_data["entries_created"] == expected_entries
    assert result_data["goals_created"] == expected_goals
    assert result_data["goal_logs_created"] == expected_goal_logs
    assert result_data["goal_manual_logs_created"] == 0
    assert result_data.get("media_files_imported", 0) + result_data.get(
        "media_files_skipped", 0
    ) == (expected_asset_refs)

    journals = api_client.list_journals(api_user.access_token)
    imported_journals = [
        journal
        for journal in journals
        if "Imported from Daylio" in (journal.get("description") or "")
    ]
    assert len(imported_journals) == 1

    entries = api_client.list_entries(api_user.access_token)
    assert len(entries) == expected_entries

    post_import_goals = api_client.list_goals(api_user.access_token)
    post_import_total_goal_logs = _total_goal_logs(
        api_client,
        api_user.access_token,
        post_import_goals,
    )
    assert post_import_total_goal_logs - pre_import_total_goal_logs == expected_goal_logs

    imported_goal_logs = []
    for goal in post_import_goals:
        imported_goal_logs.extend(api_client.list_goal_logs(api_user.access_token, goal["id"], limit=365))
    linked_goal_logs = [log for log in imported_goal_logs if log.get("moment_id") is not None]
    assert len(linked_goal_logs) >= expected_linked_goal_logs

    moments = api_client.list_moments(api_user.access_token, limit=200)
    assert len(moments) == expected_moments

    mood_lookup = {
        mood["id"]: mood["name"]
        for mood in api_client.list_moods(api_user.access_token)
    }
    imported_mood_names: set[str] = set()
    imported_media_total = 0
    for moment in moments:
        moment_id = moment["id"]
        moment_detail = api_client.request(
            "GET",
            f"/moments/{moment_id}",
            token=api_user.access_token,
            expected=(200,),
        ).json()
        primary_mood_name = moment_detail.get("primary_mood_name")
        if primary_mood_name:
            imported_mood_names.add(primary_mood_name)
        primary_mood_id = moment_detail.get("primary_mood_id")
        if primary_mood_id and primary_mood_id in mood_lookup:
            imported_mood_names.add(mood_lookup[primary_mood_id])

        for item in moment_detail.get("mood_activity") or []:
            mood_name = item.get("mood_name")
            if mood_name:
                imported_mood_names.add(mood_name)
            mood_id = item.get("mood_id")
            if mood_id and mood_id in mood_lookup:
                imported_mood_names.add(mood_lookup[mood_id])

        moment_media = api_client.request(
            "GET",
            f"/moments/{moment_id}/media",
            token=api_user.access_token,
            expected=(200,),
        ).json()
        imported_media_total += len(moment_media)

    assert expected_mood_names.issubset(imported_mood_names)
    assert imported_media_total == expected_asset_refs
