"""
Export service for creating Journiv data exports.

Handles the business logic for exporting user data to ZIP archives.
"""
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlmodel import col

from app.core.config import settings
from app.core.db_utils import normalize_uuid_list
from app.core.logging_config import log_info, log_warning
from app.core.time_utils import utc_now
from app.models import (
    Activity,
    ActivityGroup,
    Entry,
    Goal,
    GoalCategory,
    GoalLog,
    Journal,
    MomentMedia,
    Mood,
    MoodGroup,
    MoodGroupLink,
    Person,
    PersonGroup,
    PersonGroupLink,
    User,
)
from app.models.enums import ExportType
from app.models.export_job import ExportJob
from app.models.goal import GoalManualLog
from app.models.moment import Moment, MomentMoodActivity
from app.models.moment_person_link import MomentPersonLink
from app.schemas.dto import (
    ActivityDTO,
    ActivityGroupDTO,
    EntryDTO,
    GoalCategoryDTO,
    GoalDTO,
    GoalLogDTO,
    GoalManualLogDTO,
    JournalDTO,
    JournivExportDTO,
    MomentDTO,
    MomentMediaDTO,
    MomentMoodActivityDTO,
    MoodDefinitionDTO,
    MoodGroupDTO,
    MoodGroupLinkDTO,
    MoodGroupPreferenceDTO,
    MoodPreferenceDTO,
    PersonDTO,
    PersonGroupDTO,
    UserSettingsDTO,
)
from app.utils.import_export import MediaHandler, ZipHandler, validate_export_data
from app.utils.import_export.constants import ExportConfig


