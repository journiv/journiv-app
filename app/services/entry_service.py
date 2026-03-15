"""
Entry service for managing journal entries.
"""
import re
import secrets
import uuid
from typing import Any, List, Optional, cast

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import QueryableAttribute
from sqlmodel import Session, col, select

from app.core.exceptions import (
    EntryNotFoundError,
    JournalNotFoundError,
    MediaNotFoundError,
    ValidationError,
)
from app.core.logging_config import log_debug, log_error, log_info, log_warning
from app.core.time_utils import utc_now
from app.models.entry import Entry
from app.models.journal import Journal
from app.models.moment import MomentMedia
from app.schemas.entry import (
    EntryCreate,
    EntryDraftCreate,
    EntryUpdate,
)
from app.services.media_service import MediaService
from app.services.moment_lookup import MomentNotFoundError, get_owned_moment
from app.utils.quill_delta import extract_media_sources, extract_plain_text

DEFAULT_ENTRY_PAGE_LIMIT = 50


class EntryService:
    """Service class for entry operations."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _entry_moment_relation() -> QueryableAttribute[Any]:
        return cast(QueryableAttribute[Any], Entry.moment)

    @staticmethod
    def _escape_like_pattern(query: str) -> str:
        """Escape SQL LIKE wildcards (% and _) in user query."""
        if not query:
            return query
        return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def generate_unique_slug(self, title: str) -> str:
        """
        Generate a unique URL slug from an entry title.

        Aggressively cleans the title to only include:
        - lowercase letters (a-z)
        - numbers (0-9)
        - hyphens (-)

        If a collision is detected, appends -1, -2, etc. until unique.

        Args:
            title: Entry title to convert to slug

        Returns:
            Unique URL-safe slug (max 255 chars)

        Raises:
            ValidationError: If title cannot be converted to valid slug
        """
        if not title or not title.strip():
            raise ValidationError("Title is required to generate slug")

        # Convert to lowercase and replace whitespace with hyphens
        slug = title.lower().strip()
        slug = re.sub(r'\s+', '-', slug)

        # Remove all characters except a-z, 0-9, and hyphens
        slug = re.sub(r'[^a-z0-9-]', '', slug)

        # Remove consecutive hyphens
        slug = re.sub(r'-+', '-', slug)

        # Remove leading/trailing hyphens
        slug = slug.strip('-')

        if not slug:
            raise ValidationError("Title must contain at least one alphanumeric character")

        # Truncate to 240 chars to leave room for collision suffix
        base_slug = slug[:240]

        # Check for uniqueness and append suffix if needed
        final_slug = base_slug
        counter = 1

        while True:
            # Check if slug already exists
            existing = self.session.exec(
                select(Entry).where(Entry.slug == final_slug)
            ).first()

            if not existing:
                return final_slug

            # Collision detected, try next suffix
            final_slug = f"{base_slug}-{counter}"
            counter += 1

            # Safety limit to prevent infinite loops
            if counter > 1000:
                raise ValidationError("Unable to generate unique slug after 1000 attempts")

    def generate_unique_public_id(self) -> str:
        """
        Generate a unique public_id for published entries.

        Uses secrets.token_urlsafe(9) to generate a 12-character URL-safe identifier.

        Returns:
            Unique 12-character public ID

        Raises:
            ValidationError: If unable to generate unique ID after many attempts
        """
        max_attempts = 100
        for _ in range(max_attempts):
            # Generate 12-char URL-safe token
            public_id = secrets.token_urlsafe(9)

            # Check for collision
            existing = self.session.exec(
                select(Entry).where(Entry.public_id == public_id)
            ).first()

            if not existing:
                return public_id

        raise ValidationError("Unable to generate unique public_id after multiple attempts")

    def _get_owned_entry(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> Entry:
        statement = select(Entry).where(
            Entry.id == entry_id,
            Entry.user_id == user_id,
        ).options(joinedload(self._entry_moment_relation()))

        entry = self.session.exec(statement).first()
        if not entry:
            log_warning(f"Entry not found for user {user_id}: {entry_id}")
            raise EntryNotFoundError("Entry not found")
        return entry

    def _commit(self) -> None:
        """Commit database changes with proper error handling."""
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    def create_entry(
        self,
        user_id: uuid.UUID,
        entry_data: EntryCreate | EntryDraftCreate,
        *,
        is_draft: bool = False,
        skip_moment_sync: bool = False,
        commit: bool = True,
        run_side_effects: bool = True,
    ) -> Entry:
        """Create a new entry linked to a moment.

        Args:
            user_id: User ID creating the entry
            entry_data: Entry creation data (content + journal_id + moment_id)

        Returns:
            Created entry instance
        """
        # Validate journal exists and belongs to user
        journal_statement = select(Journal).where(
            Journal.id == entry_data.journal_id,
            Journal.user_id == user_id
        )
        journal = self.session.exec(journal_statement).first()
        if not journal:
            log_warning(f"Journal not found for user {user_id}: {entry_data.journal_id}")
            raise JournalNotFoundError("Journal not found")

        try:
            get_owned_moment(self.session, user_id, entry_data.moment_id)
        except MomentNotFoundError:
            log_warning(f"Moment not found for user {user_id}: {entry_data.moment_id}")
            raise ValidationError("Moment not found") from None

        if entry_data.content_delta is not None:
            delta_payload = entry_data.content_delta.model_dump()
            sources = extract_media_sources(delta_payload)
            log_debug(
                "Entry create: incoming delta media sources",
                user_id=user_id,
                journal_id=str(entry_data.journal_id),
                media_source_count=len(sources),
                redacted_media_ids=[f"{s[:8]}..." for s in sources[:5]],
            )

        plain_text = extract_plain_text(
            entry_data.content_delta.model_dump() if entry_data.content_delta else None
        )
        word_count = len(plain_text.split()) if plain_text else 0

        entry = Entry(
            title=entry_data.title,
            content_delta=entry_data.content_delta.model_dump() if entry_data.content_delta else None,
            content_plain_text=plain_text or None,
            journal_id=entry_data.journal_id,
            moment_id=entry_data.moment_id,
            word_count=word_count,
            user_id=user_id,
            is_draft=is_draft,
        )

        try:
            self.session.add(entry)
            self.session.flush()
            if not skip_moment_sync:
                from app.services.moment_service import MomentService
                moment_service = MomentService(self.session)
                moment_service.ensure_moment_for_entry(
                    user_id,
                    entry,
                    primary_mood_id=getattr(entry_data, "primary_mood_id", None),
                    commit=False,
                )
            if commit:
                self._commit()
                self.session.refresh(entry)
        except ValidationError:
            self.session.rollback()
            raise
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(
            f"Entry created for user {user_id} in journal {entry.journal_id}: {entry.id} (draft={is_draft})"
        )

        if run_side_effects:
            self._run_entry_side_effects(
                entry,
                user_id,
                skip_moment_sync=True,
                primary_mood_id=getattr(entry_data, "primary_mood_id", None),
            )

        return entry

    def _run_entry_side_effects(
        self,
        entry: Entry,
        user_id: uuid.UUID,
        *,
        skip_moment_sync: bool = False,
        primary_mood_id: Optional[uuid.UUID] = None,
    ) -> None:
        try:
            from app.services.journal_service import JournalService
            JournalService(self.session).recalculate_journal_entry_count(entry.journal_id, user_id)
        except JournalNotFoundError:
            log_warning(f"Journal missing during entry recount for user {user_id}: {entry.journal_id}")
        except SQLAlchemyError as exc:
            log_error(exc)
        except Exception as exc:
            log_error(exc)

        # Update writing streak analytics (only for published entries)
        if not entry.is_draft and entry.moment_id:
            try:
                from app.models.moment import Moment
                from app.services.analytics_service import AnalyticsService
                moment = self.session.get(Moment, entry.moment_id)
                if moment and moment.logged_date_tz:
                    analytics_service = AnalyticsService(self.session)
                    analytics_service.update_writing_streak(user_id, moment.logged_date_tz)
            except Exception as exc:
                log_error(exc)

        if not skip_moment_sync:
            try:
                from app.services.moment_service import MomentService
                moment_service = MomentService(self.session)
                moment_service.ensure_moment_for_entry(
                    user_id,
                    entry,
                    primary_mood_id=primary_mood_id,
                )
            except Exception as exc:
                log_error(exc)

    def get_entry_by_id(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Entry]:
        """Get an entry by ID, ensuring it belongs to the user."""
        statement = select(Entry).where(
            Entry.id == entry_id,
            Entry.user_id == user_id,
        )
        return self.session.exec(statement).first()

    def get_journal_entries(
        self,
        journal_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = DEFAULT_ENTRY_PAGE_LIMIT,
        offset: int = 0,
        include_drafts: bool = False,
        include_pinned: bool = True,
    ) -> List[Entry]:
        """Get entries for a specific journal."""
        from app.models.moment import Moment
        from app.services.journal_service import JournalService

        JournalService(self.session)._get_owned_journal(journal_id, user_id)

        # Join with Moment to access pinned status; every entry must have a moment.
        statement = select(Entry).join(Moment, col(Entry.moment_id) == col(Moment.id))
        statement = statement.where(Entry.journal_id == journal_id)
        statement = statement.options(
            joinedload(self._entry_moment_relation()).selectinload(Moment.tags),  # type: ignore[arg-type]
            joinedload(self._entry_moment_relation()).selectinload(Moment.mood_activity_links),  # type: ignore[arg-type]
            joinedload(self._entry_moment_relation()).selectinload(Moment.media),  # type: ignore[arg-type]
        )

        if not include_drafts:
            statement = statement.where(col(Entry.is_draft).is_(False))

        if not include_pinned:
            # Filter out pinned moments
            statement = statement.where(col(Moment.is_pinned).is_(False))
            # Standard sort by created_at
            statement = statement.order_by(col(Entry.created_at).desc())
        else:
            # Sort pinned items first, then by date
            statement = statement.order_by(
                col(Moment.is_pinned).desc(),  # True (pinned) comes before False
                col(Entry.created_at).desc(),
            )

        statement = statement.offset(offset).limit(limit)

        return list(self.session.exec(statement))

    def get_user_entries(
        self,
        user_id: uuid.UUID,
        limit: int = DEFAULT_ENTRY_PAGE_LIMIT,
        offset: int = 0,
        include_drafts: bool = False,
    ) -> List[Entry]:
        """Get all entries for a user across all journals."""
        statement = select(Entry).where(
            Entry.user_id == user_id,
        ).options(joinedload(self._entry_moment_relation())).order_by(col(Entry.created_at).desc())

        if not include_drafts:
            statement = statement.where(col(Entry.is_draft).is_(False))

        statement = statement.offset(offset).limit(limit)

        return list(self.session.exec(statement))

    def get_user_drafts(
        self,
        user_id: uuid.UUID,
        limit: int = DEFAULT_ENTRY_PAGE_LIMIT,
        offset: int = 0,
        journal_id: Optional[uuid.UUID] = None,
    ) -> List[Entry]:
        """Get all draft entries for a user, newest updated first."""
        statement = select(Entry).where(
            Entry.user_id == user_id,
            col(Entry.is_draft).is_(True),
        ).options(joinedload(self._entry_moment_relation()))

        if journal_id:
            statement = statement.where(Entry.journal_id == journal_id)

        statement = statement.order_by(
            col(Entry.updated_at).desc(),
        ).offset(offset).limit(limit)

        return list(self.session.exec(statement))

    def update_entry(self, entry_id: uuid.UUID, user_id: uuid.UUID, entry_data: EntryUpdate) -> Entry:
        """Update an entry — content fields only. Metadata lives on Moment."""
        entry = self._get_owned_entry(entry_id, user_id)
        was_draft = entry.is_draft
        media_service = MediaService(self.session)

        # Initialize variables for post-commit cleanup
        orphaned_files = []
        orphaned_immich_assets = []

        # Handle journal change if requested
        old_journal_id = None
        new_journal_id = None
        if entry_data.journal_id is not None and entry_data.journal_id != entry.journal_id:
            new_journal_statement = select(Journal).where(
                Journal.id == entry_data.journal_id,
                Journal.user_id == user_id
            )
            new_journal = self.session.exec(new_journal_statement).first()
            if not new_journal:
                log_warning(f"Target journal not found for user {user_id}: {entry_data.journal_id}")
                raise JournalNotFoundError("Target journal not found")

            if new_journal.is_archived:
                log_warning(f"Cannot move entry {entry_id} to archived journal {new_journal.id}")
                raise ValidationError("Cannot move entry to an archived journal")

            old_journal_id = entry.journal_id
            new_journal_id = entry_data.journal_id
            entry.journal_id = new_journal_id
            log_info(f"Entry {entry_id} journal changed from {old_journal_id} to {new_journal_id}")

        if entry_data.title is not None:
            entry.title = entry_data.title
        if entry_data.is_draft is not None:
            entry.is_draft = entry_data.is_draft
        if entry_data.content_delta is not None:
            from app.core.media_signing import normalize_delta_media_ids

            delta_payload = entry_data.content_delta.model_dump()
            sources = extract_media_sources(delta_payload)
            log_debug(
                "Entry update: incoming delta media sources",
                entry_id=str(entry.id),
                user_id=user_id,
                media_source_count=len(sources),
                redacted_media_ids=[f"{s[:8]}..." for s in sources[:5]],
            )
            # Get media via moment_id
            media_items = []
            if entry.moment_id:
                media_items = self.session.exec(
                    select(MomentMedia).where(MomentMedia.moment_id == entry.moment_id)
                ).all()
            log_debug(
                "Entry update: existing media items",
                entry_id=str(entry.id),
                user_id=user_id,
                media_count=len(media_items),
                media_ids=[str(media.id) for media in media_items[:5]],
                immich_asset_count=len(
                    [
                        media
                        for media in media_items
                        if media.external_provider == "immich"
                        and media.external_asset_id
                    ]
                ),
            )
            for media in media_items:
                self.session.expunge(media)
            normalized_delta = normalize_delta_media_ids(delta_payload, list(media_items)) or {}
            normalized_sources = extract_media_sources(normalized_delta)
            log_debug(
                "Entry update: normalized delta media sources",
                entry_id=str(entry.id),
                user_id=user_id,
                media_source_count=len(normalized_sources),
                redacted_media_ids=[f"{s[:8]}..." for s in normalized_sources[:5]],
            )

            if entry.moment_id:
                # Delete media that was removed from the delta
                orphaned_files, orphaned_immich_assets = media_service.delete_orphaned_media_for_delta(
                    entry.moment_id, user_id, entry.content_delta or {}, normalized_delta
                )

            entry.content_delta = normalized_delta
            plain_text = extract_plain_text(normalized_delta)
            entry.content_plain_text = plain_text or None
            entry.word_count = len(plain_text.split()) if plain_text else 0

        entry.updated_at = utc_now()
        try:
            self.session.add(entry)
            self._commit()
            self.session.refresh(entry)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        # Delete orphaned media files AFTER successful commit
        media_service.delete_media_files_post_commit(
            user_id, orphaned_files, orphaned_immich_assets
        )

        # Recalculate stats for both journals if journal was changed
        if old_journal_id is not None and new_journal_id is not None:
            try:
                from app.services.journal_service import JournalService
                journal_service = JournalService(self.session)
                journal_service.recalculate_journal_entry_count(old_journal_id, user_id)
                journal_service.recalculate_journal_entry_count(new_journal_id, user_id)
            except JournalNotFoundError:
                log_warning(f"Journal missing during entry update recount for user {user_id}")
            except SQLAlchemyError as exc:
                log_error(exc)
            except Exception as exc:
                log_error(exc)

        # Draft -> published transition is treated as finalize.
        if was_draft and not entry.is_draft:
            self._run_entry_side_effects(entry, user_id, skip_moment_sync=True)

        log_info(f"Entry updated for user {user_id}: {entry.id}")
        return entry

    def delete_entry(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """
        Hard delete an entry.

        Note: The associated Moment and its context (media, tags, mood, etc.) are NOT deleted.
        This effectively "reverts" a detailed entry back to a "Quick Log" (Moment without Entry).
        """
        entry = self._get_owned_entry(entry_id, user_id)

        # Store related IDs before deleting the entry
        journal_id = entry.journal_id
        moment_id = entry.moment_id

        # Hard delete the entry only — moment, media, and tags remain on the moment
        self.session.delete(entry)

        try:
            self._commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        try:
            from app.services.journal_service import JournalService
            JournalService(self.session).recalculate_journal_entry_count(journal_id, user_id)
        except JournalNotFoundError:
            log_warning(f"Journal missing during entry delete recount for user {user_id}: {journal_id}")
        except SQLAlchemyError as exc:
            log_error(exc)
        except Exception as exc:
            log_error(exc)

        try:
            from app.services.analytics_service import AnalyticsService
            analytics_service = AnalyticsService(self.session)
            analytics_service.recalculate_writing_streak_stats(user_id)
        except Exception as exc:
            log_warning(f"Failed to update writing streak stats after entry deletion: {exc}")

        # Clean up any orphaned moment that became structurally empty after entry deletion.
        try:
            from app.services.moment_service import MomentService
            deleted_count = MomentService(self.session).prune_empty_moments(
                user_id,
                moment_ids=[moment_id],
            )
            if deleted_count > 0:
                log_info(f"Pruned empty moment after entry deletion for user {user_id}: {moment_id}")
        except Exception as exc:
            # Non-critical cleanup; timeline filtering still prevents empty-card rendering.
            log_warning(f"Failed to prune empty moment after entry deletion: {exc}")

        log_info(f"Entry hard-deleted for user {user_id}: {entry_id}")
        return True

    def delete_entry_media(self, media_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Hard delete an entry media file.

        Args:
            media_id: Media ID to delete
            user_id: User ID for authorization

        Returns:
            True if deleted successfully

        Raises:
            EntryNotFoundError: If media doesn't exist or doesn't belong to user's entry
        """
        try:
            return MediaService(self.session).delete_media_by_id_sync(media_id, user_id)
        except MediaNotFoundError as exc:
            raise EntryNotFoundError("Media not found") from exc

    def finalize_entry(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> Entry:
        """Finalize a draft entry by marking is_draft=False via standard update flow."""
        return self.update_entry(entry_id, user_id, EntryUpdate(is_draft=False))
