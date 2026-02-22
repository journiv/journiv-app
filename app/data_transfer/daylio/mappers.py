"""
Daylio to Journiv mappers.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logging_config import log_warning
from app.core.time_utils import utc_now
from app.models.enums import GoalFrequency, GoalLogSource, GoalLogStatus, GoalType
from app.schemas.dto import (
    ActivityDTO,
    ActivityGroupDTO,
    EntryDTO,
    GoalDTO,
    GoalLogDTO,
    JournalDTO,
    JournivExportDTO,
    MomentDTO,
    MomentMediaDTO,
    MomentMoodActivityDTO,
    MoodDefinitionDTO,
    MoodGroupDTO,
    MoodGroupLinkDTO,
)
from app.utils.import_export.constants import ExportConfig
from app.utils.import_export.media_handler import MediaHandler
from app.utils.quill_delta import wrap_plain_text

from .html_to_delta import html_to_delta
from .models import (
    DaylioBackup,
    DaylioDayEntry,
)

_PREDEFINED_MOOD_NAMES = {
    1: "Rad",
    2: "Good",
    3: "Meh",
    4: "Bad",
    5: "Awful",
}

_DAYLIO_TO_SYSTEM_OVERRIDES = {
    "rad": "Awesome",
}

_SYSTEM_MOOD_META: Dict[str, tuple[int, str]] = {
    "awesome": (5, "positive"),
    "good": (4, "positive"),
    "meh": (3, "neutral"),
    "bad": (2, "negative"),
    "awful": (1, "negative"),
}


@dataclass
class DaylioMappingContext:
    assets_by_id: Dict[int, Dict[str, Any]]
    tags_by_id: Dict[int, str]
    tag_groups_by_id: Dict[int, str]
    moods_by_id: Dict[int, Dict[str, Any]]


class DaylioToJournivMapper:
    @staticmethod
    def _normalize_daylio_mood_name(
        *,
        custom_name: Optional[str],
        predefined_name_id: Optional[int],
        fallback_label: str,
    ) -> str:
        name = (custom_name or "").strip()
        if not name:
            name = _PREDEFINED_MOOD_NAMES.get(predefined_name_id or -1, fallback_label)
        return _DAYLIO_TO_SYSTEM_OVERRIDES.get(name.lower(), name)

    @staticmethod
    def build_export(
        backup: DaylioBackup,
        *,
        journal_title: str,
        import_timestamp: datetime,
        user_email: str,
        user_name: Optional[str],
        app_version: str,
        media_dir: Optional[Path] = None,
    ) -> JournivExportDTO:
        ctx = DaylioToJournivMapper._build_context(backup)

        moods, mood_links, mood_groups = DaylioToJournivMapper._map_moods_with_unmatched_group(
            backup,
            import_timestamp,
        )

        activity_groups = DaylioToJournivMapper._map_activity_groups(backup, import_timestamp)
        activities = DaylioToJournivMapper._map_activities(backup, import_timestamp)

        goals = DaylioToJournivMapper._map_goals(backup, import_timestamp, ctx)
        goal_logs = DaylioToJournivMapper._map_goal_logs(backup, import_timestamp)

        journal = DaylioToJournivMapper._map_journal(
            backup,
            ctx,
            journal_title=journal_title,
            import_timestamp=import_timestamp,
        )

        timeline_moments: List[MomentDTO] = []
        for day_entry in backup.dayEntries:
            if DaylioToJournivMapper._should_create_entry(day_entry):
                moment = DaylioToJournivMapper._map_moment(
                    day_entry,
                    ctx,
                    import_timestamp=import_timestamp,
                    media_dir=media_dir,
                    attach_media=True,
                )
                moment.entry = DaylioToJournivMapper._map_entry(
                    day_entry,
                    import_timestamp=import_timestamp,
                    journal_external_id=journal.external_id,
                    media_items=moment.media,
                )
                timeline_moments.append(moment)
                continue
            if DaylioToJournivMapper._should_create_moment(day_entry):
                timeline_moments.append(
                    DaylioToJournivMapper._map_moment(
                        day_entry,
                        ctx,
                        import_timestamp=import_timestamp,
                        media_dir=media_dir,
                        attach_media=True,
                    )
                )

        return JournivExportDTO(
            export_version=ExportConfig.EXPORT_VERSION,
            export_date=utc_now(),
            app_version=app_version,
            user_email=user_email,
            user_name=user_name,
            user_settings=None,
            journals=[journal],
            mood_definitions=moods,
            mood_groups=mood_groups,
            mood_group_links=mood_links,
            mood_group_preferences=[],
            mood_preferences=[],
            activities=activities,
            activity_groups=activity_groups,
            goals=goals,
            goal_logs=goal_logs,
            goal_manual_logs=[],
            goal_categories=[],
            moments=timeline_moments,
            stats=None,
        )

    @staticmethod
    def _build_context(backup: DaylioBackup) -> DaylioMappingContext:
        assets_by_id = {asset.id: asset.model_dump() for asset in backup.assets}
        tags_by_id = {tag.id: tag.name for tag in backup.tags}
        tag_groups_by_id = {group.id: group.name for group in backup.tag_groups}
        moods_by_id = {mood.id: mood.model_dump() for mood in backup.customMoods}
        return DaylioMappingContext(
            assets_by_id=assets_by_id,
            tags_by_id=tags_by_id,
            tag_groups_by_id=tag_groups_by_id,
            moods_by_id=moods_by_id,
        )

    @staticmethod
    def _map_moods_with_unmatched_group(
        backup: DaylioBackup,
        import_timestamp: datetime,
    ) -> tuple[List[MoodDefinitionDTO], List[MoodGroupLinkDTO], List[MoodGroupDTO]]:
        moods: List[MoodDefinitionDTO] = []
        mood_links: List[MoodGroupLinkDTO] = []
        mood_groups: List[MoodGroupDTO] = []
        unmatched_group_external_id = "daylio-unmatched"
        unmatched_group_position = 999
        unmatched_group_created = False
        for mood in backup.customMoods:
            mapped_name = DaylioToJournivMapper._normalize_daylio_mood_name(
                custom_name=mood.custom_name,
                predefined_name_id=mood.predefined_name_id,
                fallback_label=f"Daylio Mood {mood.id}",
            )
            is_system_match = mapped_name.lower() in {"awful", "bad", "meh", "good", "awesome"}
            mood_group_id = mood.mood_group_id if mood.mood_group_id is not None else 3
            mood_meta = _SYSTEM_MOOD_META.get(mapped_name.lower())
            if mood_meta:
                score, category = mood_meta
            else:
                score = max(1, min(5, mood_group_id))
                category = "neutral"
                if mood.mood_group_id in (1, 2):
                    category = "negative"
                elif mood.mood_group_id in (4, 5):
                    category = "positive"
            position = getattr(mood, "mood_group_order", 0) or 0
            moods.append(
                MoodDefinitionDTO(
                    name=mapped_name,
                    category=category,
                    icon=None,
                    key=f"daylio:{mapped_name.lower()}",
                    color_value=None,
                    score=score,
                    position=position,
                    is_active=mood.state == 0,
                    is_custom=True,
                    created_at=import_timestamp,
                    updated_at=import_timestamp,
                    external_id=str(mood.id),
                )
            )
            if not is_system_match:
                if not unmatched_group_created:
                    mood_groups.append(
                        MoodGroupDTO(
                            name="Daylio (Unmatched)",
                            icon=None,
                            color_value=None,
                            position=unmatched_group_position,
                            is_custom=True,
                            created_at=import_timestamp,
                            updated_at=import_timestamp,
                            external_id=unmatched_group_external_id,
                        )
                    )
                    unmatched_group_created = True
                mood_links.append(
                    MoodGroupLinkDTO(
                        mood_group_external_id=unmatched_group_external_id,
                        mood_external_id=str(mood.id),
                        position=position,
                        created_at=import_timestamp,
                        updated_at=import_timestamp,
                    )
                )
        return moods, mood_links, mood_groups


    @staticmethod
    def _map_activity_groups(backup: DaylioBackup, import_timestamp: datetime) -> List[ActivityGroupDTO]:
        groups = []
        for group in backup.tag_groups:
            groups.append(
                ActivityGroupDTO(
                    name=group.name,
                    color_value=None,
                    icon=None,
                    position=group.order or 0,
                    created_at=import_timestamp,
                    updated_at=import_timestamp,
                    external_id=str(group.id),
                )
            )
        return groups

    @staticmethod
    def _map_activities(backup: DaylioBackup, import_timestamp: datetime) -> List[ActivityDTO]:
        activities = []
        for tag in backup.tags:
            activities.append(
                ActivityDTO(
                    name=tag.name,
                    icon=str(tag.icon) if tag.icon is not None else None,
                    color=None,
                    position=tag.order or 0,
                    group_external_id=str(tag.id_tag_group) if tag.id_tag_group else None,
                    created_at=import_timestamp,
                    updated_at=import_timestamp,
                    external_id=str(tag.id),
                )
            )
        return activities

    @staticmethod
    def _map_goals(
        backup: DaylioBackup,
        import_timestamp: datetime,
        ctx: DaylioMappingContext,
    ) -> List[GoalDTO]:
        goals = []
        for goal in backup.goals:
            title = (goal.name or "").strip()
            if not title and goal.id_tag:
                title = ctx.tags_by_id.get(goal.id_tag, f"Daylio Goal {goal.goal_id}")
            if not title:
                title = f"Daylio Goal {goal.goal_id}"

            reminder_time = None
            if goal.reminder_enabled and goal.reminder_hour is not None and goal.reminder_minute is not None:
                reminder_time = f"{goal.reminder_hour:02d}:{goal.reminder_minute:02d}"

            frequency = GoalFrequency.DAILY
            target = goal.repeat_value or 1
            if goal.repeat_type == 2:
                frequency = GoalFrequency.WEEKLY
            elif goal.repeat_type == 1:
                frequency = GoalFrequency.DAILY

            goals.append(
                GoalDTO(
                    title=title,
                    goal_type=GoalType.ACHIEVE,
                    frequency_type=frequency,
                    target_count=target,
                    reminder_time=reminder_time,
                    is_paused=(goal.state or 0) != 0,
                    icon=str(goal.id_icon) if goal.id_icon is not None else None,
                    color_value=None,
                    position=goal.order_number or goal.order or 0,
                    archived_at=None,
                    activity_external_id=str(goal.id_tag) if goal.id_tag else None,
                    category_external_id=None,
                    created_at=_ms_to_utc(goal.created_at) or import_timestamp,
                    updated_at=import_timestamp,
                    external_id=str(goal.goal_id),
                )
            )
        return goals

    @staticmethod
    def _map_goal_logs(backup: DaylioBackup, import_timestamp: datetime) -> List[GoalLogDTO]:
        logs = []
        for entry in backup.goalEntries:
            logged_date = date(entry.year, entry.month + 1, entry.day)
            created_at = _ms_to_utc(entry.createdAt) or import_timestamp
            logs.append(
                GoalLogDTO(
                    goal_external_id=str(entry.goalId),
                    logged_date=logged_date,
                    period_start=logged_date,
                    period_end=logged_date,
                    status=GoalLogStatus.SUCCESS,
                    count=1,
                    source=GoalLogSource.AUTO,
                    last_updated_at=created_at,
                    moment_external_id=None,
                    created_at=created_at,
                    updated_at=created_at,
                    external_id=str(entry.id),
                )
            )
        return logs

    @staticmethod
    def _map_journal(
        backup: DaylioBackup,
        ctx: DaylioMappingContext,
        *,
        journal_title: str,
        import_timestamp: datetime,
    ) -> JournalDTO:
        normalized_title = (journal_title or "").strip().lower()
        stable_title = "-".join(normalized_title.split()) if normalized_title else "default"
        journal_external_id = f"daylio-journal-{stable_title}"

        last_entry_at = None
        first_entry_at = None
        logged_times = [
            _ms_to_utc(day_entry.datetime)
            for day_entry in backup.dayEntries
            if DaylioToJournivMapper._should_create_entry(day_entry)
        ]
        logged_times = [dt for dt in logged_times if dt is not None]
        if logged_times:
            first_entry_at = min(logged_times)
            last_entry_at = max(logged_times)

        return JournalDTO(
            title=journal_title,
            description="Imported from Daylio",
            color=None,
            icon=None,
            is_favorite=False,
            is_archived=False,
            last_entry_at=last_entry_at,
            import_metadata={
                "source": "daylio",
                "source_version": backup.version,
                "imported_at": import_timestamp.isoformat().replace("+00:00", "Z"),
                "raw_export_metadata": backup.metadata,
            },
            created_at=first_entry_at or import_timestamp,
            updated_at=import_timestamp,
            external_id=journal_external_id,
        )

    @staticmethod
    def _map_entry(
        day_entry: DaylioDayEntry,
        *,
        import_timestamp: datetime,
        journal_external_id: Optional[str],
        media_items: Optional[List[MomentMediaDTO]] = None,
    ) -> EntryDTO:
        logged_at = _ms_to_utc(day_entry.datetime) or import_timestamp

        title = (day_entry.note_title or "").strip() or None
        note = (day_entry.note or "").strip()
        content_delta = html_to_delta(note) if note else wrap_plain_text(None)
        content_delta = DaylioToJournivMapper._append_media_to_entry_delta(
            content_delta=content_delta,
            media_items=media_items or [],
        )

        return EntryDTO(
            title=title,
            content_delta=content_delta,
            content_plain_text=None,
            word_count=0,
            is_draft=False,
            import_metadata={
                "source": "daylio",
                "daylio_datetime": day_entry.datetime,
                "daylio_timezone_offset_ms": day_entry.timeZoneOffset,
            },
            journal_external_id=journal_external_id,
            created_at=logged_at,
            updated_at=logged_at,
            external_id=f"daylio-entry-{day_entry.datetime}",
        )

    @staticmethod
    def _append_media_to_entry_delta(
        *,
        content_delta: Dict[str, Any],
        media_items: List[MomentMediaDTO],
    ) -> Dict[str, Any]:
        """
        Append imported media embeds to the end of entry content.

        Daylio media is attached at moment level. For entry-backed moments we append
        media placeholders so later entry edits preserve media ownership unless user
        explicitly removes embeds.
        """
        if not media_items:
            return content_delta

        delta = content_delta if isinstance(content_delta, dict) else wrap_plain_text(None)
        ops = delta.get("ops")
        if not isinstance(ops, list):
            ops = [{"insert": "\n"}]
            delta["ops"] = ops

        # Ensure we end on a newline before appending embeds.
        if not ops:
            ops.append({"insert": "\n"})
        else:
            last_insert = ops[-1].get("insert") if isinstance(ops[-1], dict) else None
            if isinstance(last_insert, dict):
                ops.append({"insert": "\n"})
            elif isinstance(last_insert, str) and not last_insert.endswith("\n"):
                ops.append({"insert": "\n"})

        for media in media_items:
            if not media.external_id:
                continue
            key = "image"
            if media.media_type == "video":
                key = "video"
            elif media.media_type == "audio":
                key = "audio"
            ops.append({"insert": {key: media.external_id}})
            ops.append({"insert": "\n"})

        return delta

    @staticmethod
    def _map_moment(
        day_entry: DaylioDayEntry,
        ctx: DaylioMappingContext,
        *,
        import_timestamp: datetime,
        media_dir: Optional[Path],
        attach_media: bool,
    ) -> MomentDTO:
        logged_at = _ms_to_utc(day_entry.datetime) or import_timestamp
        tz_offset = _offset_to_timezone(day_entry.timeZoneOffset)
        logged_date = date(day_entry.year, day_entry.month + 1, day_entry.day)
        primary_mood_name, primary_mood_external_id = DaylioToJournivMapper._resolve_day_entry_mood(
            day_entry,
            ctx,
        )

        mood_activity = []

        # Add mood to mood_activity if present
        if primary_mood_name is not None or primary_mood_external_id is not None:
            mood_activity.append(
                MomentMoodActivityDTO(
                    mood_name=primary_mood_name,
                    activity_name=None,
                    mood_external_id=primary_mood_external_id,
                    activity_external_id=None,
                )
            )

        # Add activities
        for tag_id in day_entry.tags or []:
            mood_activity.append(
                MomentMoodActivityDTO(
                    mood_name=None,
                    activity_name=None,
                    mood_external_id=None,
                    activity_external_id=str(tag_id),
                )
            )

        media = DaylioToJournivMapper._map_media(day_entry, ctx, media_dir=media_dir) if attach_media else []

        return MomentDTO(
            logged_at_utc=logged_at,
            logged_date_tz=logged_date,
            logged_timezone=tz_offset,
            note=None,
            location_json=None,
            weather_json=None,
            primary_mood_name=primary_mood_name,
            mood_activity=mood_activity,
            media=media,
            created_at=logged_at,
            updated_at=logged_at,
            external_id=f"daylio-moment-{day_entry.datetime}",
            primary_mood_external_id=primary_mood_external_id,
        )

    @staticmethod
    def _resolve_day_entry_mood(
        day_entry: DaylioDayEntry,
        ctx: DaylioMappingContext,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Resolve Daylio mood reference for a day entry.

        Daylio exports can reference a custom mood by ID or a predefined mood
        scale value. For predefined values we prefer name-based mapping.
        """
        if day_entry.mood is None:
            return None, None

        mood_ref = day_entry.mood
        mood_obj = ctx.moods_by_id.get(mood_ref)
        if mood_obj:
            mapped_name = DaylioToJournivMapper._normalize_daylio_mood_name(
                custom_name=mood_obj.get("custom_name"),
                predefined_name_id=mood_obj.get("predefined_name_id"),
                fallback_label=f"Daylio Mood {mood_ref}",
            )
            return mapped_name, str(mood_ref)

        predefined_name = _PREDEFINED_MOOD_NAMES.get(mood_ref)
        if predefined_name:
            mapped_name = DaylioToJournivMapper._normalize_daylio_mood_name(
                custom_name=predefined_name,
                predefined_name_id=None,
                fallback_label=f"Daylio Mood {mood_ref}",
            )
            return mapped_name, None

        return None, str(mood_ref)

    @staticmethod
    def _map_media(
        day_entry: DaylioDayEntry,
        ctx: DaylioMappingContext,
        *,
        media_dir: Optional[Path],
    ) -> List[MomentMediaDTO]:
        if not media_dir:
            return []
        media = []
        for asset_id in day_entry.assets or []:
            asset = ctx.assets_by_id.get(asset_id)
            if not asset:
                continue
            checksum = asset.get("checksum")
            if not checksum:
                continue
            asset_path = _find_asset(media_dir / "assets", checksum)
            if not asset_path:
                continue

            mime_type = MediaHandler.detect_mime(asset_path)
            extension = _extension_from_mime(mime_type)
            if not extension:
                extension = asset_path.suffix or ".bin"
            if extension and not extension.startswith("."):
                extension = f".{extension}"

            normalized_path = asset_path
            try:
                if extension and asset_path.suffix.lower() != extension.lower():
                    normalized_path = asset_path.with_suffix(extension)
                    if not normalized_path.exists():
                        shutil.copy2(asset_path, normalized_path)
                if not normalized_path.exists():
                    log_warning(
                        "Daylio asset normalization failed; file missing after normalization",
                        asset_path=str(asset_path),
                        normalized_path=str(normalized_path),
                    )
                    continue
                file_size = normalized_path.stat().st_size
            except Exception as exc:
                log_warning(
                    "Daylio asset normalization failed; skipping asset",
                    asset_path=str(asset_path),
                    normalized_path=str(normalized_path),
                    error=str(exc),
                )
                continue

            media_type = "image"
            if asset.get("type") == 2:
                media_type = "audio"
            elif mime_type and mime_type.startswith("video/"):
                media_type = "video"

            media.append(
                MomentMediaDTO(
                    filename=normalized_path.name,
                    file_path=str(normalized_path.relative_to(media_dir)),
                    media_type=media_type,
                    file_size=file_size,
                    mime_type=mime_type,
                    checksum=None,
                    width=None,
                    height=None,
                    duration=None,
                    alt_text=None,
                    file_metadata=None,
                    thumbnail_path=None,
                    upload_status="completed",
                    created_at=_ms_to_utc(asset.get("createdAt")) or utc_now(),
                    updated_at=_ms_to_utc(asset.get("createdAt")) or utc_now(),
                    external_id=str(asset_id),
                    external_provider=None,
                    external_asset_id=None,
                    external_created_at=None,
                    external_metadata=None,
                )
            )
        return media

    @staticmethod
    def _should_create_entry(day_entry: DaylioDayEntry) -> bool:
        if day_entry.note and day_entry.note.strip():
            return True
        if day_entry.note_title and day_entry.note_title.strip():
            return True
        if day_entry.assets:
            return True
        return False

    @staticmethod
    def _should_create_moment(day_entry: DaylioDayEntry) -> bool:
        if day_entry.mood is not None:
            return True
        if day_entry.tags:
            return True
        return False


def _ms_to_utc(ms: Optional[int]) -> Optional[datetime]:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _offset_to_timezone(offset_ms: Optional[int]) -> str:
    if offset_ms is None:
        return "+00:00"
    total_minutes = int(offset_ms / 60000)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def _extension_from_mime(mime_type: Optional[str]) -> Optional[str]:
    if not mime_type:
        return None
    for ext, mt in MediaHandler.MIME_TYPE_MAP.items():
        if mt == mime_type:
            return ext
    return None


def _find_asset(assets_root: Path, checksum: str) -> Optional[Path]:
    if not assets_root.exists():
        return None
    for path in assets_root.rglob(f"{checksum}*"):
        if path.is_file():
            name = path.name
            if name == checksum or name.startswith(f"{checksum}."):
                return path
    return None