class ExportService:
    """Service for creating data exports."""

    def __init__(self, db: Session):
        """
        Initialize export service.

        Args:
            db: Database session
        """
        self.db = db
        self.zip_handler = ZipHandler()
        self.media_handler = MediaHandler()
        self._media_export_map: Dict[str, Path] = {}
        self._person_profile_export_map: Dict[str, Path] = {}
        self._missing_media_files: List[str] = []

    def create_export(
        self,
        user_id: UUID,
        export_type: ExportType,
        journal_ids: Optional[List[UUID]] = None,
        include_media: bool = True,
    ) -> ExportJob:
        """
        Create a new export job.

        Args:
            user_id: User ID to export data for
            export_type: Type of export (FULL, JOURNAL)
            journal_ids: Specific journal IDs to export (for JOURNAL type)
            include_media: Whether to include media files

        Returns:
            Created ExportJob

        Raises:
            ValueError: If export type is invalid or user not found
        """
        # Validate user exists
        user = self.db.execute(
            select(User).where(col(User.id) == user_id)
        ).unique().scalar_one_or_none()
        if not user:
            raise ValueError(f"User not found: {user_id}")
        self._media_export_map.clear()

        # Create export job
        export_job = ExportJob(
            user_id=user_id,
            export_type=export_type,
            journal_ids=[str(jid) for jid in journal_ids] if journal_ids else None,
            include_media=include_media,
        )

        self.db.add(export_job)
        self.db.commit()
        self.db.refresh(export_job)

        log_info(f"Created export job {export_job.id} for user {user_id}", user_id=str(user_id), export_job_id=str(export_job.id))
        self._person_profile_export_map.clear()
        return export_job

    def build_export_data(
        self,
        user_id: UUID,
        export_type: ExportType,
        journal_ids: Optional[List[str]] = None,
        include_media: bool = True,
        total_entries: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> JournivExportDTO:
        """
        Build export data structure.

        Args:
            user_id: User ID to export
            export_type: Type of export
            journal_ids: Optional list of journal IDs to export
            include_media: Whether entry moments should include media metadata

        Returns:
            JournivExportDTO with all user data

        Raises:
            ValueError: If user not found
        """
        user = self.db.execute(
            select(User).where(col(User.id) == user_id)
        ).unique().scalar_one_or_none()
        if not user:
            raise ValueError(f"User not found: {user_id}")
        self._media_export_map.clear()
        self._person_profile_export_map.clear()

        journals_statement = select(Journal).where(col(Journal.user_id) == user_id)

        if export_type == ExportType.JOURNAL and journal_ids:
            # Selective journal export
            journal_uuids = [UUID(jid) for jid in journal_ids]
            journals_statement = journals_statement.where(col(Journal.id).in_(journal_uuids))

        journals_result = self.db.execute(journals_statement)
        journals = list(journals_result.unique().scalars().all())
        if total_entries is None:
            total_entries = self.count_entries(user_id, export_type, journal_ids)

        entries_processed = 0

        def handle_entry_progress():
            nonlocal entries_processed
            entries_processed += 1
            if progress_callback and total_entries:
                progress_callback(entries_processed, total_entries)

        # Convert journals to metadata-only DTOs (moment-first export).
        journal_dtos = [self._convert_journal_to_dto(journal) for journal in journals]

        # Get mood definitions (system + user custom)
        mood_dtos = self._get_mood_definitions(user_id)

        # Get mood preferences/groups
        mood_preference_dtos = self._get_mood_preferences(user_id)
        mood_group_dtos = self._get_mood_groups(user_id)
        mood_group_link_dtos = self._get_mood_group_links(user_id)
        mood_group_preference_dtos = self._get_mood_group_preferences(user_id)

        # Get activity groups/activities
        activity_group_dtos = self._get_activity_groups(user_id)
        activity_dtos = self._get_activities(user_id)
        person_group_dtos = self._get_person_groups(user_id)
        person_dtos = self._get_people(user_id, include_media=include_media)

        # Get goals and categories/logs
        goal_category_dtos = self._get_goal_categories(user_id)
        goal_dtos = self._get_goals(user_id)
        goal_log_dtos = self._get_goal_logs(user_id)
        goal_manual_log_dtos = self._get_goal_manual_logs(user_id)

        # Get user settings
        user_settings = self._get_user_settings(user)

        moments_query = select(Moment).where(col(Moment.user_id) == user_id)
        if export_type == ExportType.JOURNAL and journal_ids:
            journal_uuids = [UUID(jid) for jid in journal_ids]
            moments_query = moments_query.join(
                Entry, col(Entry.moment_id) == col(Moment.id)
            ).where(col(Entry.journal_id).in_(journal_uuids))

        moments = list(
            self.db.execute(moments_query.order_by(col(Moment.logged_at_utc))).scalars().all()
        )
        moment_prefetch = self._build_moment_prefetch(moments, include_media=include_media)
        moment_dtos = [
            self._convert_moment_to_dto(moment, include_media=include_media, prefetch=moment_prefetch)
            for moment in moments
        ]

        for moment_dto in moment_dtos:
            if moment_dto.entry is not None:
                handle_entry_progress()

        # Calculate statistics
        total_entries = sum(1 for m in moment_dtos if m.entry is not None)
        total_media = sum(len(m.media) for m in moment_dtos)

        stats = {
            "journal_count": len(journal_dtos),
            "entry_count": total_entries,
            "media_count": total_media,
            "mood_count": len(mood_dtos),
            "mood_group_count": len(mood_group_dtos),
            "activity_count": len(activity_dtos),
            "activity_group_count": len(activity_group_dtos),
            "people_count": len(person_dtos),
            "person_group_count": len(person_group_dtos),
            "goal_count": len(goal_dtos),
            "goal_category_count": len(goal_category_dtos),
            "goal_log_count": len(goal_log_dtos),
            "export_size_estimate": "calculated_during_zip_creation",
        }

        # Build export DTO
        export_dto = JournivExportDTO(
            export_version=ExportConfig.EXPORT_VERSION,
            export_date=utc_now(),
            app_version=settings.app_version,
            user_email=user.email,
            user_name=user.name or user.email.split('@')[0],
            user_settings=user_settings,
            journals=journal_dtos,
            mood_definitions=mood_dtos,
            mood_preferences=mood_preference_dtos,
            mood_groups=mood_group_dtos,
            mood_group_links=mood_group_link_dtos,
            mood_group_preferences=mood_group_preference_dtos,
            activities=activity_dtos,
            activity_groups=activity_group_dtos,
            people=person_dtos,
            person_groups=person_group_dtos,
            goal_categories=goal_category_dtos,
            goals=goal_dtos,
            goal_logs=goal_log_dtos,
            goal_manual_logs=goal_manual_log_dtos,
            moments=moment_dtos,
            stats=stats,
        )

        return export_dto

    def create_export_zip(
        self,
        export_data: JournivExportDTO,
        user_id: UUID,
        include_media: bool = True,
    ) -> tuple[Path, int, Dict[str, Any]]:
        """
        Create ZIP archive from export data.

        Args:
            export_data: Export data to package
            user_id: User ID (for file naming)
            include_media: Whether to include media files

        Returns:
            Tuple of (zip_path, file_size, stats)

        Raises:
            IOError: If ZIP creation fails
        """
        # Create export directory if needed
        export_dir = Path(settings.export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"journiv_export_{user_id}_{timestamp}.zip"
        zip_path = export_dir / zip_filename

        self._missing_media_files = []
        # Collect media files if requested
        media_files: Dict[str, Path] = {}
        if include_media:
            media_files = self._collect_media_files(export_data, user_id)

        # Convert export data to dictionary and validate
        export_dict = export_data.model_dump(mode='json')
        validation = validate_export_data(export_dict)
        if not validation.valid:
            raise ValueError(f"Export validation failed: {validation.errors}")

        temp_data_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                delete=False,
                encoding="utf-8",
                suffix=".json",
            ) as tmp_file:
                # Stream JSON in chunks to avoid building a giant string in memory.
                encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"))
                for chunk in encoder.iterencode(export_dict):
                    tmp_file.write(chunk)
                temp_data_path = Path(tmp_file.name)

            # Create ZIP
            file_size = self.zip_handler.create_export_zip(
                output_path=zip_path,
                data_file_path=temp_data_path,
                media_files=media_files,
                data_filename=ExportConfig.DATA_FILENAME,
            )
        finally:
            if temp_data_path and temp_data_path.exists():
                temp_data_path.unlink(missing_ok=True)

        # Update stats
        stats = {
            "journal_count": len(export_data.journals),
            "entry_count": sum(1 for m in export_data.moments if m.entry is not None),
            "media_count": len(media_files),
            "person_group_count": len(export_data.person_groups),
            "missing_media_count": len(self._missing_media_files),
            "missing_media_files": list(self._missing_media_files),
            "file_size": file_size,
        }

        log_info(f"Created export ZIP: {zip_path} ({file_size} bytes)", user_id=str(user_id), file_size=file_size, media_count=len(media_files))
        return zip_path, file_size, stats

    def cleanup_old_exports(self) -> int:
        """
        Remove export archives older than the configured retention period.

        Returns:
            Number of files deleted.
        """
        retention_days = settings.export_cleanup_days
        if retention_days <= 0:
            return 0

        export_dir = Path(settings.export_dir)
        if not export_dir.exists():
            return 0

        cutoff_ts = (utc_now() - timedelta(days=retention_days)).timestamp()
        removed = 0

        for file_path in export_dir.glob("journiv_export_*.zip"):
            try:
                if file_path.stat().st_mtime < cutoff_ts:
                    file_path.unlink(missing_ok=True)
                    removed += 1
            except Exception as exc:  # best-effort cleanup
                log_warning(f"Failed to delete export {file_path}: {exc}", file_path=str(file_path))

        if removed:
            log_info(f"Cleaned up {removed} expired export archives", removed=removed)
        return removed

    def count_entries(
        self,
        user_id: UUID,
        export_type: ExportType,
        journal_ids: Optional[List[str]] = None,
    ) -> int:
        """Count the number of entries that will be included in the export."""
        query = (
            select(func.count(Entry.id))
            .join(Journal, Entry.journal_id == Journal.id)
            .where(Journal.user_id == user_id)
        )

        if export_type == ExportType.JOURNAL and journal_ids:
            journal_uuids = [UUID(jid) for jid in journal_ids]
            query = query.where(col(Entry.journal_id).in_(journal_uuids))

        return int(self.db.execute(query).scalar_one() or 0)

    def _convert_journal_to_dto(self, journal: Journal) -> JournalDTO:
        """
        Convert Journal model to JournalDTO.

        Maps database fields to DTO structure:
        - journal.title -> title
        - journal.color -> color (enum to string)
        - journal.is_archived, entry_count, last_entry_at included
        """
        return JournalDTO(
            title=journal.title,  # Journal has 'title' not 'name'
            description=journal.description,
            color=journal.color.value if journal.color else None,  # Convert enum to string
            icon=journal.icon,
            is_favorite=journal.is_favorite,
            is_archived=journal.is_archived,  # Include archived status
            last_entry_at=journal.last_entry_at,  # Last entry timestamp
            import_metadata=journal.import_metadata,
            created_at=journal.created_at,
            updated_at=journal.updated_at,
            external_id=str(journal.id),
        )

    def _convert_entry_to_dto(
        self,
        entry: Entry,
    ) -> EntryDTO:
        """
        Convert Entry model to EntryDTO.

        All contextual metadata (dates, location, weather, tags, media, mood,
        prompt, pinned) lives on the parent Moment.
        """
        plain_text = entry.content_plain_text or ""
        # Integrity fallback: if stored word_count is null, recompute from plain text.
        word_count = entry.word_count
        if word_count is None:
            word_count = len(plain_text.split()) if plain_text else 0

        return EntryDTO(
            title=entry.title,
            content_delta=entry.content_delta,
            content_plain_text=entry.content_plain_text,
            word_count=word_count,
            is_draft=entry.is_draft,
            journal_external_id=str(entry.journal_id),
            import_metadata=entry.import_metadata,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            external_id=str(entry.id),
        )

    def _build_moment_prefetch(self, moments: List[Moment], *, include_media: bool) -> dict:
        if not moments:
            return {
                "links_by_moment": {},
                "mood_map": {},
                "activity_map": {},
                "media_map": {},
                "entry_map": {},
                "people_links_by_moment": {},
            }
        moment_ids = [moment.id for moment in moments]
        links = (
            self.db.execute(
                select(MomentMoodActivity).where(
                    col(MomentMoodActivity.moment_id).in_(moment_ids)
                )
            )
            .scalars()
            .all()
        )
        links_by_moment: dict[UUID, list[MomentMoodActivity]] = {
            moment_id: [] for moment_id in moment_ids
        }
        mood_ids: set[UUID] = set()
        activity_ids: set[UUID] = set()
        for link in links:
            links_by_moment[link.moment_id].append(link)
            if link.mood_id:
                mood_ids.add(link.mood_id)
            if link.activity_id:
                activity_ids.add(link.activity_id)

        for moment in moments:
            if moment.primary_mood_id:
                mood_ids.add(moment.primary_mood_id)

        mood_map: dict[UUID, Mood] = {}
        if mood_ids:
            mood_map = {
                mood.id: mood
                for mood in self.db.execute(
                    select(Mood).where(col(Mood.id).in_(normalize_uuid_list(mood_ids)))
                )
                .scalars()
                .all()
            }

        activity_map: dict[UUID, Activity] = {}
        if activity_ids:
            activity_map = {
                activity.id: activity
                for activity in self.db.execute(
                    select(Activity).where(col(Activity.id).in_(normalize_uuid_list(activity_ids)))
                )
                .scalars()
                .all()
            }

        media_map: dict[UUID, list[MomentMedia]] = {
            moment_id: [] for moment_id in moment_ids
        }
        if include_media:
            media_rows = (
                self.db.execute(
                    select(MomentMedia).where(col(MomentMedia.moment_id).in_(moment_ids))
                )
                .scalars()
                .all()
            )
            for media in media_rows:
                if media.moment_id:
                    media_map[media.moment_id].append(media)

        entries = (
            self.db.execute(
                select(Entry).where(col(Entry.moment_id).in_(moment_ids))
            )
            .scalars()
            .all()
        )
        entry_map: dict[UUID, Entry] = {
            entry.moment_id: entry
            for entry in entries
            if entry.moment_id is not None
        }
        people_links_by_moment: dict[UUID, list[UUID]] = {moment_id: [] for moment_id in moment_ids}
        people_links = (
            self.db.execute(
                select(MomentPersonLink).where(col(MomentPersonLink.moment_id).in_(moment_ids))
            )
            .scalars()
            .all()
        )
        for link in people_links:
            people_links_by_moment.setdefault(link.moment_id, []).append(link.person_id)

        return {
            "links_by_moment": links_by_moment,
            "mood_map": mood_map,
            "activity_map": activity_map,
            "media_map": media_map,
            "entry_map": entry_map,
            "people_links_by_moment": people_links_by_moment,
        }

    def _convert_moment_to_dto(
        self,
        moment: Moment,
        *,
        include_media: bool,
        prefetch: Optional[dict] = None,
    ) -> MomentDTO:
        prefetch = prefetch or {}
        mood_map: dict[UUID, Mood] = prefetch.get("mood_map", {})
        activity_map: dict[UUID, Activity] = prefetch.get("activity_map", {})
        links_by_moment: dict[UUID, list[MomentMoodActivity]] = prefetch.get("links_by_moment", {})
        media_map: dict[UUID, list[MomentMedia]] = prefetch.get("media_map", {})
        entry_map: dict[UUID, Entry] = prefetch.get("entry_map", {})
        people_links_by_moment: dict[UUID, list[UUID]] = prefetch.get("people_links_by_moment", {})

        mood_name = None
        if moment.primary_mood_id:
            mood = mood_map.get(moment.primary_mood_id)
            if mood is None:
                mood = (
                    self.db.execute(
                        select(Mood).where(col(Mood.id) == moment.primary_mood_id)
                    )
                    .scalars()
                    .first()
                )
            mood_name = mood.name if mood else None

        links = links_by_moment.get(moment.id)
        if links is None:
            links = (
                self.db.execute(
                    select(MomentMoodActivity).where(
                        col(MomentMoodActivity.moment_id) == moment.id
                    )
                )
                .scalars()
                .all()
            )

        missing_mood_ids = {
            link.mood_id
            for link in links
            if link.mood_id and link.mood_id not in mood_map
        }
        if missing_mood_ids:
            mood_rows = (
                self.db.execute(
                    select(Mood).where(col(Mood.id).in_(normalize_uuid_list(missing_mood_ids)))
                )
                .scalars()
                .all()
            )
            for mood in mood_rows:
                mood_map[mood.id] = mood

        missing_activity_ids = {
            link.activity_id
            for link in links
            if link.activity_id and link.activity_id not in activity_map
        }
        if missing_activity_ids:
            activity_rows = (
                self.db.execute(
                    select(Activity).where(
                        col(Activity.id).in_(normalize_uuid_list(missing_activity_ids))
                    )
                )
                .scalars()
                .all()
            )
            for activity in activity_rows:
                activity_map[activity.id] = activity

        mood_activity = []
        for link in links:
            mood = mood_map.get(link.mood_id) if link.mood_id else None
            activity = activity_map.get(link.activity_id) if link.activity_id else None
            mood_activity.append(
                MomentMoodActivityDTO(
                    mood_name=mood.name if mood else None,
                    activity_name=activity.name if activity else None,
                    mood_external_id=str(mood.id) if mood else None,
                    activity_external_id=str(activity.id) if activity else None,
                )
            )

        media_dtos = []
        if include_media:
            moment_media = media_map.get(moment.id)
            if moment_media is None:
                moment_media = (
                    self.db.execute(
                        select(MomentMedia).where(col(MomentMedia.moment_id) == moment.id)
                    )
                    .scalars()
                    .all()
                )
            for media in moment_media:
                media_dtos.append(self._convert_media_to_dto(media))

        logged_date_tz = moment.logged_date_tz
        if logged_date_tz is None:
            if moment.logged_at_utc is not None:
                logged_date_tz = moment.logged_at_utc.date()
                log_warning(
                    "Moment logged_date_tz missing; derived from logged_at_utc",
                    moment_id=str(moment.id),
                    user_id=str(moment.user_id),
                )
            elif moment.created_at is not None:
                logged_date_tz = moment.created_at.date()
                log_warning(
                    "Moment logged_date_tz/logged_at_utc missing; derived from created_at",
                    moment_id=str(moment.id),
                    user_id=str(moment.user_id),
                )
            else:
                logged_date_tz = utc_now().date()
                log_warning(
                    "Moment logged_date_tz/logged_at_utc/created_at missing; using current date",
                    moment_id=str(moment.id),
                    user_id=str(moment.user_id),
                )

        # Collect tag names from MomentTagLink
        tags = [tag.name for tag in moment.tags] if moment.tags else []
        people_external_ids = [str(person_id) for person_id in people_links_by_moment.get(moment.id, [])]

        # Get prompt text if moment was created from a prompt
        prompt_text = None
        if moment.prompt:
            prompt_text = moment.prompt.text

        entry = entry_map.get(moment.id)
        entry_dto = self._convert_entry_to_dto(entry) if entry is not None else None

        return MomentDTO(
            logged_at_utc=moment.logged_at_utc,
            logged_date_tz=logged_date_tz,
            logged_timezone=moment.logged_timezone,
            note=moment.note,
            location_json=moment.location_json,
            latitude=moment.latitude,
            longitude=moment.longitude,
            weather_json=moment.weather_json,
            weather_summary=moment.weather_summary,
            is_pinned=moment.is_pinned,
            prompt_text=prompt_text,
            tags=tags,
            people_external_ids=people_external_ids,
            primary_mood_name=mood_name,
            primary_mood_external_id=str(moment.primary_mood_id) if moment.primary_mood_id else None,
            mood_activity=mood_activity,
            media=media_dtos,
            entry=entry_dto,
            created_at=moment.created_at,
            updated_at=moment.updated_at,
            external_id=str(moment.id),
        )

    def _convert_media_to_dto(self, media: MomentMedia) -> MomentMediaDTO:
        """
        Convert MomentMedia model to MomentMediaDTO.

        Maps database fields to DTO structure:
        - media.original_filename -> filename
        - media.file_path -> file_path (actual storage path)
        - media.media_type.value -> media_type (enum to string)
        - media.alt_text -> alt_text (also maps to caption for compatibility)
        - Includes all new fields: thumbnail_path, file_metadata, upload_status
        """
        sanitized_path = None
        if media.file_path:
            sanitized_path = self._build_media_export_path(media)
            # Ensure we don't try to resolve None or empty paths
            actual_path = Path(settings.media_root) / media.file_path
            self._media_export_map[sanitized_path] = actual_path

        # Determine filename with fallback
        filename = media.original_filename
        if not filename and media.file_path:
            filename = media.file_path.split('/')[-1]
        if not filename:
            # Fallback for external media without original_filename
            filename = f"media_{media.id}"

        return MomentMediaDTO(
            filename=filename,
            file_path=sanitized_path,
            media_type=media.media_type.value if hasattr(media.media_type, 'value') else str(media.media_type),
            file_size=media.file_size or 0,  # Ensure non-None for older entries/external
            mime_type=media.mime_type,
            checksum=media.checksum,
            width=media.width,
            height=media.height,
            duration=media.duration,
            alt_text=media.alt_text,  # Use alt_text from database
            file_metadata=media.file_metadata,  # Include metadata JSON
            thumbnail_path=media.thumbnail_path,  # Include thumbnail path
            upload_status=media.upload_status.value if hasattr(media.upload_status, 'value') else str(media.upload_status),
            # Preserve original timestamps from database
            created_at=media.created_at,
            updated_at=media.updated_at,
            caption=media.alt_text,  # PLACEHOLDER: Map alt_text to caption for compatibility

            # External provider fields
            external_provider=media.external_provider,
            external_asset_id=media.external_asset_id,
            external_url=media.external_url,
            external_created_at=media.external_created_at,
            external_metadata=media.external_metadata,
            external_id=str(media.id),
        )

    def _get_people(self, user_id: UUID, *, include_media: bool = True) -> List[PersonDTO]:
        rows = (
            self.db.execute(
                select(Person).where(col(Person.user_id) == user_id).order_by(col(Person.created_at).asc())
            )
            .scalars()
            .all()
        )
        person_ids = [person.id for person in rows]
        group_links_by_person: Dict[UUID, List[str]] = {person_id: [] for person_id in person_ids}
        if person_ids:
            links = (
                self.db.execute(
                    select(PersonGroupLink).where(
                        col(PersonGroupLink.person_id).in_(person_ids)
                    )
                )
                .scalars()
                .all()
            )
            for link in links:
                group_links_by_person.setdefault(link.person_id, []).append(
                    str(link.person_group_id)
                )

        people: List[PersonDTO] = []
        for person in rows:
            profile_image_path = None
            if include_media and person.profile_image_path:
                profile_image_path = self._build_person_profile_export_path(person)
                try:
                    self._person_profile_export_map[
                        profile_image_path
                    ] = self._resolve_media_root_path(person.profile_image_path)
                except ValueError as exc:
                    log_warning(
                        "Person profile image path escaped media root during export",
                        user_id=str(user_id),
                        person_id=str(person.id),
                        profile_image_path=person.profile_image_path,
                        error=str(exc),
                    )
                    profile_image_path = None

            people.append(
                PersonDTO(
                    name=person.name,
                    nickname=person.nickname,
                    note=person.note,
                    profile_image_path=profile_image_path,
                    person_group_external_ids=group_links_by_person.get(person.id, []),
                    archived_at=person.archived_at,
                    created_at=person.created_at,
                    updated_at=person.updated_at,
                    external_id=str(person.id),
                )
            )
        return people

    def _get_person_groups(self, user_id: UUID) -> List[PersonGroupDTO]:
        """Get person groups for export."""
        groups = (
            self.db.execute(
                select(PersonGroup)
                .where(col(PersonGroup.user_id) == user_id)
                .order_by(col(PersonGroup.position), col(PersonGroup.name))
            )
            .scalars()
            .all()
        )
        return [
            PersonGroupDTO(
                name=group.name,
                color_value=group.color_value,
                icon=group.icon,
                position=group.position,
                created_at=group.created_at,
                updated_at=group.updated_at,
                external_id=str(group.id),
            )
            for group in groups
        ]

    def _get_mood_definitions(self, user_id: UUID) -> List[MoodDefinitionDTO]:
        """
        Get user mood definitions.

        Maps database fields to DTO structure:
        - mood.name -> name
        - mood.icon -> icon (also mapped to emoji for compatibility)
        - mood.category -> category
        """
        moods_result = self.db.execute(
            select(Mood).where(
                col(Mood.user_id) == user_id
            )
        )
        moods = list(moods_result.unique().scalars().all())

        mood_dtos = []
        for mood in moods:
            mood_dto = MoodDefinitionDTO(
                name=mood.name,
                category=mood.category,
                icon=mood.icon,  # Use icon field
                key=mood.key,
                color_value=mood.color_value,
                score=mood.score,
                position=mood.position,
                is_active=mood.is_active,
                is_custom=True,
                created_at=mood.created_at,
                updated_at=mood.updated_at,
                external_id=str(mood.id),
                emoji=mood.icon or "",  # PLACEHOLDER: Map icon to emoji for compatibility
                color=None,  # PLACEHOLDER: Mood model doesn't have color string
            )
            mood_dtos.append(mood_dto)

        return mood_dtos

    def _get_user_settings(self, user: User) -> Optional[UserSettingsDTO]:
        """
        Get user settings for export.

        Maps database fields to DTO structure:
        - user.settings.time_zone -> time_zone (not timezone!)
        - Placeholders: date_format, time_format, first_day_of_week set to defaults
        """
        if not user.settings:
            return None

        return UserSettingsDTO(
            theme=user.settings.theme or "light",
            time_zone=user.settings.time_zone or "UTC",
            daily_prompt_enabled=user.settings.daily_prompt_enabled,
            push_notifications=user.settings.push_notifications,
            reminder_time=user.settings.reminder_time,
            writing_goal_daily=user.settings.writing_goal_daily,
            start_of_week_day=user.settings.start_of_week_day,
            date_format="YYYY-MM-DD",  # PLACEHOLDER: UserSettings doesn't have this field
            time_format="24h",  # PLACEHOLDER: UserSettings doesn't have this field
            first_day_of_week=0,  # PLACEHOLDER: UserSettings doesn't have this field
        )

    def _get_activity_groups(self, user_id: UUID) -> List[ActivityGroupDTO]:
        """Get activity groups for export."""
        groups = (
            self.db.execute(
                select(ActivityGroup)
                .where(col(ActivityGroup.user_id) == user_id)
                .order_by(col(ActivityGroup.position), col(ActivityGroup.created_at))
            )
            .scalars()
            .all()
        )
        return [
            ActivityGroupDTO(
                name=group.name,
                color_value=group.color_value,
                icon=group.icon,
                position=group.position,
                created_at=group.created_at,
                updated_at=group.updated_at,
                external_id=str(group.id),
            )
            for group in groups
        ]

    def _get_activities(self, user_id: UUID) -> List[ActivityDTO]:
        """Get activities for export."""
        activities = (
            self.db.execute(
                select(Activity)
                .where(col(Activity.user_id) == user_id)
                .order_by(col(Activity.position), col(Activity.created_at))
            )
            .scalars()
            .all()
        )
        return [
            ActivityDTO(
                name=activity.name,
                icon=activity.icon,
                color=activity.color,
                position=activity.position,
                group_external_id=str(activity.group_id) if activity.group_id else None,
                created_at=activity.created_at,
                updated_at=activity.updated_at,
                external_id=str(activity.id),
            )
            for activity in activities
        ]

    def _get_goal_categories(self, user_id: UUID) -> List[GoalCategoryDTO]:
        """Get goal categories for export."""
        categories = (
            self.db.execute(
                select(GoalCategory)
                .where(col(GoalCategory.user_id) == user_id)
                .order_by(col(GoalCategory.position), col(GoalCategory.created_at))
            )
            .scalars()
            .all()
        )
        return [
            GoalCategoryDTO(
                name=category.name,
                color_value=category.color_value,
                icon=category.icon,
                position=category.position,
                created_at=category.created_at,
                updated_at=category.updated_at,
                external_id=str(category.id),
            )
            for category in categories
        ]

    def _get_goals(self, user_id: UUID) -> List[GoalDTO]:
        """Get goals for export."""
        goals = (
            self.db.execute(
                select(Goal)
                .where(col(Goal.user_id) == user_id)
                .order_by(col(Goal.position), col(Goal.created_at))
            )
            .scalars()
            .all()
        )
        return [
            GoalDTO(
                title=goal.title,
                goal_type=goal.goal_type,
                frequency_type=goal.frequency_type,
                target_count=goal.target_count,
                reminder_time=goal.reminder_time,
                is_paused=goal.is_paused,
                icon=goal.icon,
                color_value=goal.color_value,
                position=goal.position,
                archived_at=goal.archived_at,
                activity_external_id=str(goal.activity_id) if goal.activity_id else None,
                category_external_id=str(goal.category_id) if goal.category_id else None,
                created_at=goal.created_at,
                updated_at=goal.updated_at,
                external_id=str(goal.id),
            )
            for goal in goals
        ]

    def _get_goal_logs(self, user_id: UUID) -> List[GoalLogDTO]:
        """Get goal logs for export."""
        logs = (
            self.db.execute(
                select(GoalLog)
                .where(col(GoalLog.user_id) == user_id)
                .order_by(col(GoalLog.logged_date), col(GoalLog.created_at))
            )
            .scalars()
            .all()
        )
        return [
            GoalLogDTO(
                goal_external_id=str(log.goal_id),
                logged_date=log.logged_date,
                period_start=log.period_start,
                period_end=log.period_end,
                status=log.status,
                count=log.count,
                source=log.source,
                last_updated_at=log.last_updated_at,
                moment_external_id=str(log.moment_id) if log.moment_id else None,
                created_at=log.created_at,
                updated_at=log.updated_at,
                external_id=str(log.id),
            )
            for log in logs
        ]

    def _get_goal_manual_logs(self, user_id: UUID) -> List[GoalManualLogDTO]:
        """Get manual goal logs for export."""
        logs = (
            self.db.execute(
                select(GoalManualLog)
                .where(col(GoalManualLog.user_id) == user_id)
                .order_by(col(GoalManualLog.logged_date), col(GoalManualLog.created_at))
            )
            .scalars()
            .all()
        )
        return [
            GoalManualLogDTO(
                goal_external_id=str(log.goal_id),
                logged_date=log.logged_date,
                status=log.status,
                created_at=log.created_at,
                updated_at=log.updated_at,
                external_id=str(log.id),
            )
            for log in logs
        ]

    def _get_mood_groups(self, user_id: UUID) -> List[MoodGroupDTO]:
        """Get mood groups for export."""
        groups = (
            self.db.execute(
                select(MoodGroup)
                .where(col(MoodGroup.user_id) == user_id)
                .order_by(col(MoodGroup.position), col(MoodGroup.created_at))
            )
            .scalars()
            .all()
        )
        return [
            MoodGroupDTO(
                name=group.name,
                icon=group.icon,
                color_value=group.color_value,
                position=group.position,
                is_custom=True,
                created_at=group.created_at,
                updated_at=group.updated_at,
                external_id=str(group.id),
            )
            for group in groups
        ]

    def _get_mood_group_links(self, user_id: UUID) -> List[MoodGroupLinkDTO]:
        """Get mood group links for export."""
        group_ids = (
            self.db.execute(
                select(col(MoodGroup.id)).where(
                    col(MoodGroup.user_id) == user_id
                )
            )
            .scalars()
            .all()
        )
        if not group_ids:
            return []
        links = (
            self.db.execute(
                select(MoodGroupLink).where(
                    col(MoodGroupLink.mood_group_id).in_(group_ids)
                )
            )
            .scalars()
            .all()
        )
        return [
            MoodGroupLinkDTO(
                mood_group_external_id=str(link.mood_group_id),
                mood_external_id=str(link.mood_id),
                position=link.position,
                created_at=link.created_at,
                updated_at=link.updated_at,
            )
            for link in links
        ]

    def _get_mood_preferences(self, _user_id: UUID) -> List[MoodPreferenceDTO]:
        """User mood preferences have been removed; keep export field empty."""
        log_warning("Mood preferences are omitted from export because the feature was removed")
        return []

    def _get_mood_group_preferences(self, _user_id: UUID) -> List[MoodGroupPreferenceDTO]:
        """User mood-group preferences have been removed; keep export field empty."""
        log_warning("Mood group preferences are omitted from export because the feature was removed")
        return []

    def _collect_media_files(
        self, export_data: JournivExportDTO, user_id: UUID
    ) -> Dict[str, Path]:
        """
        Collect media files from export data.

        Args:
            export_data: Export data with media references
            user_id: User ID for media lookup

        Returns:
            Dictionary of {relative_path: absolute_path}
        """
        media_files: Dict[str, Path] = {}
        for person in export_data.people:
            if not person.profile_image_path:
                continue

            source_path = self._resolve_person_profile_source_path(person, user_id)
            if source_path and source_path.exists():
                media_files[person.profile_image_path] = source_path
            else:
                if person.profile_image_path not in self._missing_media_files:
                    self._missing_media_files.append(person.profile_image_path)
                log_warning(
                    "Person profile image file not found during export",
                    user_id=str(user_id),
                    person_external_id=person.external_id,
                    profile_image_path=person.profile_image_path,
                    source_path=str(source_path) if source_path else None,
                )

        for moment in export_data.moments:
            for media in moment.media:
                if not media.file_path:
                    log_warning(
                        f"Media {media.filename} has no file_path, skipping",
                        user_id=str(user_id),
                        media_filename=media.filename
                    )
                    continue

                source_path = self._media_export_map.get(media.file_path)
                if not source_path:
                    source_path = Path(settings.media_root) / media.file_path

                if source_path.exists():
                    media_files[media.file_path] = source_path
                else:
                    if media.file_path not in self._missing_media_files:
                        self._missing_media_files.append(media.file_path)
                    log_warning(
                        f"Media file not found: {source_path} (file_path: {media.file_path})",
                        user_id=str(user_id),
                        file_path=media.file_path,
                        source_path=str(source_path)
                    )

        return media_files

    def _resolve_person_profile_source_path(
        self, person: PersonDTO, user_id: UUID
    ) -> Optional[Path]:
        """Resolve exported profile-image source path from cache or the database."""
        if not person.profile_image_path:
            return None

        cached_path = self._person_profile_export_map.get(person.profile_image_path)
        if cached_path:
            return cached_path

        if not person.external_id:
            return None
        try:
            person_id = UUID(person.external_id)
        except ValueError:
            return None

        source_person = self.db.get(Person, person_id)
        if (
            source_person is None
            or source_person.user_id != user_id
            or not source_person.profile_image_path
        ):
            return None

        try:
            source_path = self._resolve_media_root_path(source_person.profile_image_path)
        except ValueError as exc:
            log_warning(
                "Person profile image path escaped media root during export",
                user_id=str(user_id),
                person_id=str(source_person.id),
                profile_image_path=source_person.profile_image_path,
                error=str(exc),
            )
            return None

        self._person_profile_export_map[person.profile_image_path] = source_path
        return source_path

    def _resolve_media_root_path(self, relative_path: str) -> Path:
        """Resolve a stored media path while preventing media-root escapes."""
        media_root = Path(settings.media_root).resolve()
        resolved_path = (media_root / relative_path).resolve()
        resolved_path.relative_to(media_root)
        return resolved_path

    def _build_person_profile_export_path(self, person: Person) -> str:
        """Build a sanitized relative path for a person's profile image in export ZIP."""
        suffix = Path(person.profile_image_path or "").suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"
        return f"people/{person.id}/profile{suffix}"

    def _build_media_export_path(self, media: MomentMedia) -> str:
        """Build a sanitized relative path for media inside the export ZIP."""
        file_path = media.file_path or ""
        original_name = media.original_filename or (Path(file_path).name if file_path else "media")
        safe_name = self.media_handler.sanitize_filename(original_name)
        parent_id = media.moment_id or "media"
        return f"{parent_id}/{media.id}_{safe_name}"
