"""
Import service for importing data into Journiv.

Handles the business logic for importing data from various sources.
"""
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, cast
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.logging_config import log_error, log_info, log_warning
from app.core.time_utils import local_date_for_user, normalize_timezone, utc_now
from app.data_transfer.daylio import DaylioParser, DaylioToJournivMapper
from app.data_transfer.dayone import DayOneParser, DayOneToJournivMapper
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
    Tag,
    User,
    UserMoodGroupPreference,
    UserMoodPreference,
)
from app.models.enums import ImportSourceType, JournalColor, MediaType, UploadStatus
from app.models.goal import GoalManualLog
from app.models.import_job import ImportJob
from app.models.moment import Moment, MomentMoodActivity
from app.schemas.dto import (
    ActivityDTO,
    ActivityGroupDTO,
    EntryDTO,
    GoalCategoryDTO,
    GoalDTO,
    GoalLogDTO,
    GoalManualLogDTO,
    ImportResultSummary,
    JournivExportDTO,
    MomentDTO,
    MomentMediaDTO,
    MoodDefinitionDTO,
    MoodGroupDTO,
    MoodGroupLinkDTO,
    MoodGroupPreferenceDTO,
    MoodPreferenceDTO,
)
from app.services.journal_service import JournalService
from app.services.media_storage_service import MediaStorageService
from app.utils.import_export import (
    MediaHandler,
    ZipHandler,
)
from app.utils.import_export.constants import ExportConfig
from app.utils.quill_delta import extract_plain_text, replace_media_ids, wrap_plain_text


