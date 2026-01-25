"""
Import service for importing data into Journiv.

Handles the business logic for importing data from various sources.
"""
import re
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.core.logging_config import log_info, log_warning, log_error
from app.models import User, Journal, Entry, EntryMedia, Mood, MoodLog, Tag
from app.models.import_job import ImportJob
from app.models.enums import ImportSourceType, JournalColor, MediaType, UploadStatus
from app.schemas.dto import (
    JournivExportDTO,
    JournalDTO,
    EntryDTO,
    MediaDTO,
    MoodLogDTO,
    ImportResultSummary,
)
from app.utils.import_export import (
    ZipHandler,
    MediaHandler,
    IDMapper,
    normalize_datetime,
)
from app.utils.import_export.constants import ExportConfig
from app.core.time_utils import local_date_for_user, utc_now, normalize_timezone
from app.data_transfer.dayone import DayOneParser, DayOneToJournivMapper
from app.services.media_storage_service import MediaStorageService


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
    def _replace_media_ids_in_content(content: str, id_map: Dict[str, str]) -> str:
        """Replace legacy media IDs in shortcodes and URLs with new IDs."""
        updated = content
        for old_id, new_id in id_map.items():
            # Shortcodes: ![[media:<id>]]
            updated = re.sub(
                rf'(!\[\[media:){re.escape(old_id)}(\]\])',
                lambda match: f"{match.group(1)}{new_id}{match.group(2)}",
                updated,
                flags=re.IGNORECASE,
            )
            # API URLs: /api/v1/media/<id> (with optional /thumbnail)
            updated = re.sub(
                rf'(/api/v1/media/){re.escape(old_id)}(?=/|$)',
                lambda match: f"{match.group(1)}{new_id}",
                updated,
                flags=re.IGNORECASE,
            )
            # Legacy video placeholders with file paths or old URLs.
            updated = re.sub(
                rf':::video\s+\S*{re.escape(old_id)}\S*\s*:::',
                f'![[media:{new_id}]]',
                updated,
                flags=re.IGNORECASE,
            )
            # Legacy markdown images with file paths or old URLs.
            updated = re.sub(
                rf'!\[[^\]]*]\(\S*{re.escape(old_id)}\S*\)',
                f'![[media:{new_id}]]',
                updated,
                flags=re.IGNORECASE,
            )
        return updated

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
        user = self.db.query(User).filter(User.id == user_id).first()
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
            dayone_journals, media_dir = DayOneParser.parse_zip(
                file_path,
                extract_dir,
                is_already_extracted=extraction_dir is not None
            )

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
                        # Find corresponding Day One entry to get media references
                        dayone_entry = dayone_entry_map.get(entry_dto.external_id)

                        if dayone_entry and media_dir:
                            # Map photos
                            for photo in (dayone_entry.photos or []):
                                media_path = DayOneParser.find_media_file(
                                    media_dir,
                                    photo.identifier,
                                    md5_hash=photo.md5,
                                    media_type="photo"
                                )
                                if media_path:
                                    media_dto = DayOneToJournivMapper.map_photo_to_media(
                                        photo,
                                        media_path,
                                        entry_dto.external_id,
                                        media_base_dir=media_dir,
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
                                    media_dir,
                                    video.identifier,
                                    md5_hash=video.md5,
                                    media_type="video"
                                )
                                if media_path:
                                    media_dto = DayOneToJournivMapper.map_video_to_media(
                                        video,
                                        media_path,
                                        entry_dto.external_id,
                                        media_base_dir=media_dir,
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
                    summary.mood_logs_created += result["mood_logs_created"]
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

        if export_dto.export_version != ExportConfig.EXPORT_VERSION:
            raise ValueError(
                f"Incompatible export version {export_dto.export_version}. "
                f"Expected {ExportConfig.EXPORT_VERSION}."
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
                    summary.mood_logs_created += result["mood_logs_created"]
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

            log_info(
                f"Import completed: {summary.journals_created} journals, "
                f"{summary.entries_created} entries, "
                f"{summary.mood_logs_created} mood logs, "
                f"{summary.media_files_imported} media files",
                user_id=str(user_id),
                journals_created=summary.journals_created,
                entries_created=summary.entries_created,
                mood_logs_created=summary.mood_logs_created,
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
            "mood_logs_created": 0,
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
                result["mood_logs_created"] += entry_result["mood_logs_created"]
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
                Entry.journal_id == journal.id
            )
        ).one()

        entry_count = int(stats.count) if stats and stats.count is not None else 0
        total_words = int(stats.total_words) if stats and stats.total_words is not None else 0
        last_created = stats.last_created if stats else None

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
        # Calculate word count from content to ensure accuracy
        # (don't trust the DTO value in case it's outdated or incorrect)
        word_count = len(entry_dto.content.split()) if entry_dto.content else 0

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
            content=entry_dto.content,
            entry_date=recalculated_entry_date,  # Recalculated local date
            entry_datetime_utc=entry_dto.entry_datetime_utc,  # UTC timestamp
            entry_timezone=entry_timezone,  # IANA timezone, default to UTC
            word_count=word_count,  # Recalculate from content
            is_pinned=entry_dto.is_pinned,
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
            "mood_logs_created": 0,
            "media_imported": 0,
            "media_deduplicated": 0,
            "tags_created": 0,
            "tags_reused": 0,
        }

        # Import mood log if present
        if entry_dto.mood_log:
            mood_log_created = self._import_mood_log(
                entry_id=entry.id,
                user_id=user_id,
                mood_log_dto=entry_dto.mood_log,
                existing_mood_names=existing_mood_names,
                summary=summary,
            )
            if mood_log_created:
                result["mood_logs_created"] += 1

        # Import media
        media_map = {}  # Map md5/identifier -> media_id for Day One placeholder replacement
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

            # Build photo map for Day One imports (md5 -> media_id)
            source_key = media_result.get("source_md5") or media_dto.external_id
            if source_key and media_result.get("media_id"):
                media_map[source_key] = media_result["media_id"]
            if legacy_media_id and media_result.get("media_id"):
                legacy_media_id_map[legacy_media_id] = media_result["media_id"]

        # Replace legacy Journiv media IDs in content with newly imported IDs.
        if entry.content and legacy_media_id_map:
            entry.content = self._replace_media_ids_in_content(entry.content, legacy_media_id_map)
            # Recalculate word count after content update
            entry.word_count = len(entry.content.split()) if entry.content else 0

        # Replace Day One photo placeholders with Journiv media shortcode format
        from app.data_transfer.dayone.richtext_parser import DayOneRichTextParser
        if entry.content and DayOneRichTextParser.PLACEHOLDER_PREFIX in entry.content:
            entry.content = DayOneRichTextParser.replace_photo_placeholders(
                entry.content,
                media_map
            )
            # Recalculate word count after content update
            entry.word_count = len(entry.content.split()) if entry.content else 0

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

    def _import_mood_log(
        self,
        entry_id: UUID,
        user_id: UUID,
        mood_log_dto: MoodLogDTO,
        existing_mood_names: set,
        summary: ImportResultSummary,
    ) -> bool:
        """
        Import a mood log entry.

        Returns:
            True if mood log was created, False otherwise
        """
        # Find mood by name (case-insensitive, since existing records might store mixed case)
        mood_name_lower = mood_log_dto.mood_name.lower()
        mood = (
            self.db.query(Mood)
            .filter(func.lower(Mood.name) == mood_name_lower)
            .first()
        )

        if not mood:
            warning_msg = f"Mood not found: '{mood_log_dto.mood_name}', skipping mood log"
            log_warning(warning_msg, user_id=str(user_id), mood_name=mood_log_dto.mood_name, entry_id=str(entry_id))
            summary.warnings.append(warning_msg)
            return False

        # Recalculate logged_date from UTC timestamp and timezone to avoid DST drift
        logged_timezone = normalize_timezone(mood_log_dto.logged_timezone)
        recalculated_logged_date = local_date_for_user(
            mood_log_dto.logged_datetime_utc,
            logged_timezone
        )

        # Create mood log
        mood_log = MoodLog(
            user_id=user_id,
            entry_id=entry_id,
            mood_id=mood.id,
            note=mood_log_dto.note,
            logged_date=recalculated_logged_date,  # Recalculated local date
            logged_datetime_utc=mood_log_dto.logged_datetime_utc,
            logged_timezone=logged_timezone,
            # Preserve original timestamps from export
            created_at=mood_log_dto.created_at,
            updated_at=mood_log_dto.updated_at,
        )
        self.db.add(mood_log)
        return True

    def _handle_entry_media_race_condition(
        self,
        entry_id: UUID,
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
        existing_entry_media = (
            self.db.query(EntryMedia)
            .filter(
                EntryMedia.entry_id == entry_id,
                EntryMedia.checksum == checksum
            )
            .first()
        )

        if existing_entry_media:
            log_info(
                f"Media already associated with entry ({context}), using existing record",
                checksum=checksum,
                user_id=str(user_id),
                entry_id=str(entry_id),
                media_id=str(existing_entry_media.id)
            )
            if record_mapping and media_dto.external_id:
                record_mapping("media", media_dto.external_id, existing_entry_media.id)

            return {
                "imported": False,
                "deduplicated": True,
                "stored_relative_path": existing_entry_media.file_path,
                "stored_filename": Path(existing_entry_media.file_path).name,
                "source_md5": source_md5,
                "media_id": str(existing_entry_media.id),
            }

        return None

    def _import_media(
        self,
        entry_id: UUID,
        user_id: UUID,
        media_dto: MediaDTO,
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
        # Check if media is external-only (no local file expected)
        # We treat None or empty string file_path as "no local file"
        is_external_link_only = media_dto.external_provider is not None and not media_dto.file_path

        # Check if media file exists in media_dir
        # Skip check if this is an external link-only media
        if not media_dir and not is_external_link_only:
            warning_msg = f"No media directory, skipping media: {media_dto.filename}"
            log_warning(warning_msg, user_id=str(user_id), media_filename=media_dto.filename, entry_id=str(entry_id))
            summary.warnings.append(warning_msg)
            summary.media_files_skipped += 1
            return {"imported": False, "deduplicated": False, "stored_relative_path": None, "media_id": None}

        if not media_dto.file_path and not media_dto.external_provider:
            warning_msg = f"Missing file_path for media: {media_dto.filename}"
            log_warning(warning_msg, user_id=str(user_id), media_filename=media_dto.filename, entry_id=str(entry_id))
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
                entry_id=str(entry_id),
            )
            self._add_warning(summary, warning_msg, "Security warning")
            summary.media_files_skipped += 1
            return {"imported": False, "deduplicated": False, "stored_relative_path": None, "media_id": None}

        if not resolved_source.exists():
            warning_msg = f"Media file not found: {resolved_source}"
            log_warning(warning_msg, user_id=str(user_id), media_filename=media_dto.filename, file_path=str(resolved_source), entry_id=str(entry_id))
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
            existing_entry_media = (
                self.db.query(EntryMedia)
                .filter(
                    EntryMedia.entry_id == entry_id,
                    EntryMedia.checksum == media_dto.checksum
                )
                .first()
            )

            if existing_entry_media:
                log_info(
                    "Media already associated with entry (early check), skipping duplicate",
                    checksum=media_dto.checksum,
                    user_id=str(user_id),
                    entry_id=str(entry_id),
                    media_id=str(existing_entry_media.id)
                )
                if record_mapping and media_dto.external_id:
                    record_mapping("media", media_dto.external_id, existing_entry_media.id)

                return {
                    "imported": False,
                    "deduplicated": True,
                    "stored_relative_path": existing_entry_media.file_path,
                    "stored_filename": Path(existing_entry_media.file_path).name,
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
        existing_entry_media = (
            self.db.query(EntryMedia)
            .filter(
                EntryMedia.entry_id == entry_id,
                EntryMedia.checksum == checksum
            )
            .first()
        )

        if existing_entry_media:
            log_info(
                "Media already associated with entry, skipping duplicate",
                checksum=checksum,
                user_id=str(user_id),
                entry_id=str(entry_id),
                media_id=str(existing_entry_media.id)
            )
            if record_mapping and media_dto.external_id:
                record_mapping("media", media_dto.external_id, existing_entry_media.id)

            return {
                "imported": False,
                "deduplicated": True,
                "stored_relative_path": existing_entry_media.file_path,
                "stored_filename": Path(existing_entry_media.file_path).name,
                "source_md5": source_md5,
                "media_id": str(existing_entry_media.id),
            }

        # If deduplicated, find existing media and create reference
        if was_deduplicated:
            existing_media = (
                self.db.query(EntryMedia)
                .join(Entry)
                .join(Journal)
                .filter(
                    Journal.user_id == user_id,
                    EntryMedia.checksum == checksum
                )
                .first()
            )

            if existing_media:
                # Create new EntryMedia record referencing the same file
                media = EntryMedia(
                    entry_id=entry_id,
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
                    if "uq_entry_media_entry_checksum" in str(exc):
                        result = self._handle_entry_media_race_condition(
                            entry_id=entry_id,
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
                    log_error(exc, user_id=str(user_id), entry_id=str(entry_id), checksum=checksum)
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
                    "stored_filename": Path(existing_media.file_path).name,
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
            if "uq_entry_media_entry_checksum" in str(exc):
                result = self._handle_entry_media_race_condition(
                    entry_id=entry_id,
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
                media_service = MediaService(self.db)

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
        entry_id: UUID,
        file_path: str,
        media_dto: MediaDTO,
        checksum: str,
        file_size: Optional[int] = None,
    ) -> EntryMedia:
        """
        Create an EntryMedia record from DTO.

        This is a helper method to reduce code duplication between
        new media imports and deduplicated media records.

        Args:
            entry_id: Entry ID to associate media with
            file_path: Relative path to media file
            media_dto: Media DTO with metadata
            checksum: File checksum
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
                Tag.user_id == user_id,
                Tag.name == tag_name_lower
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
        checksums = (
            self.db.query(EntryMedia.checksum)
            .join(Entry)
            .filter(
                Entry.user_id == user_id,
                EntryMedia.checksum.isnot(None)
            )
            .all()
        )
        return {c[0] for c in checksums if c[0]}

    def _get_existing_tag_names(self, user_id: UUID) -> set:
        """Get set of existing tag names for user (lowercase)."""
        tags = self.db.query(Tag.name).filter(Tag.user_id == user_id).all()
        return {t[0].lower() for t in tags}

    def _get_existing_mood_names(self, user_id: UUID) -> set:
        """
        Get set of existing mood names (system-wide, lowercase).

        Note: Moods are system-wide, so user_id parameter is not used.
        It's kept for API consistency with other _get_existing_* methods.
        """
        moods = self.db.query(Mood.name).all()
        return {m[0].lower() for m in moods}

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
