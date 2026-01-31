"""
Day One to Journiv mappers.

Converts Day One data structures to Journiv DTOs.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from app.core.logging_config import log_warning
from app.core.time_utils import local_date_for_user, ensure_utc, normalize_timezone
from app.schemas.dto import JournalDTO, EntryDTO, MediaDTO
from app.utils.import_export.media_handler import MediaHandler
from app.utils.quill_delta import wrap_plain_text
from .models import DayOneEntry, DayOneJournal, DayOneLocation, DayOneWeather, DayOnePhoto, DayOneVideo
from .richtext_parser import DayOneRichTextParser


class DayOneToJournivMapper:
    """
    Maps Day One data to Journiv DTOs.

    Handles:
    - Journal metadata
    - Entry content and metadata
    - Location data (structured JSON)
    - Weather data (structured JSON)
    - Media files (photos and videos)
    - Tags
    - Timestamps with timezone conversion
    """

    @staticmethod
    def map_journal(dayone_journal: DayOneJournal, mapped_entries: Optional[List[EntryDTO]] = None) -> JournalDTO:
        """
        Map Day One journal to Journiv JournalDTO.

        Args:
            dayone_journal: Day One journal object
            mapped_entries: Pre-mapped entries (optional)

        Returns:
            JournalDTO for Journiv
        """
        # Use journal name as title
        title = dayone_journal.name or "Imported from Day One"

        # Calculate journal metadata from entries
        entry_count = len(dayone_journal.entries)
        last_entry_at = None
        first_entry_at = None
        if dayone_journal.entries:
            # Find most recent entry
            sorted_entries = sorted(
                dayone_journal.entries,
                key=lambda e: e.creation_date,
                reverse=True
            )
            last_entry_at = sorted_entries[0].creation_date
            # Find earliest entry
            first_entry_at = sorted_entries[-1].creation_date

        # Map entries
        entries = mapped_entries or [
            DayOneToJournivMapper.map_entry(entry)
            for entry in dayone_journal.entries
        ]

        return JournalDTO(
            title=title,
            description=f"Imported from Day One journal '{dayone_journal.name}'",
            color=None,  # Day One doesn't have journal colors
            icon=None,   # Day One doesn't have journal icons
            is_favorite=False,
            is_archived=False,
            entry_count=entry_count,
            last_entry_at=last_entry_at,
            entries=entries,
            created_at=first_entry_at or datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            external_id=None,  # Day One journals don't have UUIDs in exports
            import_metadata=None,
        )

    @staticmethod
    def map_entry(dayone_entry: DayOneEntry) -> EntryDTO:
        """
        Map Day One entry to Journiv EntryDTO.

        Extracts title from richText and converts richText to clean Markdown.

        Args:
            dayone_entry: Day One entry object

        Returns:
            EntryDTO for Journiv
        """
        title = None
        content: Optional[str] = None

        # Try to parse richText first
        if dayone_entry.rich_text:
            richtext = DayOneRichTextParser.parse_richtext(dayone_entry.rich_text)
            if richtext:
                # Extract title from richText when a header block exists
                title = DayOneRichTextParser.extract_title(richtext)

                has_body_text = False
                has_embedded_objects = False
                for block in richtext.get("contents", []):
                    embedded = block.get("embeddedObjects")
                    if embedded:
                        has_embedded_objects = True
                    text = block.get("text")
                    if text and text.strip():
                        attrs = block.get("attributes", {}) if isinstance(block.get("attributes"), dict) else {}
                        line_attrs = attrs.get("line", {}) if isinstance(attrs.get("line"), dict) else {}
                        if line_attrs.get("header") != 1:
                            has_body_text = True

                # Convert richText to Markdown (with photo placeholders)
                # We'll replace placeholders with actual paths after entry creation
                markdown = DayOneRichTextParser.convert_to_markdown(
                    richtext,
                    photos=dayone_entry.photos,
                    videos=dayone_entry.videos,
                    entry_id=None  # Will be updated after entry creation
                )
                if markdown and markdown.strip():
                    content = markdown
                    if title and not has_body_text:
                        if has_embedded_objects:
                            lines = content.splitlines()
                            if lines and lines[0].lstrip().startswith("# "):
                                content = "\n".join(lines[1:]).strip() or None
                        else:
                            content = None
                    elif title:
                        lines = content.splitlines()
                        if lines:
                            first_line = lines[0].lstrip()
                            if first_line.startswith("#"):
                                header_text = first_line.lstrip("#").strip()
                                if header_text == title:
                                    content = "\n".join(lines[1:]).strip() or None

        # Fallback to plain text if richText not available
        if content is None and dayone_entry.text:
            text = dayone_entry.text.strip()
            if text:
                if title and text == title:
                    content = None
                else:
                    content = text

        content_delta = wrap_plain_text(content)
        plain_text = content or ""
        word_count = len(plain_text.split()) if plain_text else 0

        # Parse timestamps
        creation_date_utc = ensure_utc(dayone_entry.creation_date)
        modified_date_utc = ensure_utc(
            dayone_entry.modified_date or dayone_entry.creation_date
        )

        # Get timezone (default to UTC if not specified)
        entry_timezone = normalize_timezone(dayone_entry.time_zone)

        # Recalculate entry_date from UTC timestamp and timezone
        entry_date = local_date_for_user(creation_date_utc, entry_timezone)

        # Map location data
        location_json = None
        latitude = None
        longitude = None

        if dayone_entry.location:
            location_json, latitude, longitude = (
                DayOneToJournivMapper._map_location(dayone_entry.location)
            )

        # Map weather data
        weather_json = None
        weather_summary = None

        if dayone_entry.weather:
            weather_json, weather_summary = (
                DayOneToJournivMapper._map_weather(dayone_entry.weather)
            )

        # Map tags (normalize to lowercase)
        tags = []
        for tag in (dayone_entry.tags or []):
            cleaned = tag.strip().lower()
            if cleaned and cleaned not in tags:
                tags.append(cleaned)

        # Map starred/pinned status
        is_pinned = (
            dayone_entry.starred
            or dayone_entry.pinned
            or dayone_entry.is_pinned
            or False
        )

        # Map media (photos and videos)
        media: List[MediaDTO] = []
        # Note: Media will be populated by the import service
        # We just track the external IDs here

        import_metadata = DayOneToJournivMapper._build_entry_import_metadata(
            dayone_entry,
            entry_timezone
        )

        return EntryDTO(
            title=title,  # Extracted from richText or first line
            content_delta=content_delta,
            content_plain_text=plain_text or None,
            entry_date=entry_date,
            entry_datetime_utc=creation_date_utc,
            entry_timezone=entry_timezone,
            word_count=word_count,
            is_pinned=is_pinned,
            # Structured location/weather fields
            location_json=location_json,
            latitude=latitude,
            longitude=longitude,
            weather_json=weather_json,
            weather_summary=weather_summary,
            import_metadata=import_metadata,
            # Related data
            tags=tags,
            mood_log=None,  # Day One doesn't have mood logs
            media=media,    # Will be populated during import
            prompt_text=None,
            created_at=creation_date_utc,
            updated_at=modified_date_utc,
            external_id=dayone_entry.uuid,
        )

    @staticmethod
    def _map_location(
        location: DayOneLocation
    ) -> Tuple[Optional[Dict[str, Any]], Optional[float], Optional[float]]:
        """
        Map Day One location to Journiv location format.

        Returns:
            Tuple of (location_json, latitude, longitude)
        """
        # Extract street address if present in extra fields
        # Day One location model has extra="allow" so street may be in __pydantic_extra__
        street = getattr(location, "street", None) or getattr(location, "__pydantic_extra__", {}).get("street")

        # Build structured location JSON
        location_json = {
            "name": location.place_name or location.locality_name or location.administrative_area or location.country,
            "street": street,
            "locality": location.locality_name,
            "admin_area": location.administrative_area,
            "country": location.country,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "timezone": location.time_zone_name,
        }

        # Remove None values for cleaner JSON
        location_json = {k: v for k, v in location_json.items() if v is not None}

        return location_json, location.latitude, location.longitude

    @staticmethod
    def _map_weather(
        weather: DayOneWeather
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Map Day One weather to Journiv weather format.

        Returns:
            Tuple of (weather_json, weather_summary)
        """
        # Build structured weather JSON with all available fields
        weather_json = {
            "temp_c": weather.temperature_celsius,
            "condition": weather.conditions_description,
            "code": weather.weather_code,
            "service": weather.weather_service_name,
            "humidity": weather.relative_humidity,
            "visibility_km": weather.visibility_km,
            "pressure_mb": weather.pressure_mb,
            "wind_speed_kph": weather.wind_speed_kph,
            "wind_bearing": weather.wind_bearing,
        }

        # Remove None values for cleaner JSON
        weather_json = {k: v for k, v in weather_json.items() if v is not None}

        # Build weather summary (simple temp + condition format)
        summary_parts = []
        if weather.temperature_celsius is not None:
            summary_parts.append(f"{weather.temperature_celsius:.1f}°C")
        if weather.conditions_description:
            summary_parts.append(weather.conditions_description)

        weather_summary = ", ".join(summary_parts) if summary_parts else None

        return weather_json, weather_summary

    @staticmethod
    def _prune_media_list(media_list: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
        pruned = []
        for item in media_list or []:
            if not isinstance(item, dict):
                continue
            entry = {
                "identifier": item.get("identifier"),
                "md5": item.get("md5"),
            }
            entry = {k: v for k, v in entry.items() if v is not None}
            if entry:
                pruned.append(entry)
        return pruned

    @staticmethod
    def _build_entry_import_metadata(
        dayone_entry: DayOneEntry,
        normalized_timezone: str,
    ) -> Dict[str, Any]:
        raw_dayone = dayone_entry.model_dump(by_alias=True, mode="json", exclude_none=True)
        raw_dayone.pop("text", None)

        photos = DayOneToJournivMapper._prune_media_list(raw_dayone.get("photos"))
        videos = DayOneToJournivMapper._prune_media_list(raw_dayone.get("videos"))
        if photos:
            raw_dayone["photos"] = photos
        else:
            raw_dayone.pop("photos", None)
        if videos:
            raw_dayone["videos"] = videos
        else:
            raw_dayone.pop("videos", None)

        return {
            "source": "dayone",
            "raw_dayone": raw_dayone,
            "normalized_timezone": normalized_timezone,
        }

    @staticmethod
    def _map_media_common(
        media_path: Path,
        identifier: str,
        entry_external_id: str,
        media_base_dir: Optional[Path],
        media_type: str,
        mime_type: str,
        width: Optional[int],
        height: Optional[int],
        duration: Optional[float],
        date: Optional[datetime],
        file_metadata: Dict[str, Any],
    ) -> MediaDTO:
        """
        Common media mapping logic for photos and videos.

        Args:
            media_path: Path to actual media file
            identifier: Day One media identifier
            entry_external_id: External ID of parent entry (currently unused, kept for future debugging/features)
            media_base_dir: Base directory for media
            media_type: Media type string (image/video)
            mime_type: MIME type
            width: Media width
            height: Media height
            duration: Media duration
            date: Media creation date
            file_metadata: Additional metadata dict

        Returns:
            MediaDTO
        """
        # entry_external_id is currently unused but kept for future debugging/features
        # (e.g., could be added to file_metadata or used for logging)
        file_size = media_path.stat().st_size

        # Remove None values from metadata
        file_metadata = {k: v for k, v in file_metadata.items() if v is not None}
        file_metadata_str = json.dumps(file_metadata) if file_metadata else None

        try:
            relative_path = media_path.relative_to(media_base_dir) if media_base_dir else media_path
        except ValueError:
            relative_path = media_path

        # Sanitization: Day One metadata can sometimes contain 0 for dimensions,
        # which violates Journiv's POSITIVE check constraints.
        width = width if width and width > 0 else None
        height = height if height and height > 0 else None

        return MediaDTO(
            filename=media_path.name,
            file_path=str(relative_path),
            media_type=media_type,
            file_size=file_size,
            mime_type=mime_type,
            checksum=None,  # Will be calculated during import
            width=width,
            height=height,
            duration=duration,
            alt_text=None,
            file_metadata=file_metadata_str,
            thumbnail_path=None,
            upload_status="completed",
            created_at=date or datetime.now(timezone.utc),
            updated_at=date or datetime.now(timezone.utc),
            external_id=identifier,
        )

    @staticmethod
    def map_photo_to_media(
        photo: DayOnePhoto,
        media_path: Optional[Path],
        entry_external_id: str,
        media_base_dir: Optional[Path] = None,
    ) -> Optional[MediaDTO]:
        """
        Map Day One photo to Journiv MediaDTO.

        Args:
            photo: Day One photo object
            media_path: Path to actual media file
            entry_external_id: External ID of parent entry
            media_base_dir: Base directory for media (used to store relative file_path)

        Returns:
            MediaDTO if media file exists, None otherwise
        """
        if not media_path or not media_path.exists():
            log_warning(
                f"Media file not found for photo {photo.identifier}",
                photo_id=photo.identifier,
                entry_id=entry_external_id
            )
            return None

        # Determine media type and MIME type from file extension
        ext = media_path.suffix.lower()

        if ext in MediaHandler.IMAGE_EXTENSIONS:
            media_type = "image"
        else:
            media_type = "unknown"

        # Use centralized MIME type mapping
        mime_type = MediaHandler.MIME_TYPE_MAP.get(ext, 'application/octet-stream')

        # Build file metadata JSON
        file_metadata = {
            "camera_make": photo.camera_make,
            "camera_model": photo.camera_model,
            "focal_length": photo.focal_length,
            "lens_model": photo.lens_model,
            "exposure_time": photo.exposure_time,
            "fnumber": photo.fnumber,
            "iso": photo.iso,
            "order_in_entry": photo.order_in_entry,
        }

        return DayOneToJournivMapper._map_media_common(
            media_path=media_path,
            identifier=photo.identifier,
            entry_external_id=entry_external_id,
            media_base_dir=media_base_dir,
            media_type=media_type,
            mime_type=mime_type,
            width=photo.width,
            height=photo.height,
            duration=photo.duration,
            date=photo.date,
            file_metadata=file_metadata,
        )

    @staticmethod
    def map_video_to_media(
        video: DayOneVideo,
        media_path: Optional[Path],
        entry_external_id: str,
        media_base_dir: Optional[Path] = None,
    ) -> Optional[MediaDTO]:
        """
        Map Day One video to Journiv MediaDTO.

        Args:
            video: Day One video object
            media_path: Path to actual media file
            entry_external_id: External ID of parent entry
            media_base_dir: Base directory for media (used to store relative file_path)

        Returns:
            MediaDTO if media file exists, None otherwise
        """
        if not media_path or not media_path.exists():
            log_warning(
                f"Media file not found for video {video.identifier}",
                video_id=video.identifier,
                entry_id=entry_external_id
            )
            return None

        # Determine MIME type from file extension using centralized mapping
        ext = media_path.suffix.lower()
        mime_type = MediaHandler.MIME_TYPE_MAP.get(ext, 'video/mp4')

        # Build file metadata JSON
        file_metadata = {
            "order_in_entry": video.order_in_entry,
        }

        return DayOneToJournivMapper._map_media_common(
            media_path=media_path,
            identifier=video.identifier,
            entry_external_id=entry_external_id,
            media_base_dir=media_base_dir,
            media_type="video",
            mime_type=mime_type,
            width=video.width,
            height=video.height,
            duration=video.duration,
            date=video.date,
            file_metadata=file_metadata,
        )
