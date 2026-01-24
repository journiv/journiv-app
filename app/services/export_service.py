"""
Export service for creating Journiv data exports.

Handles the business logic for exporting user data to ZIP archives.
"""
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import log_info, log_warning
from app.core.time_utils import utc_now
from app.models import User, Journal, Entry, EntryMedia, Mood, Tag
from app.models.export_job import ExportJob
from app.models.enums import ExportType
from app.schemas.dto import (
    JournivExportDTO,
    JournalDTO,
    EntryDTO,
    MediaDTO,
    MoodDefinitionDTO,
    UserSettingsDTO,
    MoodLogDTO,
)
from app.utils.import_export import ZipHandler, MediaHandler, validate_export_data
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
        user = self.db.query(User).filter(User.id == user_id).first()
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
        return export_job

    def build_export_data(
        self,
        user_id: UUID,
        export_type: ExportType,
        journal_ids: Optional[List[str]] = None,
        total_entries: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> JournivExportDTO:
        """
        Build export data structure.

        Args:
            user_id: User ID to export
            export_type: Type of export
            journal_ids: Optional list of journal IDs to export

        Returns:
            JournivExportDTO with all user data

        Raises:
            ValueError: If user not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User not found: {user_id}")

        journals_query = self.db.query(Journal).filter(Journal.user_id == user_id)

        if export_type == ExportType.JOURNAL and journal_ids:
            # Selective journal export
            journal_uuids = [UUID(jid) for jid in journal_ids]
            journals_query = journals_query.filter(Journal.id.in_(journal_uuids))

        journals = journals_query.all()
        if total_entries is None:
            total_entries = self.count_entries(user_id, export_type, journal_ids)

        entries_processed = 0

        def handle_entry_progress():
            nonlocal entries_processed
            entries_processed += 1
            if progress_callback and total_entries:
                progress_callback(entries_processed, total_entries)

        # Convert journals to DTOs
        journal_dtos = []
        for journal in journals:
            journal_dto = self._convert_journal_to_dto(
                journal,
                entry_progress_callback=handle_entry_progress,
            )
            journal_dtos.append(journal_dto)

        # Get custom mood definitions
        mood_dtos = self._get_mood_definitions()

        # Get user settings
        user_settings = self._get_user_settings(user)

        # Calculate statistics
        total_entries = sum(len(j.entries) for j in journal_dtos)
        total_media = sum(
            len(e.media) for j in journal_dtos for e in j.entries
        )

        stats = {
            "journal_count": len(journal_dtos),
            "entry_count": total_entries,
            "media_count": total_media,
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
                json.dump(export_dict, tmp_file, ensure_ascii=False)
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
            "entry_count": sum(len(j.entries) for j in export_data.journals),
            "media_count": len(media_files),
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
        query = self.db.query(func.count(Entry.id)).join(Journal, Entry.journal_id == Journal.id)
        query = query.filter(Journal.user_id == user_id)

        if export_type == ExportType.JOURNAL and journal_ids:
            journal_uuids = [UUID(jid) for jid in journal_ids]
            query = query.filter(Entry.journal_id.in_(journal_uuids))

        return int(query.scalar() or 0)

    def _convert_journal_to_dto(
        self,
        journal: Journal,
        entry_progress_callback: Optional[Callable[[], None]] = None,
    ) -> JournalDTO:
        """
        Convert Journal model to JournalDTO.

        Maps database fields to DTO structure:
        - journal.title -> title
        - journal.color -> color (enum to string)
        - journal.is_archived, entry_count, last_entry_at included
        """
        from sqlalchemy.orm import joinedload
        from app.models.mood import MoodLog

        # Get all entries for this journal with eager loading
        entries = (
            self.db.query(Entry)
            .filter(Entry.journal_id == journal.id)
            .options(
                joinedload(Entry.tags),
                joinedload(Entry.mood_log).joinedload(MoodLog.mood),
                joinedload(Entry.media),
            )
            .order_by(Entry.entry_datetime_utc)
            .all()
        )

        entry_dtos = []
        for entry in entries:
            entry_dtos.append(self._convert_entry_to_dto(entry))
            if entry_progress_callback:
                entry_progress_callback()

        return JournalDTO(
            title=journal.title,  # Journal has 'title' not 'name'
            description=journal.description,
            color=journal.color.value if journal.color else None,  # Convert enum to string
            icon=journal.icon,
            is_favorite=journal.is_favorite,
            is_archived=journal.is_archived,  # Include archived status
            entry_count=journal.entry_count,  # Denormalized count
            last_entry_at=journal.last_entry_at,  # Last entry timestamp
            entries=entry_dtos,
            import_metadata=journal.import_metadata,
            created_at=journal.created_at,
            updated_at=journal.updated_at,
        )

    def _convert_entry_to_dto(self, entry: Entry) -> EntryDTO:
        """
        Convert Entry model to EntryDTO.

        Maps database fields to DTO structure:
        - All three datetime fields: entry_date, entry_datetime_utc, entry_timezone
        - Structured fields: location_json, latitude, longitude, weather_json, weather_summary
        - entry.word_count, entry.is_pinned included
        - Creates MoodLogDTO from entry.mood_log if exists
        """
        tags = [tag.name for tag in entry.tags] if entry.tags else []

        # Get mood log as MoodLogDTO
        mood_log_dto = None
        if entry.mood_log and entry.mood_log.mood:
            mood_log_dto = MoodLogDTO(
                mood_name=entry.mood_log.mood.name,
                note=entry.mood_log.note,
                logged_date=entry.mood_log.logged_date,
                logged_datetime_utc=entry.mood_log.logged_datetime_utc,
                logged_timezone=entry.mood_log.logged_timezone,
                # Preserve original timestamps from database
                created_at=entry.mood_log.created_at,
                updated_at=entry.mood_log.updated_at,
                mood_score=None,  # PLACEHOLDER: Not in database
            )

        # Get media
        media_dtos = []
        if entry.media:
            for media in entry.media:
                media_dto = self._convert_media_to_dto(media)
                media_dtos.append(media_dto)

        # Get prompt text if entry was created from a prompt
        prompt_text = None
        if entry.prompt:
            prompt_text = entry.prompt.text

        return EntryDTO(
            title=entry.title,
            content=entry.content or "",
            entry_date=entry.entry_date,  # All three datetime fields required
            entry_datetime_utc=entry.entry_datetime_utc,
            entry_timezone=entry.entry_timezone,
            word_count=entry.word_count,  # Include word count
            is_pinned=entry.is_pinned,  # Include pinned status
            tags=tags,
            mood_log=mood_log_dto,  # Use MoodLogDTO instead of separate fields
            # Structured location/weather fields
            location_json=entry.location_json,
            latitude=entry.latitude,
            longitude=entry.longitude,
            weather_json=entry.weather_json,
            weather_summary=entry.weather_summary,
            import_metadata=entry.import_metadata,
            # PLACEHOLDER: For backward compatibility with other apps
            temperature=None,  # Use weather_json.temp_c instead
            media=media_dtos,
            prompt_text=prompt_text,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    def _convert_media_to_dto(self, media: EntryMedia) -> MediaDTO:
        """
        Convert EntryMedia model to MediaDTO.

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

        return MediaDTO(
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

    def _get_mood_definitions(self) -> List[MoodDefinitionDTO]:
        """
        Get mood definitions (system-wide, not user-specific as of now).

        Maps database fields to DTO structure:
        - mood.name -> name
        - mood.icon -> icon (also mapped to emoji for compatibility)
        - mood.category -> category
        - Placeholders: score, color set to None
        """
        moods = self.db.query(Mood).all()

        mood_dtos = []
        for mood in moods:
            mood_dto = MoodDefinitionDTO(
                name=mood.name,
                category=mood.category,
                icon=mood.icon,  # Use icon field
                emoji=mood.icon or "",  # PLACEHOLDER: Map icon to emoji for compatibility
                score=None,  # PLACEHOLDER: Mood model doesn't have score
                color=None,  # PLACEHOLDER: Mood model doesn't have color
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
            date_format="YYYY-MM-DD",  # PLACEHOLDER: UserSettings doesn't have this field
            time_format="24h",  # PLACEHOLDER: UserSettings doesn't have this field
            first_day_of_week=0,  # PLACEHOLDER: UserSettings doesn't have this field
        )

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
        for journal in export_data.journals:
            for entry in journal.entries:
                for media in entry.media:
                    # Skip media without file_path
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
                        log_warning(
                            f"Media file not found: {source_path} (file_path: {media.file_path})",
                            user_id=str(user_id),
                            file_path=media.file_path,
                            source_path=str(source_path)
                        )

        return media_files

    def _build_media_export_path(self, media: EntryMedia) -> str:
        """Build a sanitized relative path for media inside the export ZIP."""
        original_name = media.original_filename or Path(media.file_path).name
        safe_name = self.media_handler.sanitize_filename(original_name)
        return f"{media.entry_id}/{media.id}_{safe_name}"
