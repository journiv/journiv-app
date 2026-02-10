"""
Import service for importing data into Journiv.

Handles the business logic for importing data from various sources.
"""
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Optional, cast
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlmodel import col, select

from app.core.config import settings
from app.core.logging_config import log_error, log_info, log_warning
from app.core.time_utils import local_date_for_user, normalize_timezone, utc_now
from app.data_transfer.dayone import DayOneParser, DayOneToJournivMapper
from app.models import Activity, Entry, EntryMedia, Journal, Mood, Tag, User
from app.models.enums import ImportSourceType, JournalColor, MediaType, UploadStatus
from app.models.import_job import ImportJob
from app.models.moment import Moment, MomentMoodActivity
from app.schemas.dto import (
    EntryDTO,
    ImportResultSummary,
    JournalDTO,
    JournivExportDTO,
    MediaDTO,
    MomentDTO,
)
from app.services.media_storage_service import MediaStorageService
from app.utils.import_export import (
    IDMapper,
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
    def _extract_legacy_media_id(file_path: Optional[str]) -> Optional[str]:
        """Extract legacy media UUID from exported file paths like entry_id/media_id_filename."""
        if not file_path:
            return None

        name = Path(file_path).name
        if "_" in name:
            candidate = name.split("_", 1)[0]
            try:
                UUID(candidate)
                return candidate
            except ValueError:
                return None

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
        legacy_media_id_map: Dict[str, str],
    ) -> Dict[str, str]:
        """Build Day One md5/identifier -> media_id map for placeholder replacement."""
        import_metadata = entry_dto.import_metadata or {}
        if import_metadata.get("source") != "dayone":
            return {}

        raw_dayone = import_metadata.get("raw_dayone") or {}
        media_items = (raw_dayone.get("photos") or []) + (raw_dayone.get("videos") or [])
        placeholder_map: Dict[str, str] = {}

        for item in media_items:
            if not isinstance(item, dict):
                continue
            identifier = item.get("identifier")
            if not identifier:
                continue
            media_id = legacy_media_id_map.get(identifier)
            if not media_id:
                continue
            placeholder_map[identifier] = media_id
            md5_hash = item.get("md5")
            if md5_hash:
                placeholder_map[md5_hash] = media_id

        for media_dto in entry_dto.media:
            if media_dto.external_asset_id and media_dto.external_asset_id in legacy_media_id_map:
                placeholder_map[media_dto.external_asset_id] = legacy_media_id_map[media_dto.external_asset_id]

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

        # Create temp directory for extraction if not provided
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
            # Parse Day One ZIP
            dayone_journals, parsed_media_dir = DayOneParser.parse_zip(
                file_path,
                extract_dir,
                is_already_extracted=extraction_dir is not None
            )

            # Use provided media_dir (e.g. from zero-copy CLI) or fallback to parsed one
            final_media_dir = media_dir or parsed_media_dir

            if not dayone_journals:
                raise ValueError("No journals found in Day One export")

            # Count total entries for progress tracking
            if not total_entries:
                total_entries = sum(len(j.entries) for j in dayone_journals)

            # Initialize tracking
            summary = ImportResultSummary()
            id_mapper = IDMapper()

            # Track existing items for deduplication
            existing_media_checksums = self._get_existing_media_checksums(user_id)
            existing_tag_names = self._get_existing_tag_names(user_id)
            existing_mood_names = self._get_existing_mood_names(user_id)

            entries_processed = 0

            def handle_entry_progress():
                nonlocal entries_processed
                entries_processed += 1
                if progress_callback:
                    progress_callback(entries_processed, total_entries or 0)

            def record_mapping(entity_type: str, external_id: Optional[str], new_id: UUID):
                if not external_id:
                    return
                id_mapper.record(external_id, new_id)
                summary.id_mappings.setdefault(entity_type, {})[external_id] = str(new_id)

            # Import each Day One journal as a separate Journiv journal
            for dayone_journal in dayone_journals:
                try:
                    # Map entries individually to allow per-entry skips before DTO creation
                    mapped_entries = []
                    for entry in dayone_journal.entries:
                        try:
                            mapped_entries.append(DayOneToJournivMapper.map_entry(entry))
                        except Exception as entry_error:  # noqa: BLE001
                            warning_msg = f"Skipped Day One entry during mapping: {entry_error}"
                            self._add_warning(summary, warning_msg, "Skipped (entry error)")
                            summary.entries_skipped += 1
                            log_warning(warning_msg, user_id=str(user_id), journal_name=dayone_journal.name)
                            handle_entry_progress()

                    # Map Day One journal to Journiv DTO
                    journal_dto = DayOneToJournivMapper.map_journal(dayone_journal, mapped_entries=mapped_entries)
                    source_version = dayone_journal.export_version
                    if not source_version and dayone_journal.export_metadata:
                        source_version = dayone_journal.export_metadata.get("version")
                    journal_dto.import_metadata = {
                        "source": "dayone",
                        "source_version": source_version,
                        "imported_at": import_timestamp.isoformat().replace("+00:00", "Z"),
                        "export_file": dayone_journal.source_file,
                        "raw_export_metadata": dayone_journal.export_metadata,
                    }

                    # Build lookup map for efficient entry matching (O(1) instead of O(n))
                    dayone_entry_map = {e.uuid: e for e in dayone_journal.entries}

                    # Map media for each entry
                    for entry_dto in journal_dto.entries:
                        if not entry_dto.external_id:
                            continue
                        # Find corresponding Day One entry to get media references
                        dayone_entry = dayone_entry_map.get(entry_dto.external_id)

                        if dayone_entry and final_media_dir:
                            # Map photos
                            for photo in (dayone_entry.photos or []):
                                media_path = DayOneParser.find_media_file(
                                    final_media_dir,
                                    photo.identifier,
                                    md5_hash=photo.md5,
                                    media_type="photo"
                                )
                                if media_path:
                                    media_dto = DayOneToJournivMapper.map_photo_to_media(
                                        photo,
                                        media_path,
                                        entry_dto.external_id,
                                        media_base_dir=final_media_dir,
                                    )
                                    if media_dto:
                                        entry_dto.media.append(media_dto)
                                else:
                                    warning_msg = f"Media file not found for photo {photo.identifier}"
                                    self._add_warning(summary, warning_msg, "Skipped (missing media)")
                                    summary.media_files_skipped += 1

                            # Map videos
                            for video in (dayone_entry.videos or []):
                                media_path = DayOneParser.find_media_file(
                                    final_media_dir,
                                    video.identifier,
                                    md5_hash=video.md5,
                                    media_type="video"
                                )
                                if media_path:
                                    media_dto = DayOneToJournivMapper.map_video_to_media(
                                        video,
                                        media_path,
                                        entry_dto.external_id,
                                        media_base_dir=final_media_dir,
                                    )
                                    if media_dto:
                                        entry_dto.media.append(media_dto)
                                else:
                                    warning_msg = f"Media file not found for video {video.identifier}"
                                    self._add_warning(summary, warning_msg, "Skipped (missing media)")
                                    summary.media_files_skipped += 1

                    # Import journal using existing import logic
                    result = self._import_journal(
                        user_id=user_id,
                        journal_dto=journal_dto,
                        media_dir=final_media_dir,
                        id_mapper=id_mapper,
                        existing_media_checksums=existing_media_checksums,
                        existing_tag_names=existing_tag_names,
                        existing_mood_names=existing_mood_names,
                        summary=summary,
                        entry_progress_callback=handle_entry_progress,
                        record_mapping=record_mapping,
                    )
                    self.db.commit()

                    # Update summary
                    summary.journals_created += 1
                    summary.entries_created += result["entries_created"]
                    summary.media_files_imported += result["media_imported"]
                    summary.media_files_deduplicated += result["media_deduplicated"]
                    summary.tags_created += result["tags_created"]
                    summary.tags_reused += result["tags_reused"]

                except (ValueError, SQLAlchemyError) as journal_error:
                    self.db.rollback()
                    warning_msg = (
                        f"Failed to import Day One journal '{dayone_journal.name}': {journal_error}"
                    )
                    log_error(journal_error, user_id=str(user_id), journal_name=dayone_journal.name)
                    self._add_warning(summary, warning_msg, "Skipped (journal error)")
                    summary.entries_skipped += len(dayone_journal.entries)
                except Exception as journal_error:
                    self.db.rollback()
                    warning_msg = (
                        f"Failed to import Day One journal '{dayone_journal.name}': {journal_error}"
                    )
                    log_error(journal_error, user_id=str(user_id), journal_name=dayone_journal.name, context="unexpected_journal_import_error")
                    self._add_warning(summary, warning_msg, "Skipped (journal error)")
                    summary.entries_skipped += len(dayone_journal.entries)

            log_info(
                f"Day One import completed: {summary.journals_created} journals, "
                f"{summary.entries_created} entries, "
                f"{summary.media_files_imported} media files",
                user_id=str(user_id),
                journals_created=summary.journals_created,
                entries_created=summary.entries_created,
                media_files_imported=summary.media_files_imported
            )

            if summary.warnings:
                log_info(f"Day One import completed with {len(summary.warnings)} warnings", user_id=str(user_id), warning_count=len(summary.warnings))

            return summary

        except Exception as e:
            self.db.rollback()
            log_error(e, user_id=str(user_id))
            raise
        finally:
            # Cleanup is handled by caller
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
        id_mapper = IDMapper()

        # Track existing items for deduplication
        existing_media_checksums = self._get_existing_media_checksums(user_id)
        existing_tag_names = self._get_existing_tag_names(user_id)
        existing_mood_names = self._get_existing_mood_names(user_id)

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
            id_mapper.record(external_id, new_id)
            summary.id_mappings.setdefault(entity_type, {})[external_id] = str(new_id)

        try:
            # Import mood definitions first
            if export_dto.mood_definitions:
                for mood_dto in export_dto.mood_definitions:
                    mood_name_lower = mood_dto.name.lower()
                    if mood_name_lower not in existing_mood_names:
                        # Create new mood definition
                        mood = Mood(
                            name=mood_dto.name,  # Will be normalized to lowercase by validator
                            icon=mood_dto.icon,
                            category=mood_dto.category,
                        )
                        self.db.add(mood)
                        summary.moods_created += 1
                        existing_mood_names.add(mood_name_lower)
                    else:
                        summary.moods_reused += 1

            # Flush to get mood IDs
            self.db.flush()

            # Import journals and entries with per-journal commits
            for journal_dto in export_dto.journals:
                try:
                    result = self._import_journal(
                        user_id=user_id,
                        journal_dto=journal_dto,
                        media_dir=media_dir,
                        id_mapper=id_mapper,
                        existing_media_checksums=existing_media_checksums,
                        existing_tag_names=existing_tag_names,
                        existing_mood_names=existing_mood_names,
                        summary=summary,
                        entry_progress_callback=handle_entry_progress,
                        record_mapping=record_mapping,
                    )
                    self.db.commit()

                    # Update summary
                    summary.journals_created += 1
                    summary.entries_created += result["entries_created"]
                    summary.media_files_imported += result["media_imported"]
                    summary.media_files_deduplicated += result["media_deduplicated"]
                    summary.tags_created += result["tags_created"]
                    summary.tags_reused += result["tags_reused"]
                except (ValueError, SQLAlchemyError) as journal_error:
                    # Narrow exception handling: catch expected DB/validation errors
                    # but let unexpected errors propagate to outer handler
                    self.db.rollback()
                    warning_msg = (
                        f"Failed to import journal '{journal_dto.title}': {journal_error}"
                    )
                    log_error(journal_error, user_id=str(user_id), journal_title=journal_dto.title)
                    self._add_warning(summary, warning_msg, "Skipped (journal error)")
                    summary.entries_skipped += len(journal_dto.entries)
                except Exception as journal_error:
                    # Defensive catch-all for truly unexpected errors
                    # This allows continuing with other journals even on programming errors
                    self.db.rollback()
                    warning_msg = (
                        f"Failed to import journal '{journal_dto.title}': {journal_error}"
                    )
                    log_error(journal_error, user_id=str(user_id), journal_title=journal_dto.title, context="unexpected_journal_import_error")
                    self._add_warning(summary, warning_msg, "Skipped (journal error)")
                    summary.entries_skipped += len(journal_dto.entries)

            if export_dto.moments:
                for moment_dto in export_dto.moments:
                    try:
                        created_moment_id = self._import_moment(
                            user_id=user_id,
                            moment_dto=moment_dto,
                            media_dir=media_dir,
                            existing_media_checksums=existing_media_checksums,
                            summary=summary,
                            record_mapping=record_mapping,
                        )
                        self.db.commit()
                        if created_moment_id and hasattr(summary, "moments_created"):
                            summary.moments_created += 1
                    except Exception as moment_error:
                        self.db.rollback()
                        warning_msg = f"Failed to import moment: {moment_error}"
                        log_warning(warning_msg, user_id=str(user_id))
                        self._add_warning(summary, warning_msg, "Skipped (moment error)")

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

    def _import_journal(
        self,
        user_id: UUID,
        journal_dto: JournalDTO,
        media_dir: Optional[Path],
        id_mapper: IDMapper,
        existing_media_checksums: set,
        existing_tag_names: set,
        existing_mood_names: set,
        summary: ImportResultSummary,
        entry_progress_callback: Optional[Callable[[], None]] = None,
        record_mapping: Optional[Callable[[str, Optional[str], UUID], None]] = None,
    ) -> Dict[str, int]:
        """
        Import a single journal with its entries.

        Returns:
            Dictionary with counts of imported items
        """
        # Parse color enum if provided
        color = None
        if journal_dto.color:
            try:
                # Try to parse as JournalColor enum
                color = JournalColor(journal_dto.color.upper())
            except ValueError:
                # If not a valid enum, try to find by hex value
                try:
                    color = next(
                        c for c in JournalColor if c.value == journal_dto.color
                    )
                except StopIteration:
                    warning_msg = f"Invalid journal color '{journal_dto.color}' for journal '{journal_dto.title}', using default"
                    log_warning(warning_msg, user_id=str(user_id), journal_title=journal_dto.title, color=journal_dto.color)
                    self._add_warning(summary, warning_msg, "Format warning")

        # Create journal
        journal = Journal(
            user_id=user_id,
            title=journal_dto.title,
            description=journal_dto.description,
            color=color,
            icon=journal_dto.icon,
            is_favorite=journal_dto.is_favorite,
            is_archived=journal_dto.is_archived,
            import_metadata=journal_dto.import_metadata,
            # Preserve original timestamps from export
            created_at=journal_dto.created_at,
            updated_at=journal_dto.updated_at,
            # Note: entry_count and last_entry_at are denormalized fields
            # They will be updated by the service layer after entries are imported
        )
        self.db.add(journal)
        self.db.flush()  # Get journal ID
        if record_mapping and journal_dto.external_id:
            record_mapping("journals", journal_dto.external_id, journal.id)

        result = {
            "entries_created": 0,
            "media_imported": 0,
            "media_deduplicated": 0,
            "tags_created": 0,
            "tags_reused": 0,
        }

        # Import entries
        for entry_dto in journal_dto.entries:
            try:
                entry_result = self._import_entry(
                    journal_id=journal.id,
                    user_id=user_id,
                    entry_dto=entry_dto,
                    media_dir=media_dir,
                    existing_media_checksums=existing_media_checksums,
                    existing_tag_names=existing_tag_names,
                    existing_mood_names=existing_mood_names,
                    summary=summary,
                    record_mapping=record_mapping,
                )

                result["entries_created"] += 1
                result["media_imported"] += entry_result["media_imported"]
                result["media_deduplicated"] += entry_result["media_deduplicated"]
                result["tags_created"] += entry_result["tags_created"]
                result["tags_reused"] += entry_result["tags_reused"]
            except Exception as entry_error:  # noqa: BLE001 - continue on bad entry
                warning_msg = f"Skipped entry due to error: {entry_error}"
                self._add_warning(summary, warning_msg, "Skipped (entry error)")
                summary.entries_skipped += 1
                log_warning(warning_msg, user_id=str(user_id), journal_id=str(journal.id))

            if entry_progress_callback:
                entry_progress_callback()

        # Update journal denormalized fields (entry_count, total_words, last_entry_at)
        # This ensures the journal card statistics are accurate after import
        self.db.flush()  # Ensure all entries are committed
        stats = self.db.execute(
            select(
                func.count(Entry.id).label("count"),
                func.sum(Entry.word_count).label("total_words"),
                func.max(Entry.created_at).label("last_created")
            ).where(
                col(Entry.journal_id) == journal.id,
                col(Entry.is_draft).is_(False),
            )
        ).one()

        stats_mapping = stats._mapping
        entry_count = int(stats_mapping["count"] or 0)
        total_words = int(stats_mapping["total_words"] or 0)
        last_created = stats_mapping["last_created"]

        journal.entry_count = entry_count
        journal.total_words = total_words
        journal.last_entry_at = last_created

        log_info(
            f"Updated journal {journal.id} denormalized stats: "
            f"{entry_count} entries, {total_words} words, last entry at {last_created}",
            user_id=str(user_id),
            journal_id=str(journal.id),
            entry_count=entry_count,
            total_words=total_words
        )

        return result

    def _import_entry(
        self,
        journal_id: UUID,
        user_id: UUID,
        entry_dto: EntryDTO,
        media_dir: Optional[Path],
        existing_media_checksums: set,
        existing_tag_names: set,
        existing_mood_names: set,
        summary: ImportResultSummary,
        record_mapping: Optional[Callable[[str, Optional[str], UUID], None]] = None,
    ) -> Dict[str, int]:
        """Import a single entry with media and tags."""
        content_delta = entry_dto.content_delta or wrap_plain_text(entry_dto.content_plain_text)
        plain_text = entry_dto.content_plain_text or extract_plain_text(content_delta)
        word_count = len(plain_text.split()) if plain_text else 0

        # Recalculate entry_date from UTC timestamp and timezone to avoid DST drift
        # This ensures consistency even if the exported entry_date was calculated
        # under different DST rules
        entry_timezone = normalize_timezone(entry_dto.entry_timezone)
        recalculated_entry_date = local_date_for_user(
            entry_dto.entry_datetime_utc,
            entry_timezone
        )

        # Create entry with proper datetime fields
        entry = Entry(
            journal_id=journal_id,
            user_id=user_id,
            title=entry_dto.title,
            content_delta=content_delta,
            content_plain_text=plain_text or None,
            entry_date=recalculated_entry_date,  # Recalculated local date
            entry_datetime_utc=entry_dto.entry_datetime_utc,  # UTC timestamp
            entry_timezone=entry_timezone,  # IANA timezone, default to UTC
            word_count=word_count,  # Recalculate from content
            is_pinned=entry_dto.is_pinned,
            is_draft=entry_dto.is_draft or False,
            # Structured location/weather fields
            location_json=entry_dto.location_json,
            latitude=entry_dto.latitude,
            longitude=entry_dto.longitude,
            weather_json=entry_dto.weather_json,
            weather_summary=entry_dto.weather_summary,
            import_metadata=entry_dto.import_metadata,
            # Preserve original timestamps from export
            created_at=entry_dto.created_at,
            updated_at=entry_dto.updated_at,
        )
        self.db.add(entry)
        self.db.flush()  # Get entry ID
        if record_mapping and entry_dto.external_id:
            record_mapping("entries", entry_dto.external_id, entry.id)

        result = {
            "media_imported": 0,
            "media_deduplicated": 0,
            "tags_created": 0,
            "tags_reused": 0,
        }

        moment = self._import_moment_for_entry(
            entry=entry,
            entry_dto=entry_dto,
            user_id=user_id,
            existing_mood_names=existing_mood_names,
            summary=summary,
        )

        # Import media
        legacy_media_id_map: Dict[str, str] = {}
        for media_dto in entry_dto.media:
            legacy_media_id = self._extract_legacy_media_id(media_dto.file_path)
            # Fallback for link-only media where ID is not in file_path
            if not legacy_media_id and media_dto.external_id:
                try:
                    UUID(media_dto.external_id)
                    legacy_media_id = media_dto.external_id
                except (ValueError, TypeError):
                    pass
            media_result = self._import_media(
                entry_id=entry.id,
                moment_id=moment.id if moment else None,
                user_id=user_id,
                media_dto=media_dto,
                media_dir=media_dir,
                existing_checksums=existing_media_checksums,
                summary=summary,
                record_mapping=record_mapping,
            )
            if media_result["imported"]:
                result["media_imported"] += 1
            elif media_result.get("deduplicated"):
                result["media_deduplicated"] += 1

            if media_result.get("media_id"):
                if legacy_media_id:
                    legacy_media_id_map[legacy_media_id] = media_result["media_id"]
                if media_dto.external_asset_id:
                    legacy_media_id_map[media_dto.external_asset_id] = media_result["media_id"]

        # Replace legacy Journiv media IDs (and Day One placeholders) in content with newly imported IDs.
        dayone_placeholder_map = self._build_dayone_placeholder_map(entry_dto, legacy_media_id_map)
        replacement_map = dict(legacy_media_id_map)
        if dayone_placeholder_map:
            replacement_map.update(dayone_placeholder_map)
        if entry.content_delta and replacement_map:
            entry.content_delta = self._replace_media_ids_in_delta(entry.content_delta, replacement_map)
            plain_text = extract_plain_text(entry.content_delta)
            entry.content_plain_text = plain_text or None
            entry.word_count = len(plain_text.split()) if plain_text else 0

        # Import tags
        for tag_name in entry_dto.tags:
            tag_result = self._import_tag(
                entry_id=entry.id,
                user_id=user_id,
                tag_name=tag_name,
                existing_tag_names=existing_tag_names,
            )
            if tag_result["created"]:
                result["tags_created"] += 1
            else:
                result["tags_reused"] += 1

        return result

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

    def _import_moment_for_entry(
        self,
        entry: Entry,
        entry_dto: EntryDTO,
        user_id: UUID,
        existing_mood_names: set,
        summary: ImportResultSummary,
    ) -> Optional[Moment]:
        moment_dto = entry_dto.moment

        logged_at = entry.entry_datetime_utc
        logged_timezone = normalize_timezone(entry.entry_timezone)
        logged_date = local_date_for_user(logged_at, logged_timezone)
        note = None
        location_data = entry.location_json
        weather_data = entry.weather_json
        primary_mood_name = None
        mood_activity_items = []

        if moment_dto:
            logged_at = moment_dto.logged_at or logged_at
            logged_timezone = normalize_timezone(moment_dto.logged_timezone or logged_timezone)
            logged_date = local_date_for_user(logged_at, logged_timezone)
            note = moment_dto.note
            location_data = moment_dto.location_data
            weather_data = moment_dto.weather_data
            primary_mood_name = moment_dto.primary_mood_name
            mood_activity_items = moment_dto.mood_activity
        moment = Moment(
            user_id=user_id,
            entry_id=entry.id,
            primary_mood_id=None,
            logged_at=logged_at,
            logged_date=logged_date,
            logged_timezone=logged_timezone,
            note=note,
            location_data=location_data,
            weather_data=weather_data,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )
        self.db.add(moment)
        self.db.flush()

        if primary_mood_name:
            mood = (
                self.db.query(Mood)
                .filter(func.lower(Mood.name) == primary_mood_name.lower())
                .first()
            )
            if mood:
                moment.primary_mood_id = mood.id
            else:
                warning_msg = f"Mood not found: '{primary_mood_name}', skipping moment primary mood"
                log_warning(warning_msg, user_id=str(user_id), mood_name=primary_mood_name, entry_id=str(entry.id))
                summary.warnings.append(warning_msg)

        if mood_activity_items:
            for item in mood_activity_items:
                mood_id = None
                activity_id = None
                if item.mood_name:
                    mood = (
                        self.db.query(Mood)
                        .filter(func.lower(Mood.name) == item.mood_name.lower())
                        .first()
                    )
                    if mood:
                        mood_id = mood.id
                    else:
                        warning_msg = f"Mood not found: '{item.mood_name}', skipping moment mood link"
                        log_warning(warning_msg, user_id=str(user_id), mood_name=item.mood_name, entry_id=str(entry.id))
                        summary.warnings.append(warning_msg)
                if item.activity_name:
                    activity = self._get_or_create_activity(user_id, item.activity_name)
                    activity_id = activity.id if activity else None
                if mood_id is None and activity_id is None:
                    continue
                self.db.add(
                    MomentMoodActivity(
                        moment_id=moment.id,
                        mood_id=mood_id,
                        activity_id=activity_id,
                    )
                )
        elif primary_mood_name:
            mood = (
                self.db.query(Mood)
                .filter(func.lower(Mood.name) == primary_mood_name.lower())
                .first()
            )
            if mood:
                self.db.add(
                    MomentMoodActivity(
                        moment_id=moment.id,
                        mood_id=mood.id,
                        activity_id=None,
                    )
                )
        self.db.flush()
        return moment

    def _import_moment(
        self,
        user_id: UUID,
        moment_dto: MomentDTO,
        media_dir: Optional[Path],
        existing_media_checksums: set,
        summary: ImportResultSummary,
        record_mapping: Optional[Callable[[str, Optional[str], UUID], None]] = None,
    ) -> Optional[Moment]:
        logged_at = moment_dto.logged_at or utc_now()
        logged_timezone = normalize_timezone(moment_dto.logged_timezone)
        logged_date = local_date_for_user(logged_at, logged_timezone)

        moment = Moment(
            user_id=user_id,
            entry_id=None,
            primary_mood_id=None,
            logged_at=logged_at,
            logged_date=logged_date,
            logged_timezone=logged_timezone,
            note=moment_dto.note,
            location_data=moment_dto.location_data,
            weather_data=moment_dto.weather_data,
            created_at=moment_dto.created_at,
            updated_at=moment_dto.updated_at,
        )
        self.db.add(moment)
        self.db.flush()

        if moment_dto.primary_mood_name:
            mood = (
                self.db.query(Mood)
                .filter(func.lower(Mood.name) == moment_dto.primary_mood_name.lower())
                .first()
            )
            if mood:
                moment.primary_mood_id = mood.id
            else:
                warning_msg = f"Mood not found: '{moment_dto.primary_mood_name}', skipping moment primary mood"
                log_warning(warning_msg, user_id=str(user_id), mood_name=moment_dto.primary_mood_name)
                summary.warnings.append(warning_msg)

        links_created = 0
        for item in moment_dto.mood_activity:
            mood_id = None
            activity_id = None
            if item.mood_name:
                mood = (
                    self.db.query(Mood)
                    .filter(func.lower(Mood.name) == item.mood_name.lower())
                    .first()
                )
                if mood:
                    mood_id = mood.id
                else:
                    warning_msg = f"Mood not found: '{item.mood_name}', skipping moment mood link"
                    log_warning(warning_msg, user_id=str(user_id), mood_name=item.mood_name)
                    summary.warnings.append(warning_msg)
            if item.activity_name:
                activity = self._get_or_create_activity(user_id, item.activity_name)
                activity_id = activity.id if activity else None
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
            media_result = self._import_media(
                entry_id=None,
                moment_id=moment.id,
                user_id=user_id,
                media_dto=media_dto,
                media_dir=media_dir,
                existing_checksums=existing_media_checksums,
                summary=summary,
                record_mapping=None,
            )
            if media_result["imported"]:
                summary.media_files_imported += 1
            elif media_result.get("deduplicated"):
                summary.media_files_deduplicated += 1

        if record_mapping:
            external_id = getattr(moment_dto, "external_id", None)
            if external_id:
                record_mapping("moments", external_id, moment.id)

        self.db.flush()
        return moment

    def _handle_entry_media_race_condition(
        self,
        entry_id: Optional[UUID],
        moment_id: Optional[UUID],
        checksum: str,
        user_id: UUID,
        media_dto: MediaDTO,
        source_md5: Optional[str],
        record_mapping: Optional[Callable[[str, Optional[str], UUID], None]] = None,
        context: str = "race condition",
    ) -> Optional[Dict[str, Any]]:
        """
        Handle race condition where EntryMedia was created by concurrent import.

        Args:
            entry_id: Entry ID
            checksum: Media checksum
            user_id: User ID
            media_dto: Media DTO
            source_md5: Source MD5 (for Day One imports)
            record_mapping: Optional mapping function for external IDs
            context: Context string for logging (e.g., "race condition", "race condition during deduplication")

        Returns:
            Result dict if existing EntryMedia found, None otherwise
        """
        filters = [col(EntryMedia.checksum) == checksum]
        if entry_id:
            filters.append(col(EntryMedia.entry_id) == entry_id)
        else:
            filters.append(col(EntryMedia.entry_id).is_(None))
        if moment_id:
            filters.append(col(EntryMedia.moment_id) == moment_id)
        else:
            filters.append(col(EntryMedia.moment_id).is_(None))

        existing_entry_media = self.db.query(EntryMedia).filter(*filters).first()

        if existing_entry_media:
            log_info(
                f"Media already associated with entry ({context}), using existing record",
                checksum=checksum,
                user_id=str(user_id),
                entry_id=str(entry_id) if entry_id else None,
                moment_id=str(moment_id) if moment_id else None,
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
        entry_id: Optional[UUID],
        user_id: UUID,
        media_dto: MediaDTO,
        media_dir: Optional[Path],
        existing_checksums: set,
        summary: ImportResultSummary,
        moment_id: Optional[UUID] = None,
        record_mapping: Optional[Callable[[str, Optional[str], UUID], None]] = None,
    ) -> Dict[str, Any]:
        """
        Import a media file with deduplication.

        Returns:
            {"imported": True/False, "deduplicated": True/False, "stored_relative_path": str | None, "media_id": str | None}
        """
        # Check if media is external-only (no local file expected)
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
                entry_id=str(entry_id) if entry_id else None,
                moment_id=str(moment_id) if moment_id else None,
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
                entry_id=str(entry_id) if entry_id else None,
                moment_id=str(moment_id) if moment_id else None,
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
                entry_id=entry_id,
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
            log_warning(warning_msg, user_id=str(user_id), media_filename=media_dto.filename, entry_id=str(entry_id))
            summary.warnings.append(warning_msg)
            summary.media_files_skipped += 1
            return {"imported": False, "deduplicated": False, "stored_relative_path": None, "media_id": None}

        if media_dto.file_path is None:
            warning_msg = f"Missing file_path for media: {media_dto.filename}"
            log_warning(warning_msg, user_id=str(user_id), media_filename=media_dto.filename, entry_id=str(entry_id))
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
                entry_id=str(entry_id) if entry_id else None,
                moment_id=str(moment_id) if moment_id else None,
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
                entry_id=str(entry_id) if entry_id else None,
                moment_id=str(moment_id) if moment_id else None,
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
        # check for existing EntryMedia before storing the file to avoid unnecessary I/O
        # For external media, checksum might be None, so we skip this check if media is strictly external and has no checksum
        if media_dto.checksum:
            early_filters = [col(EntryMedia.checksum) == media_dto.checksum]
            if entry_id:
                early_filters.append(col(EntryMedia.entry_id) == entry_id)
            else:
                early_filters.append(col(EntryMedia.entry_id).is_(None))
            if moment_id:
                early_filters.append(col(EntryMedia.moment_id) == moment_id)
            else:
                early_filters.append(col(EntryMedia.moment_id).is_(None))

            existing_entry_media = self.db.query(EntryMedia).filter(*early_filters).first()

            if existing_entry_media:
                log_info(
                    "Media already associated with entry (early check), skipping duplicate",
                    checksum=media_dto.checksum,
                    user_id=str(user_id),
                    entry_id=str(entry_id) if entry_id else None,
                    moment_id=str(moment_id) if moment_id else None,
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

        # Check if EntryMedia record already exists for this entry and checksum
        # This prevents duplicate media within the same entry (handles cases where checksum wasn't in DTO)
        dedupe_filters = [col(EntryMedia.checksum) == checksum]
        if entry_id:
            dedupe_filters.append(col(EntryMedia.entry_id) == entry_id)
        else:
            dedupe_filters.append(col(EntryMedia.entry_id).is_(None))
        if moment_id:
            dedupe_filters.append(col(EntryMedia.moment_id) == moment_id)
        else:
            dedupe_filters.append(col(EntryMedia.moment_id).is_(None))

        existing_entry_media = self.db.query(EntryMedia).filter(*dedupe_filters).first()

        if existing_entry_media:
            log_info(
                "Media already associated with entry, skipping duplicate",
                checksum=checksum,
                user_id=str(user_id),
                entry_id=str(entry_id) if entry_id else None,
                moment_id=str(moment_id) if moment_id else None,
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
                self.db.query(EntryMedia)
                .outerjoin(Entry)
                .outerjoin(Journal)
                .outerjoin(Moment, col(EntryMedia.moment_id) == col(Moment.id))
                .filter(
                    col(EntryMedia.checksum) == checksum,
                    or_(col(Journal.user_id) == user_id, col(Moment.user_id) == user_id),
                )
                .first()
            )

            if existing_media:
                # Create new EntryMedia record referencing the same file
                media = EntryMedia(
                    entry_id=entry_id,
                    moment_id=moment_id,
                    file_path=existing_media.file_path,
                    original_filename=media_dto.filename,
                    media_type=existing_media.media_type,
                    file_size=existing_media.file_size,
                    mime_type=existing_media.mime_type,
                    checksum=checksum,
                    thumbnail_path=existing_media.thumbnail_path,
                    width=existing_media.width,
                    height=existing_media.height,
                    duration=existing_media.duration,
                    alt_text=media_dto.alt_text or media_dto.caption,
                    upload_status=existing_media.upload_status,
                    file_metadata=existing_media.file_metadata,
                    created_at=media_dto.created_at,
                    updated_at=media_dto.updated_at,
                )
                try:
                    self.db.add(media)
                    self.db.commit()
                    self.db.refresh(media)
                except IntegrityError as exc:
                    self.db.rollback()
                    # Race condition: EntryMedia was created by concurrent import
                    if "uq_entry_media_entry_checksum" in str(exc) or "uq_entry_media_moment_checksum" in str(exc):
                        result = self._handle_entry_media_race_condition(
                            entry_id=entry_id,
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
                    self.db.rollback()
                    log_error(
                        exc,
                        user_id=str(user_id),
                        entry_id=str(entry_id) if entry_id else None,
                        moment_id=str(moment_id) if moment_id else None,
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
            entry_id=entry_id,
            moment_id=moment_id,
            file_path=relative_path, # This might be None for pure external links if logic allowed it, but here relative_path is derived from storage service
            media_dto=media_dto,
            checksum=checksum,
            file_size=file_size,
        )

        try:
            self.db.add(media)
            self.db.commit()
            self.db.refresh(media)
        except IntegrityError as exc:
            self.db.rollback()
            # Race condition: EntryMedia was created by concurrent import
            if "uq_entry_media_entry_checksum" in str(exc) or "uq_entry_media_moment_checksum" in str(exc):
                result = self._handle_entry_media_race_condition(
                    entry_id=entry_id,
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
            self.db.rollback()
            log_error(exc, user_id=str(user_id), entry_id=str(entry_id), checksum=checksum)
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
        entry_id: Optional[UUID],
        file_path: Optional[str],
        media_dto: MediaDTO,
        checksum: Optional[str],
        file_size: Optional[int] = None,
        moment_id: Optional[UUID] = None,
    ) -> EntryMedia:
        """
        Create an EntryMedia record from DTO.

        This is a helper method to reduce code duplication between
        new media imports and deduplicated media records.

        Args:
            entry_id: Entry ID to associate media with
            moment_id: Moment ID to associate media with (for standalone moments)
            file_path: Relative path to media file (optional for external media)
            media_dto: Media DTO with metadata
            checksum: File checksum (optional for external media)
            file_size: Optional file size override (uses DTO value if not provided)

        Returns:
            Created EntryMedia instance (not yet added to session)
        """
        media_type = self._parse_media_type(media_dto.media_type)
        upload_status = self._parse_upload_status(media_dto.upload_status)

        # Sanitization: Reset 0 dimensions to None to satisfy DB constraints
        width = media_dto.width if media_dto.width and media_dto.width > 0 else None
        height = media_dto.height if media_dto.height and media_dto.height > 0 else None

        return EntryMedia(
            entry_id=entry_id,
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
        entry_id: UUID,
        user_id: UUID,
        tag_name: str,
        existing_tag_names: set,
    ) -> Dict[str, bool]:
        """
        Import a tag with deduplication.

        Uses existing_tag_names for fast-path check before querying DB.

        Returns:
            {"created": True/False}
        """
        tag_name_lower = tag_name.strip().lower()

        # Single query regardless of whether tag is in cache
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
        elif tag_name_lower not in existing_tag_names:
            # Tag exists in DB but not in cache, update cache
            existing_tag_names.add(tag_name_lower)

        # Link tag to entry
        from app.models.entry_tag_link import EntryTagLink
        link = EntryTagLink(entry_id=entry_id, tag_id=tag.id)
        self.db.add(link)

        return {"created": created}

    def _get_existing_media_checksums(self, user_id: UUID) -> set:
        """Get set of existing media checksums for user."""
        checksums = self.db.execute(
            select(EntryMedia.checksum)
            .join(Entry)
            .where(
                Entry.user_id == user_id,
                col(EntryMedia.checksum).is_not(None)
            )
        ).all()
        return {c[0] for c in checksums if c[0]}

    def _get_existing_tag_names(self, user_id: UUID) -> set:
        """Get set of existing tag names for user (lowercase)."""
        tags = self.db.execute(
            select(Tag.name).where(Tag.user_id == user_id)
        ).all()
        return {t[0].lower() for t in tags}

    def _get_existing_mood_names(self, user_id: UUID) -> set:
        """
        Get set of existing mood names (system-wide, lowercase).

        Note: Moods are system-wide, so user_id parameter is not used.
        It's kept for API consistency with other _get_existing_* methods.
        """
        moods = self.db.execute(select(Mood.name)).all()
        return {m[0].lower() for m in moods}

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
        journals = data.get("journals", [])
        total = 0
        for journal in journals:
            entries = journal.get("entries", [])
            total += len(entries)
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