class ImportService:
    """Service for importing data."""

    def __init__(self, db: Session):
        """
        Initialize import service.

        Args:
            db: Database session
        """
        self.db = db
        self.zip_handler = ZipHandler()
        self.media_storage_service = MediaStorageService(Path(settings.media_root), db)
        self.media_handler = MediaHandler()

    @staticmethod
    def _extract_export_media_id(file_path: Optional[str]) -> Optional[str]:
        """Extract media UUID from exported file paths like moment_id/media_id_filename."""
        if not file_path:
            return None

        name = Path(file_path).name
        if "_" in name:
            candidate = name.split("_", 1)[0]
            try:
                UUID(candidate)
                return candidate
            except ValueError:
                pass

        # Fallback: match any UUID in the filename portion.
        match = re.search(
            r'([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})',
            name,
        )
        return match.group(1) if match else None

    @staticmethod
    def _replace_media_ids_in_delta(
        content_delta: Optional[Dict[str, Any]],
        id_map: Dict[str, str],
    ) -> Dict[str, Any]:
        """Replace media IDs inside Quill Delta embeds."""
        if not id_map:
            return content_delta or {"ops": []}
        return replace_media_ids(content_delta, id_map)

    @staticmethod
    def _build_dayone_placeholder_map(
        entry_dto: EntryDTO,
        media_items: List[MomentMediaDTO],
        export_media_id_map: Dict[str, str],
    ) -> Dict[str, str]:
        """Build Day One md5/identifier -> media_id map for placeholder replacement."""
        import_metadata = entry_dto.import_metadata or {}
        if import_metadata.get("source") != "dayone":
            return {}

        raw_dayone = import_metadata.get("raw_dayone") or {}
        raw_media_items = (raw_dayone.get("photos") or []) + (raw_dayone.get("videos") or [])
        placeholder_map: Dict[str, str] = {}

        for item in raw_media_items:
            if not isinstance(item, dict):
                continue
            identifier = item.get("identifier")
            if not identifier:
                continue
            media_id = export_media_id_map.get(identifier)
            if not media_id:
                continue
            placeholder_map[identifier] = media_id
            md5_hash = item.get("md5")
            if md5_hash:
                placeholder_map[md5_hash] = media_id

        # Also map asset identifiers stored on normalized MomentMediaDTO entries.
        for media_dto in media_items:
            if media_dto.external_asset_id and media_dto.external_asset_id in export_media_id_map:
                placeholder_map[media_dto.external_asset_id] = export_media_id_map[media_dto.external_asset_id]

        return placeholder_map

    @staticmethod
    def _add_warning(summary: ImportResultSummary, message: str, category: str):
        """Add a warning to summary and increment category count."""
        summary.warnings.append(message)
        summary.warning_categories[category] = summary.warning_categories.get(category, 0) + 1

    def create_import_job(
        self,
        user_id: UUID,
        source_type: ImportSourceType,
        file_path: str,
    ) -> ImportJob:
        """
        Create a new import job.

        Args:
            user_id: User ID to import data for
            source_type: Source type (JOURNIV, MARKDOWN, etc.)
            file_path: Path to uploaded file

        Returns:
            Created ImportJob

        Raises:
            ValueError: If user not found or file invalid
        """
        # Validate user exists
        user = self.db.query(User).filter(col(User.id) == user_id).first()
        if not user:
            raise ValueError(f"User not found: {user_id}")

        # Validate file exists
        if not Path(file_path).exists():
            raise ValueError(f"File not found: {file_path}")

        # Create import job
        import_job = ImportJob(
            user_id=user_id,
            source_type=source_type,
            file_path=file_path,
        )

        self.db.add(import_job)
        self.db.commit()
        self.db.refresh(import_job)

        log_info(f"Created import job {import_job.id} for user {user_id}", user_id=str(user_id), import_job_id=str(import_job.id))
        return import_job

    def extract_import_data(
        self, file_path: Path
    ) -> tuple[Dict[str, Any], Optional[Path]]:
        """
        Extract import data from ZIP file.

        Args:
            file_path: Path to ZIP file

        Returns:
            Tuple of (data_dict, media_dir)

        Raises:
            ValueError: If ZIP is invalid
            IOError: If extraction fails
        """
        # Create temp directory for extraction
        temp_dir = Path(settings.import_temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Extract ZIP
        extract_result = self.zip_handler.extract_zip(
            zip_path=file_path,
            extract_to=temp_dir / file_path.stem,
            max_size_mb=settings.import_export_max_file_size_mb,
        )

        # Load JSON data
        import json
        with open(extract_result["data_file"], "r") as f:
            data = json.load(f)

        return data, extract_result.get("media_dir")

    def import_dayone_data(
        self,
        user_id: UUID,
        file_path: Path,
        *,
        total_entries: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        extraction_dir: Optional[Path] = None,
        media_dir: Optional[Path] = None,
    ) -> ImportResultSummary:
        """
        Import Day One export data.

        Args:
            user_id: User ID to import for
            file_path: Path to Day One ZIP file
            total_entries: Total number of entries (for progress tracking)
            progress_callback: Callback for progress updates
            extraction_dir: Optional pre-extracted directory path

        Returns:
            ImportResultSummary with statistics

        Raises:
            ValueError: If data is invalid
        """
        log_info(f"Starting Day One import for user {user_id}", user_id=str(user_id), file_path=str(file_path))

        if not extraction_dir:
            temp_dir = Path(settings.import_temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            extract_dir = temp_dir / file_path.stem
        else:
            if not extraction_dir.exists() or not extraction_dir.is_dir():
                raise ValueError(f"Extraction directory not found: {extraction_dir}")
            extract_dir = extraction_dir
        import_timestamp = utc_now()

        dayone_journals, parsed_media_dir = DayOneParser.parse_zip(
            file_path,
            extract_dir,
            is_already_extracted=extraction_dir is not None,
        )
        final_media_dir = media_dir or parsed_media_dir

        user = self.db.query(User).filter(col(User.id) == user_id).first()
        if not user:
            raise ValueError(f"User not found: {user_id}")

        export_dto = DayOneToJournivMapper.build_export(
            dayone_journals,
            import_timestamp=import_timestamp,
            user_email=user.email,
            user_name=user.name,
            app_version=settings.app_version,
            media_dir=final_media_dir,
        )

        journal_map = {j.external_id: j for j in export_dto.journals}
        entries_processed = 0
        for moment in export_dto.moments:
            entry = moment.entry
            if entry is None or not entry.external_id:
                continue
            entries_processed += 1
            if progress_callback and total_entries:
                progress_callback(entries_processed, total_entries)

            if entry.journal_external_id and entry.journal_external_id not in journal_map:
                entry.journal_external_id = None

        data = export_dto.model_dump(mode="json")
        if total_entries is None:
            total_entries = self.count_entries_in_data(data)

        return self.import_journiv_data(
            user_id=user_id,
            data=data,
            media_dir=final_media_dir,
            total_entries=total_entries,
            progress_callback=progress_callback,
        )

    def import_daylio_data(
        self,
        user_id: UUID,
        file_path: Path,
        *,
        total_entries: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        extraction_dir: Optional[Path] = None,
        media_dir: Optional[Path] = None,
    ) -> ImportResultSummary:
        """
        Import Daylio export data.
        """
        log_info(f"Starting Daylio import for user {user_id}", user_id=str(user_id), file_path=str(file_path))

        if not extraction_dir:
            temp_dir = Path(settings.import_temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            extract_dir = temp_dir / file_path.stem
        else:
            if not extraction_dir.exists() or not extraction_dir.is_dir():
                raise ValueError(f"Extraction directory not found: {extraction_dir}")
            extract_dir = extraction_dir

        import_timestamp = utc_now()

        try:
            backup, extract_root = DaylioParser.parse_zip(
                file_path,
                extract_dir,
                is_already_extracted=extraction_dir is not None,
            )
            final_media_root = media_dir or extract_root

            user = self.db.query(User).filter(col(User.id) == user_id).first()
            if not user:
                raise ValueError(f"User not found: {user_id}")

            journal_title = "Imported from Daylio"
            export_dto = DaylioToJournivMapper.build_export(
                backup,
                journal_title=journal_title,
                import_timestamp=import_timestamp,
                user_email=user.email,
                user_name=user.name,
                app_version=settings.app_version,
                media_dir=final_media_root,
            )

            data = export_dto.model_dump(mode="json")

            if total_entries is None:
                total_entries = self.count_entries_in_data(data)

            summary = self.import_journiv_data(
                user_id=user_id,
                data=data,
                media_dir=final_media_root,
                total_entries=total_entries,
                progress_callback=progress_callback,
            )

            return summary
        except Exception as e:
            self.db.rollback()
            log_error(e, user_id=str(user_id))
            raise
        finally:
            pass

    def import_journiv_data(
        self,
        user_id: UUID,
        data: Dict[str, Any],
        media_dir: Optional[Path] = None,
        *,
        total_entries: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> ImportResultSummary:
        """
        Import Journiv export data.

        Args:
            user_id: User ID to import for
            data: Parsed export data
            media_dir: Directory containing media files

        Returns:
            ImportResultSummary with statistics

        Raises:
            ValueError: If data is invalid
        """
        # Parse data into DTO
        try:
            export_dto = JournivExportDTO(**data)
        except Exception as e:
            raise ValueError(f"Invalid Journiv export format: {e}") from e

        # Initialize tracking
        summary = ImportResultSummary()
        # Track existing items for deduplication
        existing_media_checksums = self._get_existing_media_checksums(user_id)
        existing_tag_names = self._get_existing_tag_names(user_id)
        tag_lookup: Dict[str, Tag] = {}
        precreated_tag_names: set[str] = set()
        activity_lookup: Dict[str, UUID] = {}
        newly_linked_precreated_tags: set[str] = set()

        # ID maps for new entities
        mood_id_map: Dict[str, UUID] = {}
        mood_group_id_map: Dict[str, UUID] = {}
        activity_group_id_map: Dict[str, UUID] = {}
        activity_id_map: Dict[str, UUID] = {}
        goal_category_id_map: Dict[str, UUID] = {}
        goal_id_map: Dict[str, UUID] = {}
        moment_id_map: Dict[str, UUID] = {}
        journal_external_id_map: Dict[str, UUID] = {}
        default_journal_id: Optional[UUID] = None
        first_imported_journal_id: Optional[UUID] = None

        if not self._is_supported_export_version(export_dto.export_version):
            raise ValueError(
                f"Incompatible export version {export_dto.export_version}. "
                f"Expected {ExportConfig.EXPORT_VERSION} or earlier in the same major version."
            )

        if total_entries is None:
            total_entries = self.count_entries_in_data(data)

        entries_processed = 0

        def handle_entry_progress():
            nonlocal entries_processed
            entries_processed += 1
            if progress_callback and total_entries:
                progress_callback(entries_processed, total_entries)

        def record_mapping(entity_type: str, external_id: Optional[str], new_id: UUID):
            if not external_id:
                return
            summary.id_mappings.setdefault(entity_type, {})[external_id] = str(new_id)

        try:
            # Import mood definitions first (system + custom)
            if export_dto.mood_definitions:
                mood_id_map = self._import_mood_definitions(
                    user_id=user_id,
                    mood_definitions=export_dto.mood_definitions,
                    summary=summary,
                    record_mapping=record_mapping,
                )

            # Import mood groups and preferences
            if export_dto.mood_groups:
                mood_group_id_map = self._import_mood_groups(
                    user_id=user_id,
                    mood_groups=export_dto.mood_groups,
                    summary=summary,
                    record_mapping=record_mapping,
                )
            if export_dto.mood_group_links:
                self._import_mood_group_links(
                    mood_group_links=export_dto.mood_group_links,
                    mood_id_map=mood_id_map,
                    mood_group_id_map=mood_group_id_map,
                    summary=summary,
                )
            if export_dto.mood_preferences:
                self._import_mood_preferences(
                    user_id=user_id,
                    mood_preferences=export_dto.mood_preferences,
                    mood_id_map=mood_id_map,
                    summary=summary,
                )
            if export_dto.mood_group_preferences:
                self._import_mood_group_preferences(
                    user_id=user_id,
                    mood_group_preferences=export_dto.mood_group_preferences,
                    mood_group_id_map=mood_group_id_map,
                    summary=summary,
                )

            # Import activity groups/activities
            if export_dto.activity_groups:
                activity_group_id_map = self._import_activity_groups(
                    user_id=user_id,
                    activity_groups=export_dto.activity_groups,
                    summary=summary,
                    record_mapping=record_mapping,
                )
            if export_dto.activities:
                activity_id_map = self._import_activities(
                    user_id=user_id,
                    activities=export_dto.activities,
                    activity_group_id_map=activity_group_id_map,
                    summary=summary,
                    record_mapping=record_mapping,
                )

            # Import goal categories/goals
            if export_dto.goal_categories:
                goal_category_id_map = self._import_goal_categories(
                    user_id=user_id,
                    goal_categories=export_dto.goal_categories,
                    summary=summary,
                    record_mapping=record_mapping,
                )
            if export_dto.goals:
                goal_id_map = self._import_goals(
                    user_id=user_id,
                    goals=export_dto.goals,
                    activity_id_map=activity_id_map,
                    goal_category_id_map=goal_category_id_map,
                    summary=summary,
                    record_mapping=record_mapping,
                )

            # Persist entity/library imports before timeline processing.
            self.db.commit()
            # Pre-batch moment-level taxonomy entities once, after library imports.
            tag_lookup, precreated_tag_names = self._prepare_tag_lookup(
                user_id,
                export_dto.moments,
                existing_tag_names,
            )
            activity_lookup = self._prepare_activity_lookup(user_id, export_dto.moments)

            # Import journals metadata.
            for journal_dto in export_dto.journals:
                try:
                    journal = Journal(
                        user_id=user_id,
                        title=journal_dto.title,
                        description=journal_dto.description,
                        color=(
                            JournalColor(journal_dto.color.upper())
                            if journal_dto.color and journal_dto.color.upper() in JournalColor.__members__
                            else None
                        ),
                        icon=journal_dto.icon,
                        is_favorite=journal_dto.is_favorite,
                        is_archived=journal_dto.is_archived,
                        import_metadata=journal_dto.import_metadata,
                        created_at=journal_dto.created_at,
                        updated_at=journal_dto.updated_at,
                    )
                    self.db.add(journal)
                    self.db.flush()
                    self.db.commit()
                    if first_imported_journal_id is None:
                        first_imported_journal_id = journal.id
                    summary.journals_created += 1
                    if journal_dto.external_id:
                        journal_external_id_map[journal_dto.external_id] = journal.id
                        if record_mapping:
                            record_mapping("journals", journal_dto.external_id, journal.id)
                except (ValueError, SQLAlchemyError) as journal_error:
                    self.db.rollback()
                    warning_msg = (
                        f"Failed to import journal '{journal_dto.title}': {journal_error}"
                    )
                    log_error(journal_error, user_id=str(user_id), journal_title=journal_dto.title)
                    self._add_warning(summary, warning_msg, "Skipped (journal error)")

            # Prefer reusing an imported journal as fallback to avoid creating
            # an extra "Auto-created for moment-first import" journal when
            # external ID linkage is absent or mismatched.
            if default_journal_id is None:
                if len(journal_external_id_map) == 1:
                    default_journal_id = next(iter(journal_external_id_map.values()))
                elif first_imported_journal_id is not None:
                    default_journal_id = first_imported_journal_id

            if export_dto.moments:
                for moment_dto in export_dto.moments:
                    try:
                        with self.db.begin_nested():
                            if moment_dto.entry is not None:
                                entry_result = self._import_entry_from_moment(
                                    user_id=user_id,
                                    moment_dto=moment_dto,
                                    media_dir=media_dir,
                                    existing_media_checksums=existing_media_checksums,
                                    existing_tag_names=existing_tag_names,
                                    summary=summary,
                                    mood_id_map=mood_id_map,
                                    activity_id_map=activity_id_map,
                                    moment_id_map=moment_id_map,
                                    journal_external_id_map=journal_external_id_map,
                                    default_journal_id=default_journal_id,
                                    record_mapping=record_mapping,
                                    tag_lookup=tag_lookup,
                                    precreated_tag_names=precreated_tag_names,
                                    newly_linked_precreated_tags=newly_linked_precreated_tags,
                                    activity_lookup=activity_lookup,
                                )
                                default_journal_id = entry_result["default_journal_id"]
                                created_moment = entry_result["moment"]
                                created_entry = True
                            else:
                                created_moment = self._import_moment(
                                    user_id=user_id,
                                    moment_dto=moment_dto,
                                    media_dir=media_dir,
                                    existing_media_checksums=existing_media_checksums,
                                    summary=summary,
                                    existing_tag_names=existing_tag_names,
                                    record_mapping=record_mapping,
                                    mood_id_map=mood_id_map,
                                    activity_id_map=activity_id_map,
                                    tag_lookup=tag_lookup,
                                    precreated_tag_names=precreated_tag_names,
                                    newly_linked_precreated_tags=newly_linked_precreated_tags,
                                    activity_lookup=activity_lookup,
                                )
                                created_entry = False

                        self.db.commit()
                        if created_entry:
                            summary.entries_created += 1
                            handle_entry_progress()
                            continue
                        if created_moment and hasattr(summary, "moments_created"):
                            summary.moments_created += 1
                        if created_moment and moment_dto.external_id:
                            moment_id_map[moment_dto.external_id] = created_moment.id
                    except Exception as moment_error:
                        warning_msg = f"Failed to import moment: {moment_error}"
                        log_warning(warning_msg, user_id=str(user_id))
                        self._add_warning(summary, warning_msg, "Skipped (moment error)")

            # Import goal logs after moments are created (to preserve moment references)
            if export_dto.goal_logs or export_dto.goal_manual_logs:
                try:
                    if export_dto.goal_logs:
                        self._import_goal_logs(
                            user_id=user_id,
                            goal_logs=export_dto.goal_logs,
                            goal_id_map=goal_id_map,
                            moment_id_map=moment_id_map,
                            summary=summary,
                            record_mapping=record_mapping,
                        )
                    if export_dto.goal_manual_logs:
                        self._import_goal_manual_logs(
                            user_id=user_id,
                            goal_manual_logs=export_dto.goal_manual_logs,
                            goal_id_map=goal_id_map,
                            summary=summary,
                            record_mapping=record_mapping,
                        )
                    self.db.commit()
                except Exception as goal_log_error:
                    self.db.rollback()
                    warning_msg = f"Failed to import goal logs: {goal_log_error}"
                    log_warning(warning_msg, user_id=str(user_id))
                    self._add_warning(summary, warning_msg, "Skipped (goal log error)")

            # Moment-first imports bypass per-entry journal stat updates.
            # Reuse JournalService recalculation logic for all user journals.
            try:
                journal_service = JournalService(self.db)
                journal_ids = self.db.execute(
                    select(Journal.id).where(Journal.user_id == user_id)
                ).scalars().all()
                for journal_id in journal_ids:
                    try:
                        journal_service.recalculate_journal_entry_count(journal_id, user_id)
                    except Exception as recalc_error:
                        log_error(
                            recalc_error,
                            user_id=str(user_id),
                            journal_id=str(journal_id),
                            context="journal_recalculation_failed_after_import",
                        )
                        self._add_warning(
                            summary,
                            f"Failed to recalculate journal stats for {journal_id}: {recalc_error}",
                            "Stats recalculation warning",
                        )
            except Exception as recalc_setup_error:
                log_error(
                    recalc_setup_error,
                    user_id=str(user_id),
                    context="journal_recalculation_setup_failed_after_import",
                )
                self._add_warning(
                    summary,
                    f"Failed to run post-import journal stats recalculation: {recalc_setup_error}",
                    "Stats recalculation warning",
                )

            log_info(
                f"Import completed: {summary.journals_created} journals, "
                f"{summary.entries_created} entries, "
                f"{summary.media_files_imported} media files",
                user_id=str(user_id),
                journals_created=summary.journals_created,
                entries_created=summary.entries_created,
                media_files_imported=summary.media_files_imported
            )

            if summary.warnings:
                log_info(f"Import completed with {len(summary.warnings)} warnings", user_id=str(user_id), warning_count=len(summary.warnings))

            return summary

        except Exception as e:
            # Rollback on error
            self.db.rollback()
            log_error(e, user_id=str(user_id))
            raise

    def _import_entry_from_moment(
        self,
        user_id: UUID,
        moment_dto: MomentDTO,
        media_dir: Optional[Path],
        existing_media_checksums: set,
        existing_tag_names: set,
        summary: ImportResultSummary,
        mood_id_map: Dict[str, UUID],
        activity_id_map: Dict[str, UUID],
        moment_id_map: Dict[str, UUID],
        journal_external_id_map: Dict[str, UUID],
        default_journal_id: Optional[UUID],
        record_mapping: Optional[Callable[[str, Optional[str], UUID], None]] = None,
        tag_lookup: Optional[Dict[str, Tag]] = None,
        precreated_tag_names: Optional[set[str]] = None,
        newly_linked_precreated_tags: Optional[set[str]] = None,
        activity_lookup: Optional[Dict[str, UUID]] = None,
    ) -> Dict[str, Any]:
        entry_dto = moment_dto.entry
        if entry_dto is None:
            raise ValueError("Moment.entry is required")

        journal_id = (
            journal_external_id_map.get(entry_dto.journal_external_id)
            if entry_dto.journal_external_id
            else None
        )
        if journal_id is None:
            if entry_dto.journal_external_id:
                warning_msg = (
                    f"Journal external ID '{entry_dto.journal_external_id}' not found; "
                    "using default imported journal"
                )
                self._add_warning(summary, warning_msg, "Skipped (missing journal)")
            if default_journal_id is None:
                default_journal = Journal(
                    user_id=user_id,
                    title="Imported Journal",
                    description="Auto-created for moment-first import",
                    color=None,
                    icon=None,
                    is_favorite=False,
                    is_archived=False,
                )
                self.db.add(default_journal)
                self.db.flush()
                default_journal_id = default_journal.id
            journal_id = default_journal_id

        # Create moment (context + media + tags).
        moment = self._import_moment(
            user_id=user_id,
            moment_dto=moment_dto,
            media_dir=media_dir,
            existing_media_checksums=existing_media_checksums,
            summary=summary,
            existing_tag_names=existing_tag_names,
            record_mapping=record_mapping,
            mood_id_map=mood_id_map,
            activity_id_map=activity_id_map,
            tag_lookup=tag_lookup,
            precreated_tag_names=precreated_tag_names,
            newly_linked_precreated_tags=newly_linked_precreated_tags,
            activity_lookup=activity_lookup,
        )
        if moment is None:
            raise ValueError("Failed to import moment for entry")
        if moment_dto.external_id:
            moment_id_map[moment_dto.external_id] = moment.id
        summary.moments_created += 1

        content_delta = entry_dto.content_delta or wrap_plain_text(entry_dto.content_plain_text)
        plain_text = entry_dto.content_plain_text or extract_plain_text(content_delta)
        word_count = len(plain_text.split()) if plain_text else 0

        entry = Entry(
            journal_id=journal_id,
            user_id=user_id,
            moment_id=moment.id,
            title=entry_dto.title,
            content_delta=content_delta,
            content_plain_text=plain_text or None,
            word_count=word_count,
            is_draft=entry_dto.is_draft or False,
            import_metadata=entry_dto.import_metadata,
            created_at=entry_dto.created_at,
            updated_at=entry_dto.updated_at,
        )
        self.db.add(entry)
        self.db.flush()
        if record_mapping and entry_dto.external_id:
            record_mapping("entries", entry_dto.external_id, entry.id)

        # Replace placeholder media IDs in delta with imported media UUIDs.
        imported_media = self.db.execute(
            select(MomentMedia).where(col(MomentMedia.moment_id) == moment.id)
        ).scalars().all()
        media_id_map: Dict[str, str] = {}
        for media_record in imported_media:
            mapped_id = str(media_record.id)
            if media_record.external_asset_id:
                media_id_map[media_record.external_asset_id] = mapped_id

        for media_dto in moment_dto.media:
            export_media_id = self._extract_export_media_id(media_dto.file_path)
            if export_media_id and media_dto.external_asset_id in media_id_map:
                media_id_map[export_media_id] = media_id_map[media_dto.external_asset_id]
            if media_dto.external_id and media_dto.external_asset_id in media_id_map:
                media_id_map[media_dto.external_id] = media_id_map[media_dto.external_asset_id]

        # Daylio and other imports may use media.external_id placeholders directly
        # in entry delta embeds. Resolve those placeholders using recorded ID mappings.
        media_mappings = summary.id_mappings.get("media", {})
        for media_dto in moment_dto.media:
            if media_dto.external_id and media_dto.external_id in media_mappings:
                media_id_map[media_dto.external_id] = media_mappings[media_dto.external_id]

        placeholder_map = self._build_dayone_placeholder_map(
            entry_dto,
            moment_dto.media,
            media_id_map,
        )
        replacement_map = dict(media_id_map)
        replacement_map.update(placeholder_map)
        if entry.content_delta and replacement_map:
            entry.content_delta = self._replace_media_ids_in_delta(entry.content_delta, replacement_map)
            updated_plain = extract_plain_text(entry.content_delta)
            entry.content_plain_text = updated_plain or None
            entry.word_count = len(updated_plain.split()) if updated_plain else 0

        return {
            "default_journal_id": default_journal_id,
            "moment": moment,
        }

    def _get_or_create_activity(self, user_id: UUID, activity_name: str) -> Optional[Activity]:
        if not activity_name:
            return None
        name = activity_name.strip()
        if not name:
            return None
        existing = (
            self.db.execute(
                select(Activity).where(
                    col(Activity.user_id) == user_id,
                    func.lower(col(Activity.name)) == name.lower(),
                )
            )
            .scalars()
            .first()
        )
        if existing:
            return existing
        activity = Activity(user_id=user_id, name=name)
        self.db.add(activity)
        self.db.flush()
        return activity

    def _resolve_mood_id(
        self,
        user_id: UUID,
        mood_name: Optional[str],
        mood_external_id: Optional[str],
        mood_id_map: Dict[str, UUID],
    ) -> Optional[UUID]:
        if mood_external_id and mood_external_id in mood_id_map:
            return mood_id_map[mood_external_id]
        if not mood_name:
            return None
        mood = (
            self.db.execute(
                select(Mood)
                .where(
                    func.lower(Mood.name) == mood_name.lower(),
                    col(Mood.user_id) == user_id,
                )
            )
            .scalars()
            .first()
        )
        return mood.id if mood else None

    def _resolve_activity_id(
        self,
        user_id: UUID,
        activity_name: Optional[str],
        activity_external_id: Optional[str],
        activity_id_map: Dict[str, UUID],
        activity_lookup: Optional[Dict[str, UUID]] = None,
    ) -> Optional[UUID]:
        if activity_external_id and activity_external_id in activity_id_map:
            return activity_id_map[activity_external_id]
        if not activity_name:
            return None
        if activity_lookup:
            lookup_id = activity_lookup.get(activity_name.strip().lower())
            if lookup_id:
                return lookup_id
        activity = self._get_or_create_activity(user_id, activity_name)
        return activity.id if activity else None

    def _import_moment(
        self,
        user_id: UUID,
        moment_dto: MomentDTO,
        media_dir: Optional[Path],
        existing_media_checksums: set,
        summary: ImportResultSummary,
        existing_tag_names: set,
        record_mapping: Optional[Callable[[str, Optional[str], UUID], None]] = None,
        mood_id_map: Optional[Dict[str, UUID]] = None,
        activity_id_map: Optional[Dict[str, UUID]] = None,
        tag_lookup: Optional[Dict[str, Tag]] = None,
        precreated_tag_names: Optional[set[str]] = None,
        newly_linked_precreated_tags: Optional[set[str]] = None,
        activity_lookup: Optional[Dict[str, UUID]] = None,
    ) -> Optional[Moment]:
        mood_id_map = mood_id_map or {}
        activity_id_map = activity_id_map or {}

        logged_at_utc = moment_dto.logged_at_utc or utc_now()
        logged_timezone = normalize_timezone(moment_dto.logged_timezone)
        logged_date_tz = local_date_for_user(logged_at_utc, logged_timezone)

        moment = Moment(
            user_id=user_id,
            primary_mood_id=None,
            logged_at_utc=logged_at_utc,
            logged_date_tz=logged_date_tz,
            logged_timezone=logged_timezone,
            note=moment_dto.note,
            location_json=moment_dto.location_json,
            latitude=moment_dto.latitude,
            longitude=moment_dto.longitude,
            weather_json=moment_dto.weather_json,
            weather_summary=moment_dto.weather_summary,
            is_pinned=moment_dto.is_pinned,
            created_at=moment_dto.created_at or utc_now(),
            updated_at=moment_dto.updated_at or utc_now(),
        )
        self.db.add(moment)
        self.db.flush()

        if moment_dto.primary_mood_name or moment_dto.primary_mood_external_id:
            mood_id = self._resolve_mood_id(
                user_id=user_id,
                mood_name=moment_dto.primary_mood_name,
                mood_external_id=moment_dto.primary_mood_external_id,
                mood_id_map=mood_id_map,
            )
            if mood_id:
                moment.primary_mood_id = mood_id
            else:
                warning_msg = (
                    f"Mood not found: '{moment_dto.primary_mood_name or moment_dto.primary_mood_external_id}', "
                    "skipping moment primary mood"
                )
                log_warning(warning_msg, user_id=str(user_id), mood_name=moment_dto.primary_mood_name)
                summary.warnings.append(warning_msg)

        links_created = 0
        for item in moment_dto.mood_activity:
            mood_id = self._resolve_mood_id(
                user_id=user_id,
                mood_name=item.mood_name,
                mood_external_id=item.mood_external_id,
                mood_id_map=mood_id_map,
            )
            if mood_id is None and item.mood_name:
                warning_msg = f"Mood not found: '{item.mood_name}', skipping moment mood link"
                log_warning(warning_msg, user_id=str(user_id), mood_name=item.mood_name)
                summary.warnings.append(warning_msg)

            activity_id = self._resolve_activity_id(
                user_id=user_id,
                activity_name=item.activity_name,
                activity_external_id=item.activity_external_id,
                activity_id_map=activity_id_map,
                activity_lookup=activity_lookup,
            )
            if mood_id is None and activity_id is None:
                continue
            self.db.add(
                MomentMoodActivity(
                    moment_id=moment.id,
                    mood_id=mood_id,
                    activity_id=activity_id,
                )
            )
            links_created += 1

        if links_created == 0 and moment.primary_mood_id:
            self.db.add(
                MomentMoodActivity(
                    moment_id=moment.id,
                    mood_id=moment.primary_mood_id,
                    activity_id=None,
                )
            )

        for media_dto in moment_dto.media:
            try:
                media_result = self._import_media(
                    moment_id=moment.id,
                    user_id=user_id,
                    media_dto=media_dto,
                    media_dir=media_dir,
                    existing_checksums=existing_media_checksums,
                    summary=summary,
                    record_mapping=record_mapping,
                )
                if media_result["imported"]:
                    summary.media_files_imported += 1
                elif media_result.get("deduplicated"):
                    summary.media_files_deduplicated += 1
            except Exception as media_error:
                warning_msg = (
                    f"Failed to import media '{media_dto.filename}' for moment "
                    f"{moment_dto.external_id or moment.id}: {media_error}"
                )
                log_warning(
                    warning_msg,
                    user_id=str(user_id),
                    moment_id=str(moment.id),
                    media_filename=media_dto.filename,
                )
                self._add_warning(summary, warning_msg, "Skipped (media error)")
                summary.media_files_skipped += 1

        for tag_name in {t.strip().lower() for t in moment_dto.tags if t and t.strip()}:
            tag_result = self._import_tag(
                moment_id=moment.id,
                user_id=user_id,
                tag_name=tag_name,
                existing_tag_names=existing_tag_names,
                tag_lookup=tag_lookup,
                precreated_tag_names=precreated_tag_names,
                newly_linked_precreated_tags=newly_linked_precreated_tags,
            )
            if tag_result["created"]:
                summary.tags_created += 1
            else:
                summary.tags_reused += 1

        if record_mapping:
            external_id = moment_dto.external_id
            if external_id:
                record_mapping("moments", external_id, moment.id)

        self.db.flush()
        return moment

    def _handle_entry_media_race_condition(
        self,
        moment_id: UUID,
        checksum: str,
        user_id: UUID,
        media_dto: MomentMediaDTO,
        source_md5: Optional[str],
        record_mapping: Optional[Callable[[str, Optional[str], UUID], None]] = None,
        context: str = "race condition",
    ) -> Optional[Dict[str, Any]]:
        """
        Handle race condition where MomentMedia was created by concurrent import.

        Args:
            moment_id: Moment ID
            checksum: Media checksum
            user_id: User ID
            media_dto: Media DTO
            source_md5: Source MD5 (for Day One imports)
            record_mapping: Optional mapping function for external IDs
            context: Context string for logging (e.g., "race condition", "race condition during deduplication")

        Returns:
            Result dict if existing MomentMedia found, None otherwise
        """
        filters = [
            col(MomentMedia.checksum) == checksum,
            col(MomentMedia.moment_id) == moment_id,
        ]

        existing_entry_media = self.db.query(MomentMedia).filter(*filters).first()

        if existing_entry_media:
            log_info(
                f"Media already associated with moment ({context}), using existing record",
                checksum=checksum,
                user_id=str(user_id),
                moment_id=str(moment_id),
                media_id=str(existing_entry_media.id)
            )
            if record_mapping and media_dto.external_id:
                record_mapping("media", media_dto.external_id, existing_entry_media.id)

            return {
                "imported": False,
                "deduplicated": True,
                "stored_relative_path": existing_entry_media.file_path,
                "stored_filename": Path(existing_entry_media.file_path or "").name,
                "source_md5": source_md5,
                "media_id": str(existing_entry_media.id),
            }

        return None

    def _import_media(
        self,
        moment_id: UUID,
        user_id: UUID,
        media_dto: MomentMediaDTO,
        media_dir: Optional[Path],
        existing_checksums: set,
        summary: ImportResultSummary,
        record_mapping: Optional[Callable[[str, Optional[str], UUID], None]] = None,
    ) -> Dict[str, Any]:
        """
        Import a media file with deduplication.

        Returns:
            {"imported": True/False, "deduplicated": True/False, "stored_relative_path": str | None, "media_id": str | None}
        """
        # Check if media is external-only (no local file expected)
        # We treat None or empty string file_path as "no local file"
        is_external_link_only = media_dto.external_provider is not None and not media_dto.file_path

        # Check if media file exists in media_dir
        # Skip check if this is an external link-only media
        if not media_dir and not is_external_link_only:
            warning_msg = f"No media directory, skipping media: {media_dto.filename}"
            log_warning(
                warning_msg,
                user_id=str(user_id),
                media_filename=media_dto.filename,
                moment_id=str(moment_id),
            )
            summary.warnings.append(warning_msg)
            summary.media_files_skipped += 1
            return {"imported": False, "deduplicated": False, "stored_relative_path": None, "media_id": None}

        if not media_dto.file_path and not media_dto.external_provider:
            warning_msg = f"Missing file_path for media: {media_dto.filename}"
            log_warning(
                warning_msg,
                user_id=str(user_id),
                media_filename=media_dto.filename,
                moment_id=str(moment_id),
            )
            summary.warnings.append(warning_msg)
            summary.media_files_skipped += 1
            return {"imported": False, "deduplicated": False, "stored_relative_path": None, "media_id": None}


        # If it's external only, we skip file system checks
        if is_external_link_only:
            # Create new external media record
            # Normalize file_size to None if not positive (external assets might report 0)
            file_size = media_dto.file_size if media_dto.file_size and media_dto.file_size > 0 else None
            media = self._create_media_record(
                moment_id=moment_id,
                file_path=None,
                media_dto=media_dto,
                checksum=media_dto.checksum,
                file_size=file_size
            )
            self.db.add(media)
            # Commit happens at journal level, but we need ID
            self.db.flush()

            if record_mapping and media_dto.external_id:
                record_mapping("media", media_dto.external_id, media.id)

            return {
                "imported": True,
                "deduplicated": False,
                "stored_relative_path": None,
                "stored_filename": media_dto.filename,
                "source_md5": None,
                "media_id": str(media.id),
            }

        if media_dir is None:
            warning_msg = f"No media directory, skipping media: {media_dto.filename}"
            log_warning(warning_msg, user_id=str(user_id), media_filename=media_dto.filename, moment_id=str(moment_id))
            summary.warnings.append(warning_msg)
            summary.media_files_skipped += 1
            return {"imported": False, "deduplicated": False, "stored_relative_path": None, "media_id": None}

        if media_dto.file_path is None:
            warning_msg = f"Missing file_path for media: {media_dto.filename}"
            log_warning(warning_msg, user_id=str(user_id), media_filename=media_dto.filename, moment_id=str(moment_id))
            summary.warnings.append(warning_msg)
            summary.media_files_skipped += 1
            return {"imported": False, "deduplicated": False, "stored_relative_path": None, "media_id": None}

        source_path = Path(media_dto.file_path)
        if not source_path.is_absolute():
            source_path = media_dir / source_path

        # Ensure media lives under the extracted media directory to prevent traversal
        resolved_source = source_path.resolve()
        media_root = media_dir.resolve()
        try:
            resolved_source.relative_to(media_root)
        except ValueError:
            warning_msg = f"Media file outside expected directory: {resolved_source}"
            log_warning(
                warning_msg,
                user_id=str(user_id),
                media_filename=media_dto.filename,
                file_path=media_dto.file_path,
                moment_id=str(moment_id),
            )
            self._add_warning(summary, warning_msg, "Security warning")
            summary.media_files_skipped += 1
            return {"imported": False, "deduplicated": False, "stored_relative_path": None, "media_id": None}

        if not resolved_source.exists():
            warning_msg = f"Media file not found: {resolved_source}"
            log_warning(
                warning_msg,
                user_id=str(user_id),
                media_filename=media_dto.filename,
                file_path=str(resolved_source),
                moment_id=str(moment_id),
            )
            self._add_warning(summary, warning_msg, "Skipped (missing media)")
            summary.media_files_skipped += 1
            return {"imported": False, "deduplicated": False, "stored_relative_path": None, "media_id": None}

        # Normalize to resolved path for subsequent operations
        source_path = resolved_source

        # Detect Day One md5 from filename (stem)
        # Day One export filenames for media use the MD5 hash as the filename stem per Day One's export format,
        # so extracting source_path.stem yields the media MD5. When that convention isn't present, the code
        # falls back to external_id (see usage around line 712). Maintainers should consult Day One export
        # docs if behavior changes.
        source_md5 = source_path.stem if source_path.stem else None

        # Early deduplication check: If checksum is provided in DTO (e.g., from Journiv export),
        # check for existing MomentMedia before storing the file to avoid unnecessary I/O
        # For external media, checksum might be None, so we skip this check if media is strictly external and has no checksum
        if media_dto.checksum:
            early_filters = [
                col(MomentMedia.checksum) == media_dto.checksum,
                col(MomentMedia.moment_id) == moment_id,
            ]

            existing_entry_media = self.db.query(MomentMedia).filter(*early_filters).first()

            if existing_entry_media:
                log_info(
                    "Media already associated with moment (early check), skipping duplicate",
                    checksum=media_dto.checksum,
                    user_id=str(user_id),
                    moment_id=str(moment_id),
                    media_id=str(existing_entry_media.id)
                )
                if record_mapping and media_dto.external_id:
                    record_mapping("media", media_dto.external_id, existing_entry_media.id)

                return {
                    "imported": False,
                    "deduplicated": True,
                    "stored_relative_path": existing_entry_media.file_path,
                    "stored_filename": Path(existing_entry_media.file_path or "").name,
                    "source_md5": source_md5,
                    "media_id": str(existing_entry_media.id),
                }

        # Choose media subdirectory based on type
        media_type_str = media_dto.media_type.lower() if media_dto.media_type else "unknown"
        if media_type_str.startswith("image"):
            media_type_dir = "images"
        elif media_type_str.startswith("video"):
            media_type_dir = "videos"
        elif media_type_str.startswith("audio"):
            media_type_dir = "audio"
        else:
            media_type_dir = "images"  # Default to images for unknown types

        # Store media using unified storage service (per-user deduplication)
        relative_path, checksum, was_deduplicated = self.media_storage_service.store_media(
            source=source_path,
            user_id=str(user_id),
            media_type=media_type_dir,
            extension=source_path.suffix,
            checksum=media_dto.checksum  # Use DTO checksum if available, otherwise will be calculated
        )

        # Track checksum for in-memory deduplication tracking
        existing_checksums.add(checksum)

        # Check if MomentMedia record already exists for this moment and checksum
        # This prevents duplicate media within the same moment (handles cases where checksum wasn't in DTO)
        dedupe_filters = [
            col(MomentMedia.checksum) == checksum,
            col(MomentMedia.moment_id) == moment_id,
        ]

        existing_entry_media = self.db.query(MomentMedia).filter(*dedupe_filters).first()

        if existing_entry_media:
            log_info(
                "Media already associated with moment, skipping duplicate",
                checksum=checksum,
                user_id=str(user_id),
                moment_id=str(moment_id),
                media_id=str(existing_entry_media.id)
            )
            if record_mapping and media_dto.external_id:
                record_mapping("media", media_dto.external_id, existing_entry_media.id)

            return {
                "imported": False,
                "deduplicated": True,
                "stored_relative_path": existing_entry_media.file_path,
                "stored_filename": Path(existing_entry_media.file_path or "").name,
                "source_md5": source_md5,
                "media_id": str(existing_entry_media.id),
            }

        # If deduplicated, find existing media and create reference
        if was_deduplicated:
            existing_media = (
                self.db.query(MomentMedia)
                .join(Moment, col(MomentMedia.moment_id) == col(Moment.id))
                .filter(
                    col(MomentMedia.checksum) == checksum,
                    col(Moment.user_id) == user_id,
                )
                .first()
            )

            if existing_media:
                # Create new MomentMedia record referencing the same file
                media = MomentMedia(
                    moment_id=moment_id,
                    file_path=existing_media.file_path,
                    original_filename=media_dto.filename,
                    media_type=existing_media.media_type,
                    file_size=existing_media.file_size,
                    mime_type=existing_media.mime_type,
                    checksum=checksum,
                    thumbnail_path=existing_media.thumbnail_path,
                    display_path=existing_media.display_path,
                    width=existing_media.width,
                    height=existing_media.height,
                    duration=existing_media.duration,
                    alt_text=media_dto.alt_text or media_dto.caption,
                    upload_status=existing_media.upload_status,
                    file_metadata=existing_media.file_metadata,
                    external_provider=existing_media.external_provider,
                    external_asset_id=existing_media.external_asset_id,
                    external_url=existing_media.external_url,
                    external_created_at=existing_media.external_created_at,
                    external_metadata=existing_media.external_metadata,
                    created_at=media_dto.created_at,
                    updated_at=media_dto.updated_at,
                )
                try:
                    self.db.add(media)
                    self.db.flush()
                except IntegrityError as exc:
                    # Race condition: MomentMedia was created by concurrent import
                    if "uq_moment_media_moment_checksum" in str(exc):
                        result = self._handle_entry_media_race_condition(
                            moment_id=moment_id,
                            checksum=checksum,
                            user_id=user_id,
                            media_dto=media_dto,
                            source_md5=source_md5,
                            record_mapping=record_mapping,
                            context="race condition during deduplication"
                        )
                        if result:
                            return result
                    raise
                except SQLAlchemyError as exc:
                    log_error(
                        exc,
                        user_id=str(user_id),
                        moment_id=str(moment_id),
                        checksum=checksum,
                    )
                    raise

                if record_mapping and media_dto.external_id:
                    record_mapping("media", media_dto.external_id, media.id)

                log_info(
                    "Media deduplicated during import",
                    checksum=checksum,
                    user_id=str(user_id),
                    relative_path=relative_path
                )

                return {
                    "imported": False,
                    "deduplicated": True,
                    "stored_relative_path": existing_media.file_path,
                    "stored_filename": Path(existing_media.file_path or "").name,
                    "source_md5": source_md5,
                    "media_id": str(media.id),
                }

        # File is new - create media record
        # For external media (link-only), we might not have a local file

        full_path = None
        if media_dto.external_provider is not None and media_dto.file_path is None:
             # External media without local file (link-only)
             file_size = media_dto.file_size
        else:
            full_path = self.media_storage_service.get_full_path(relative_path)
            file_size = full_path.stat().st_size

        media = self._create_media_record(
            moment_id=moment_id,
            file_path=relative_path, # This might be None for pure external links if logic allowed it, but here relative_path is derived from storage service
            media_dto=media_dto,
            checksum=checksum,
            file_size=file_size,
        )

        try:
            self.db.add(media)
            self.db.flush()
        except IntegrityError as exc:
            # Race condition: MomentMedia was created by concurrent import
            if "uq_moment_media_moment_checksum" in str(exc):
                result = self._handle_entry_media_race_condition(
                    moment_id=moment_id,
                    checksum=checksum,
                    user_id=user_id,
                    media_dto=media_dto,
                    source_md5=source_md5,
                    record_mapping=record_mapping,
                    context="race condition"
                )
                if result:
                    return result
            raise
        except SQLAlchemyError as exc:
            log_error(exc, user_id=str(user_id), moment_id=str(moment_id), checksum=checksum)
            raise

        # Generate thumbnail for imported media
        if media.media_type in [MediaType.IMAGE, MediaType.VIDEO]:
            try:
                from app.services.media_service import MediaService
                media_service = MediaService(cast(Any, self.db))

                # Generate thumbnail synchronously
                if full_path is None:
                    # Can't generate thumbnail for external link-only media without download
                    # Assuming external_provider might handle thumbnails or we rely on external_url
                    pass
                elif not full_path.exists():
                    log_warning(f"Media file not found for thumbnail generation: {full_path}", media_id=str(media.id), file_path=str(full_path))
                else:
                    thumbnail_path = media_service._generate_thumbnail(
                        str(full_path),
                        media.media_type
                    )

                    if thumbnail_path:
                        # Convert to relative path
                        media.thumbnail_path = media_service._relative_thumbnail_path(Path(thumbnail_path))
                        log_info(f"Generated thumbnail for imported media: {media.id}", media_id=str(media.id))
            except Exception as thumb_error:
                # Log but don't fail import if thumbnail generation fails
                self._add_warning(summary, f"Failed to generate thumbnail for imported media {media.id}: {thumb_error}", "Thumbnail warning")
                log_warning(f"Failed to generate thumbnail for imported media {media.id}: {thumb_error}", media_id=str(media.id))

        if record_mapping and media_dto.external_id:
            record_mapping("media", media_dto.external_id, media.id)

        return {
            "imported": True,
            "deduplicated": False,
            "stored_relative_path": relative_path,
            "stored_filename": Path(relative_path).name,
            "source_md5": source_md5,
            "media_id": str(media.id),
        }

    def _parse_media_type(self, media_type_str: str) -> MediaType:
        """Parse media type string to enum."""
        try:
            return MediaType(media_type_str.lower())
        except ValueError:
            log_warning(f"Invalid media type: {media_type_str}, using UNKNOWN", media_type=media_type_str)
            return MediaType.UNKNOWN

    def _parse_upload_status(self, status_str: str) -> UploadStatus:
        """Parse upload status string to enum."""
        try:
            return UploadStatus(status_str.lower())
        except ValueError:
            log_warning(f"Invalid upload status: {status_str}, using COMPLETED", upload_status=status_str)
            return UploadStatus.COMPLETED

    def _create_media_record(
        self,
        moment_id: UUID,
        file_path: Optional[str],
        media_dto: MomentMediaDTO,
        checksum: Optional[str],
        file_size: Optional[int] = None,
    ) -> MomentMedia:
        """
        Create an MomentMedia record from DTO.

        This is a helper method to reduce code duplication between
        new media imports and deduplicated media records.

        Args:
            moment_id: Moment ID to associate media with
            file_path: Relative path to media file (optional for external media)
            media_dto: Media DTO with metadata
            checksum: File checksum (optional for external media)
            file_size: Optional file size override (uses DTO value if not provided)

        Returns:
            Created MomentMedia instance (not yet added to session)
        """
        media_type = self._parse_media_type(media_dto.media_type)
        upload_status = self._parse_upload_status(media_dto.upload_status)

        # Imported local files already exist on disk; don't leave them in pending/processing.
        if file_path and upload_status in (UploadStatus.PENDING, UploadStatus.PROCESSING):
            upload_status = UploadStatus.COMPLETED

        # Sanitization: Reset 0 dimensions to None to satisfy DB constraints
        width = media_dto.width if media_dto.width and media_dto.width > 0 else None
        height = media_dto.height if media_dto.height and media_dto.height > 0 else None

        return MomentMedia(
            moment_id=moment_id,
            file_path=file_path,
            original_filename=media_dto.filename,
            media_type=media_type,
            file_size=file_size,
            mime_type=media_dto.mime_type,
            checksum=checksum,
            thumbnail_path=media_dto.thumbnail_path,
            width=width,
            height=height,
            duration=media_dto.duration,
            alt_text=media_dto.alt_text or media_dto.caption,
            upload_status=upload_status,
            file_metadata=media_dto.file_metadata,
            created_at=media_dto.created_at,
            updated_at=media_dto.updated_at,
            # External provider fields
            external_provider=media_dto.external_provider,
            external_asset_id=media_dto.external_asset_id,
            external_url=media_dto.external_url,
            external_created_at=media_dto.external_created_at,
            external_metadata=media_dto.external_metadata,
        )

    def _import_tag(
        self,
        moment_id: UUID,
        user_id: UUID,
        tag_name: str,
        existing_tag_names: set,
        tag_lookup: Optional[Dict[str, Tag]] = None,
        precreated_tag_names: Optional[set[str]] = None,
        newly_linked_precreated_tags: Optional[set[str]] = None,
    ) -> Dict[str, bool]:
        """
        Import a tag with deduplication.

        Uses existing_tag_names for fast-path check before querying DB.

        Returns:
            {"created": True/False}
        """
        tag_name_lower = tag_name.strip().lower()

        tag = tag_lookup.get(tag_name_lower) if tag_lookup else None
        if not tag:
            tag = (
                self.db.query(Tag)
                .filter(
                    col(Tag.user_id) == user_id,
                    col(Tag.name) == tag_name_lower
                )
                .first()
            )

        created = False
        if not tag:
            # Tag doesn't exist, create it
            tag = Tag(user_id=user_id, name=tag_name_lower)
            self.db.add(tag)
            self.db.flush()
            existing_tag_names.add(tag_name_lower)
            created = True
            if tag_lookup is not None:
                tag_lookup[tag_name_lower] = tag
        elif tag_name_lower not in existing_tag_names:
            # Tag exists in DB but not in cache, update cache
            existing_tag_names.add(tag_name_lower)
        elif (
            precreated_tag_names is not None
            and newly_linked_precreated_tags is not None
            and tag_name_lower in precreated_tag_names
            and tag_name_lower not in newly_linked_precreated_tags
        ):
            # Preserve summary semantics: first linked use of a precreated tag counts as created.
            created = True
            newly_linked_precreated_tags.add(tag_name_lower)

        # Link tag to moment
        from app.models.moment_tag_link import MomentTagLink
        link = MomentTagLink(moment_id=moment_id, tag_id=tag.id)
        self.db.add(link)

        return {"created": created}

    def _get_existing_media_checksums(self, user_id: UUID) -> set:
        """Get set of existing media checksums for user."""
        checksums = self.db.execute(
            select(MomentMedia.checksum)
            .join(Moment, col(MomentMedia.moment_id) == col(Moment.id))
            .where(
                col(Moment.user_id) == user_id,
                col(MomentMedia.checksum).is_not(None)
            )
        ).all()
        return {c[0] for c in checksums if c[0]}

    def _get_existing_tag_names(self, user_id: UUID) -> set:
        """Get set of existing tag names for user (lowercase)."""
        tags = self.db.execute(
            select(Tag.name).where(Tag.user_id == user_id)
        ).all()
        return {t[0].lower() for t in tags}

    def _prepare_tag_lookup(
        self,
        user_id: UUID,
        moments: List[MomentDTO],
        existing_tag_names: set[str],
    ) -> tuple[Dict[str, Tag], set[str]]:
        """Create/fetch all tags referenced by imported moments in batch."""
        wanted_names = {
            tag.strip().lower()
            for moment in moments
            for tag in (moment.tags or [])
            if tag and tag.strip()
        }
        if not wanted_names:
            return {}, set()

        existing_tags = (
            self.db.execute(
                select(Tag).where(
                    col(Tag.user_id) == user_id,
                    col(Tag.name).in_(list(wanted_names)),
                )
            )
            .scalars()
            .all()
        )
        tag_lookup: Dict[str, Tag] = {tag.name.lower(): tag for tag in existing_tags}
        missing_names = wanted_names - set(tag_lookup.keys())
        created_names: set[str] = set()
        for name in missing_names:
            tag = Tag(user_id=user_id, name=name)
            self.db.add(tag)
            self.db.flush()
            tag_lookup[name] = tag
            existing_tag_names.add(name)
            created_names.add(name)
        return tag_lookup, created_names

    def _prepare_activity_lookup(
        self,
        user_id: UUID,
        moments: List[MomentDTO],
    ) -> Dict[str, UUID]:
        """Create/fetch all activity names used in mood_activity lists in batch."""
        wanted_names = {
            item.activity_name.strip().lower()
            for moment in moments
            for item in (moment.mood_activity or [])
            if item.activity_name and item.activity_name.strip()
        }
        if not wanted_names:
            return {}

        existing = (
            self.db.execute(
                select(Activity).where(
                    col(Activity.user_id) == user_id,
                    func.lower(col(Activity.name)).in_(list(wanted_names)),
                )
            )
            .scalars()
            .all()
        )
        lookup: Dict[str, UUID] = {activity.name.strip().lower(): activity.id for activity in existing}
        for name in wanted_names - set(lookup.keys()):
            activity = Activity(user_id=user_id, name=name)
            self.db.add(activity)
            self.db.flush()
            lookup[name] = activity.id
        return lookup

    def _get_existing_mood_names(self, user_id: UUID) -> set:
        """Get set of existing user mood names (lowercase)."""
        moods = self.db.execute(
            select(Mood.name).where(col(Mood.user_id) == user_id)
        ).all()
        return {m[0].lower() for m in moods}

    def _import_mood_definitions(
        self,
        user_id: UUID,
        mood_definitions: list[MoodDefinitionDTO],
        summary: ImportResultSummary,
        record_mapping: Callable[[str, Optional[str], UUID], None],
    ) -> Dict[str, UUID]:
        """Import mood definitions and return external_id -> mood_id map."""
        existing = (
            self.db.execute(
                select(Mood).where(col(Mood.user_id) == user_id)
            )
            .scalars()
            .all()
        )
        user_by_key: Dict[str, Mood] = {}
        user_by_name: Dict[str, Mood] = {}
        for mood in existing:
            if mood.key:
                user_by_key[mood.key] = mood
            user_by_name[mood.name.lower()] = mood

        mood_id_map: Dict[str, UUID] = {}
        for mood_dto in mood_definitions:
            lookup_key = mood_dto.key or ""
            lookup_name = mood_dto.name.lower()
            existing_mood = None
            if lookup_key and lookup_key in user_by_key:
                existing_mood = user_by_key[lookup_key]
            elif lookup_name in user_by_name:
                existing_mood = user_by_name[lookup_name]

            mood_name_for_insert = mood_dto.name

            if existing_mood:
                existing_mood.icon = mood_dto.icon
                existing_mood.key = mood_dto.key
                existing_mood.color_value = mood_dto.color_value
                if mood_dto.score is not None:
                    existing_mood.score = mood_dto.score
                existing_mood.position = mood_dto.position
                existing_mood.is_active = mood_dto.is_active
                existing_mood.category = mood_dto.category
                if mood_dto.updated_at:
                    existing_mood.updated_at = mood_dto.updated_at
                summary.moods_reused += 1
                mood_id = existing_mood.id
            else:
                mood = Mood(
                    name=mood_name_for_insert,
                    category=mood_dto.category,
                    icon=mood_dto.icon,
                    key=mood_dto.key,
                    color_value=mood_dto.color_value,
                    score=mood_dto.score or 3,
                    position=mood_dto.position,
                    is_active=mood_dto.is_active,
                    user_id=user_id,
                    created_at=mood_dto.created_at or utc_now(),
                    updated_at=mood_dto.updated_at or utc_now(),
                )
                self.db.add(mood)
                self.db.flush()
                summary.moods_created += 1
                mood_id = mood.id
                user_by_name[mood.name.lower()] = mood
                if lookup_key:
                    user_by_key[lookup_key] = mood

            if mood_dto.external_id:
                mood_id_map[mood_dto.external_id] = mood_id
                record_mapping("moods", mood_dto.external_id, mood_id)

        self.db.flush()
        return mood_id_map

    def _import_mood_groups(
        self,
        user_id: UUID,
        mood_groups: list[MoodGroupDTO],
        summary: ImportResultSummary,
        record_mapping: Callable[[str, Optional[str], UUID], None],
    ) -> Dict[str, UUID]:
        """Import mood groups and return external_id -> group_id map."""
        mood_group_id_map: Dict[str, UUID] = {}
        for group_dto in mood_groups:
            query = select(MoodGroup).where(
                func.lower(MoodGroup.name) == group_dto.name.lower(),
                col(MoodGroup.user_id) == user_id,
            )
            existing = self.db.execute(query).scalars().first()

            if existing:
                existing.icon = group_dto.icon
                existing.color_value = group_dto.color_value
                existing.position = group_dto.position
                if group_dto.updated_at:
                    existing.updated_at = group_dto.updated_at
                group_id = existing.id
            else:
                group = MoodGroup(
                    user_id=user_id,
                    name=group_dto.name,
                    icon=group_dto.icon,
                    color_value=group_dto.color_value,
                    position=group_dto.position,
                    created_at=group_dto.created_at or utc_now(),
                    updated_at=group_dto.updated_at or utc_now(),
                )
                self.db.add(group)
                self.db.flush()
                summary.mood_groups_created += 1
                group_id = group.id

            if group_dto.external_id:
                mood_group_id_map[group_dto.external_id] = group_id
                record_mapping("mood_groups", group_dto.external_id, group_id)

        self.db.flush()
        return mood_group_id_map

    def _import_mood_group_links(
        self,
        mood_group_links: list[MoodGroupLinkDTO],
        mood_id_map: Dict[str, UUID],
        mood_group_id_map: Dict[str, UUID],
        summary: ImportResultSummary,
    ) -> None:
        """Import mood group links."""
        for link_dto in mood_group_links:
            group_id = mood_group_id_map.get(link_dto.mood_group_external_id)
            mood_id = mood_id_map.get(link_dto.mood_external_id)
            if not group_id or not mood_id:
                warning_msg = (
                    "Skipping mood group link due to missing group or mood mapping"
                )
                self._add_warning(summary, warning_msg, "Skipped (mood group link)")
                continue

            existing = (
                self.db.execute(
                    select(MoodGroupLink).where(
                        col(MoodGroupLink.mood_group_id) == group_id,
                        col(MoodGroupLink.mood_id) == mood_id,
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                existing.position = link_dto.position
                if link_dto.updated_at:
                    existing.updated_at = link_dto.updated_at
                continue

            link = MoodGroupLink(
                mood_group_id=group_id,
                mood_id=mood_id,
                position=link_dto.position,
                created_at=link_dto.created_at or utc_now(),
                updated_at=link_dto.updated_at or utc_now(),
            )
            self.db.add(link)
            summary.mood_group_links_created += 1

        self.db.flush()

    def _import_mood_preferences(
        self,
        user_id: UUID,
        mood_preferences: list[MoodPreferenceDTO],
        mood_id_map: Dict[str, UUID],
        summary: ImportResultSummary,
    ) -> None:
        """Import user mood preferences."""
        for pref_dto in mood_preferences:
            mood_id = mood_id_map.get(pref_dto.mood_external_id)
            if not mood_id:
                warning_msg = "Skipping mood preference due to missing mood mapping"
                self._add_warning(summary, warning_msg, "Skipped (mood preference)")
                continue

            existing = (
                self.db.execute(
                    select(UserMoodPreference).where(
                        col(UserMoodPreference.user_id) == user_id,
                        col(UserMoodPreference.mood_id) == mood_id,
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                existing.sort_order = pref_dto.sort_order
                existing.is_hidden = pref_dto.is_hidden
                if pref_dto.updated_at:
                    existing.updated_at = pref_dto.updated_at
            else:
                pref = UserMoodPreference(
                    user_id=user_id,
                    mood_id=mood_id,
                    sort_order=pref_dto.sort_order,
                    is_hidden=pref_dto.is_hidden,
                    created_at=pref_dto.created_at or utc_now(),
                    updated_at=pref_dto.updated_at or utc_now(),
                )
                self.db.add(pref)
                summary.mood_preferences_imported += 1

        self.db.flush()

    def _import_mood_group_preferences(
        self,
        user_id: UUID,
        mood_group_preferences: list[MoodGroupPreferenceDTO],
        mood_group_id_map: Dict[str, UUID],
        summary: ImportResultSummary,
    ) -> None:
        """Import user mood group preferences."""
        for pref_dto in mood_group_preferences:
            group_id = mood_group_id_map.get(pref_dto.mood_group_external_id)
            if not group_id:
                warning_msg = "Skipping mood group preference due to missing group mapping"
                self._add_warning(summary, warning_msg, "Skipped (mood group preference)")
                continue

            existing = (
                self.db.execute(
                    select(UserMoodGroupPreference).where(
                        col(UserMoodGroupPreference.user_id) == user_id,
                        col(UserMoodGroupPreference.mood_group_id) == group_id,
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                existing.sort_order = pref_dto.sort_order
                existing.is_hidden = pref_dto.is_hidden
                if pref_dto.updated_at:
                    existing.updated_at = pref_dto.updated_at
            else:
                pref = UserMoodGroupPreference(
                    user_id=user_id,
                    mood_group_id=group_id,
                    sort_order=pref_dto.sort_order,
                    is_hidden=pref_dto.is_hidden,
                    created_at=pref_dto.created_at or utc_now(),
                    updated_at=pref_dto.updated_at or utc_now(),
                )
                self.db.add(pref)
                summary.mood_group_preferences_imported += 1

        self.db.flush()

    def _import_activity_groups(
        self,
        user_id: UUID,
        activity_groups: list[ActivityGroupDTO],
        summary: ImportResultSummary,
        record_mapping: Callable[[str, Optional[str], UUID], None],
    ) -> Dict[str, UUID]:
        """Import activity groups and return external_id -> group_id map."""
        activity_group_id_map: Dict[str, UUID] = {}
        for group_dto in activity_groups:
            existing = (
                self.db.execute(
                    select(ActivityGroup).where(
                        col(ActivityGroup.user_id) == user_id,
                        func.lower(ActivityGroup.name) == group_dto.name.lower(),
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                group_id = existing.id
            else:
                group = ActivityGroup(
                    user_id=user_id,
                    name=group_dto.name,
                    color_value=group_dto.color_value,
                    icon=group_dto.icon,
                    position=group_dto.position,
                    created_at=group_dto.created_at or utc_now(),
                    updated_at=group_dto.updated_at or utc_now(),
                )
                self.db.add(group)
                self.db.flush()
                summary.activity_groups_created += 1
                group_id = group.id

            if group_dto.external_id:
                activity_group_id_map[group_dto.external_id] = group_id
                record_mapping("activity_groups", group_dto.external_id, group_id)

        self.db.flush()
        return activity_group_id_map

    def _import_activities(
        self,
        user_id: UUID,
        activities: list[ActivityDTO],
        activity_group_id_map: Dict[str, UUID],
        summary: ImportResultSummary,
        record_mapping: Callable[[str, Optional[str], UUID], None],
    ) -> Dict[str, UUID]:
        """Import activities and return external_id -> activity_id map."""
        activity_id_map: Dict[str, UUID] = {}
        for activity_dto in activities:
            existing = (
                self.db.execute(
                    select(Activity).where(
                        col(Activity.user_id) == user_id,
                        func.lower(Activity.name) == activity_dto.name.lower(),
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                activity_id = existing.id
            else:
                group_id = None
                if activity_dto.group_external_id:
                    group_id = activity_group_id_map.get(activity_dto.group_external_id)
                activity = Activity(
                    user_id=user_id,
                    name=activity_dto.name,
                    icon=activity_dto.icon,
                    color=activity_dto.color,
                    position=activity_dto.position or 0,
                    group_id=group_id,
                    created_at=activity_dto.created_at or utc_now(),
                    updated_at=activity_dto.updated_at or utc_now(),
                )
                self.db.add(activity)
                self.db.flush()
                summary.activities_created += 1
                activity_id = activity.id

            if activity_dto.external_id:
                activity_id_map[activity_dto.external_id] = activity_id
                record_mapping("activities", activity_dto.external_id, activity_id)

        self.db.flush()
        return activity_id_map

    def _import_goal_categories(
        self,
        user_id: UUID,
        goal_categories: list[GoalCategoryDTO],
        summary: ImportResultSummary,
        record_mapping: Callable[[str, Optional[str], UUID], None],
    ) -> Dict[str, UUID]:
        """Import goal categories and return external_id -> category_id map."""
        category_id_map: Dict[str, UUID] = {}
        for category_dto in goal_categories:
            existing = (
                self.db.execute(
                    select(GoalCategory).where(
                        col(GoalCategory.user_id) == user_id,
                        func.lower(GoalCategory.name) == category_dto.name.lower(),
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                category_id = existing.id
            else:
                category = GoalCategory(
                    user_id=user_id,
                    name=category_dto.name,
                    color_value=category_dto.color_value,
                    icon=category_dto.icon,
                    position=category_dto.position or 0,
                    created_at=category_dto.created_at or utc_now(),
                    updated_at=category_dto.updated_at or utc_now(),
                )
                self.db.add(category)
                self.db.flush()
                summary.goal_categories_created += 1
                category_id = category.id

            if category_dto.external_id:
                category_id_map[category_dto.external_id] = category_id
                record_mapping("goal_categories", category_dto.external_id, category_id)

        self.db.flush()
        return category_id_map

    def _import_goals(
        self,
        user_id: UUID,
        goals: list[GoalDTO],
        activity_id_map: Dict[str, UUID],
        goal_category_id_map: Dict[str, UUID],
        summary: ImportResultSummary,
        record_mapping: Callable[[str, Optional[str], UUID], None],
    ) -> Dict[str, UUID]:
        """Import goals and return external_id -> goal_id map."""
        goal_id_map: Dict[str, UUID] = {}
        for goal_dto in goals:
            existing = (
                self.db.execute(
                    select(Goal).where(
                        col(Goal.user_id) == user_id,
                        func.lower(col(Goal.title)) == goal_dto.title.lower(),
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                if goal_dto.external_id:
                    goal_id_map[goal_dto.external_id] = existing.id
                    record_mapping("goals", goal_dto.external_id, existing.id)
                continue

            activity_id = None
            if goal_dto.activity_external_id:
                activity_id = activity_id_map.get(goal_dto.activity_external_id)
            category_id = None
            if goal_dto.category_external_id:
                category_id = goal_category_id_map.get(goal_dto.category_external_id)

            goal = Goal(
                user_id=user_id,
                activity_id=activity_id,
                category_id=category_id,
                title=goal_dto.title,
                goal_type=goal_dto.goal_type,
                frequency_type=goal_dto.frequency_type,
                target_count=goal_dto.target_count,
                reminder_time=goal_dto.reminder_time,
                is_paused=goal_dto.is_paused,
                icon=goal_dto.icon,
                color_value=goal_dto.color_value,
                position=goal_dto.position,
                archived_at=goal_dto.archived_at,
                created_at=goal_dto.created_at or utc_now(),
                updated_at=goal_dto.updated_at or utc_now(),
            )
            self.db.add(goal)
            self.db.flush()
            summary.goals_created += 1

            if goal_dto.external_id:
                goal_id_map[goal_dto.external_id] = goal.id
                record_mapping("goals", goal_dto.external_id, goal.id)

        self.db.flush()
        return goal_id_map

    def _import_goal_logs(
        self,
        user_id: UUID,
        goal_logs: list[GoalLogDTO],
        goal_id_map: Dict[str, UUID],
        moment_id_map: Dict[str, UUID],
        summary: ImportResultSummary,
        record_mapping: Optional[Callable[[str, Optional[str], UUID], None]] = None,
    ) -> None:
        """Import goal logs."""
        for log_dto in goal_logs:
            goal_id = goal_id_map.get(log_dto.goal_external_id)
            if not goal_id:
                warning_msg = "Skipping goal log due to missing goal mapping"
                self._add_warning(summary, warning_msg, "Skipped (goal log)")
                continue
            moment_id = None
            if log_dto.moment_external_id:
                mapped_moment_id = moment_id_map.get(log_dto.moment_external_id)
                if mapped_moment_id is not None:
                    moment_id = mapped_moment_id

            existing = (
                self.db.execute(
                    select(GoalLog).where(
                        col(GoalLog.goal_id) == goal_id,
                        col(GoalLog.period_start) == log_dto.period_start,
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                existing.logged_date = log_dto.logged_date
                existing.period_end = log_dto.period_end
                existing.status = log_dto.status
                existing.count = log_dto.count
                existing.source = log_dto.source
                existing.last_updated_at = log_dto.last_updated_at or existing.last_updated_at or utc_now()
                if moment_id is not None:
                    existing.moment_id = moment_id
                if log_dto.updated_at:
                    existing.updated_at = log_dto.updated_at
                if record_mapping and log_dto.external_id:
                    record_mapping("goal_logs", log_dto.external_id, existing.id)
                continue

            log = GoalLog(
                goal_id=goal_id,
                user_id=user_id,
                logged_date=log_dto.logged_date,
                period_start=log_dto.period_start,
                period_end=log_dto.period_end,
                status=log_dto.status,
                count=log_dto.count,
                source=log_dto.source,
                last_updated_at=log_dto.last_updated_at or utc_now(),
                moment_id=moment_id,
                created_at=log_dto.created_at or utc_now(),
                updated_at=log_dto.updated_at or utc_now(),
            )
            self.db.add(log)
            self.db.flush()
            summary.goal_logs_created += 1
            if record_mapping and log_dto.external_id:
                record_mapping("goal_logs", log_dto.external_id, log.id)

        self.db.flush()

    def _import_goal_manual_logs(
        self,
        user_id: UUID,
        goal_manual_logs: list[GoalManualLogDTO],
        goal_id_map: Dict[str, UUID],
        summary: ImportResultSummary,
        record_mapping: Optional[Callable[[str, Optional[str], UUID], None]] = None,
    ) -> None:
        """Import manual goal logs."""
        for log_dto in goal_manual_logs:
            goal_id = goal_id_map.get(log_dto.goal_external_id)
            if not goal_id:
                warning_msg = "Skipping manual goal log due to missing goal mapping"
                self._add_warning(summary, warning_msg, "Skipped (manual goal log)")
                continue

            existing = (
                self.db.execute(
                    select(GoalManualLog).where(
                        col(GoalManualLog.goal_id) == goal_id,
                        col(GoalManualLog.logged_date) == log_dto.logged_date,
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                existing.status = log_dto.status
                if log_dto.updated_at:
                    existing.updated_at = log_dto.updated_at
                if record_mapping and log_dto.external_id:
                    record_mapping("goal_manual_logs", log_dto.external_id, existing.id)
                continue

            log = GoalManualLog(
                goal_id=goal_id,
                user_id=user_id,
                logged_date=log_dto.logged_date,
                status=log_dto.status,
                created_at=log_dto.created_at or utc_now(),
                updated_at=log_dto.updated_at or utc_now(),
            )
            self.db.add(log)
            self.db.flush()
            summary.goal_manual_logs_created += 1
            if record_mapping and log_dto.external_id:
                record_mapping("goal_manual_logs", log_dto.external_id, log.id)

        self.db.flush()

    def _is_supported_export_version(self, version: str) -> bool:
        try:
            major_str, minor_str = version.split(".")
            current_major_str, current_minor_str = ExportConfig.EXPORT_VERSION.split(".")
            major = int(major_str)
            minor = int(minor_str)
            current_major = int(current_major_str)
            current_minor = int(current_minor_str)
        except Exception:
            return False

        if major != current_major:
            return False
        return minor <= current_minor

    @staticmethod
    def count_entries_in_data(data: Dict[str, Any]) -> int:
        """Count number of entries present in import data."""
        total = 0
        moments = data.get("moments", [])
        for moment in moments:
            if isinstance(moment, dict) and moment.get("entry"):
                total += 1
        return total

    def cleanup_temp_files(self, file_path: Path):
        """
        Clean up temporary import files.

        This is best-effort cleanup that should not fail the import process.
        Broad exception handling is intentional to ensure cleanup attempts
        don't raise errors even if file system operations fail.

        Args:
            file_path: Path to uploaded file
        """
        try:
            upload_root = (Path(settings.import_temp_dir) / "uploads").resolve()
            temp_root = Path(settings.import_temp_dir).resolve()
            file_path_resolved = file_path.resolve()

            # Only delete files inside the configured upload directory
            if str(file_path_resolved).startswith(str(upload_root)) and file_path_resolved.exists():
                file_path_resolved.unlink()

            # Remove extraction directory (always under import_temp_dir/<stem>)
            extract_dir = (temp_root / file_path.stem).resolve()
            if str(extract_dir).startswith(str(temp_root)) and extract_dir.exists():
                shutil.rmtree(extract_dir)

            log_info(f"Cleaned up temp files for: {file_path}", file_path=str(file_path))
        except Exception as e:  # noqa: BLE001
            # Best-effort cleanup: log but don't raise
            log_error(e, file_path=str(file_path), context="cleanup_temp_files")

    def cleanup_stale_temp_files(self, *, older_than_hours: int = 2) -> int:
        """Best-effort cleanup of stale import temp files/directories."""
        removed = 0
        try:
            temp_root = Path(settings.import_temp_dir).resolve()
            if not temp_root.exists():
                return 0
            cutoff_ts = (utc_now().timestamp() - (older_than_hours * 3600))
            upload_root = (temp_root / "uploads").resolve()

            if upload_root.exists():
                for path in upload_root.iterdir():
                    try:
                        if path.stat().st_mtime >= cutoff_ts:
                            continue
                        if path.is_file():
                            path.unlink(missing_ok=True)
                            removed += 1
                        elif path.is_dir():
                            shutil.rmtree(path, ignore_errors=True)
                            removed += 1
                    except Exception:
                        continue

            for path in temp_root.iterdir():
                if path.name == "uploads":
                    continue
                try:
                    if path.stat().st_mtime >= cutoff_ts:
                        continue
                    if path.is_dir():
                        shutil.rmtree(path, ignore_errors=True)
                        removed += 1
                except Exception:
                    continue
        except Exception as exc:
            log_error(exc, context="cleanup_stale_temp_files")
        return removed
