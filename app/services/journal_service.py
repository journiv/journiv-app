"""
Journal service for handling journal-related operations.
"""
import uuid
from typing import Any, List, Optional, cast

from sqlalchemy import case, update
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, func, select

from app.core.exceptions import JournalNotFoundError
from app.core.logging_config import log_error, log_info, log_warning
from app.core.time_utils import utc_now
from app.models.journal import Journal
from app.schemas.journal import JournalCreate, JournalUpdate


class JournalService:
    """Service class for journal operations."""

    def __init__(self, session: Session):
        self.session = session

    def _get_owned_journal(self, journal_id: uuid.UUID, user_id: uuid.UUID, *, include_deleted: bool = False) -> Journal:
        """Retrieve a journal ensuring ownership, raising when missing."""
        statement = select(Journal).where(
            Journal.id == journal_id,
            Journal.user_id == user_id,
        )

        journal = self.session.exec(statement).first()
        if not journal:
            log_warning(f"Journal not found for user {user_id}: {journal_id}")
            raise JournalNotFoundError("Journal not found")
        return journal

    def create_journal(self, user_id: uuid.UUID, journal_data: JournalCreate) -> Journal:
        """Create a new journal for a user."""
        journal = Journal(
            title=journal_data.title,
            description=journal_data.description,
            color=journal_data.color,
            icon=journal_data.icon,
            user_id=user_id
        )

        self.session.add(journal)
        try:
            self.session.commit()
            self.session.refresh(journal)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Journal created for user {user_id}: {journal.id}")
        return journal

    def get_journal_by_id(self, journal_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Journal]:
        """Get a journal by ID for a specific user."""
        statement = select(Journal).where(
            Journal.id == journal_id,
            Journal.user_id == user_id,
        )
        return self.session.exec(statement).first()

    def get_user_journals(self, user_id: uuid.UUID, include_archived: bool = False) -> List[Journal]:
        """
        Get all journals for a user with custom ordering.

        Ordering logic: favorites first (by position ASC), then regular journals (by position ASC),
        with created_at DESC as fallback for NULL positions.
        """
        statement = select(Journal).where(
            Journal.user_id == user_id,
        )

        if not include_archived:
            statement = statement.where(col(Journal.is_archived).is_(False))

        # Custom ordering: is_favorite DESC (favorites first), position ASC NULLS LAST, created_at DESC
        statement = statement.order_by(
            col(Journal.is_favorite).desc(),
            col(Journal.position).asc().nullslast(),
            col(Journal.created_at).desc()
        )
        return list(self.session.exec(statement))

    def update_journal(self, journal_id: uuid.UUID, user_id: uuid.UUID, journal_data: JournalUpdate) -> Journal:
        """Update a journal."""
        journal = self._get_owned_journal(journal_id, user_id)

        # Update fields
        if journal_data.title is not None:
            journal.title = journal_data.title
        if journal_data.description is not None:
            journal.description = journal_data.description
        if journal_data.color is not None:
            journal.color = journal_data.color
        if journal_data.icon is not None:
            journal.icon = journal_data.icon
        if journal_data.is_favorite is not None:
            journal.is_favorite = journal_data.is_favorite
        if journal_data.is_archived is not None:
            journal.is_archived = journal_data.is_archived

        journal.updated_at = utc_now()
        try:
            self.session.add(journal)
            self.session.commit()
            self.session.refresh(journal)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Journal updated for {user_id}: {journal.id}")
        return journal

    async def delete_journal(self, journal_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Hard delete a journal and all related entries and media."""
        journal = self._get_owned_journal(journal_id, user_id)

        # Get all entries in this journal
        from app.models.entry import Entry
        from app.services.entry_service import EntryService

        entries = self.session.exec(
            select(Entry).where(Entry.journal_id == journal_id)
        ).all()

        # Delete each entry (which handles media deletion, Immich cleanup, etc.)
        entry_service = EntryService(self.session)
        for entry in entries:
            await entry_service.delete_entry(entry.id, user_id)

        # Hard delete the journal itself
        self.session.delete(journal)

        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Journal and related entries/media hard-deleted for {user_id}: {journal_id}")
        return True
    def get_favorite_journals(self, user_id: uuid.UUID) -> List[Journal]:
        """
        Get favorite journals for a user with custom ordering.

        Ordering logic: position ASC NULLS LAST, created_at DESC as fallback.
        """
        statement = select(Journal).where(
            Journal.user_id == user_id,
            col(Journal.is_favorite).is_(True)
        ).order_by(
            col(Journal.position).asc().nullslast(),
            col(Journal.created_at).desc()
        )
        return list(self.session.exec(statement))

    def toggle_favorite(self, journal_id: uuid.UUID, user_id: uuid.UUID) -> Journal:
        """
        Toggle favorite status of a journal and adjust position accordingly.

        When toggling favorite ON: Place at bottom of favorites section (MAX position + 1)
        When toggling favorite OFF: Place at top of regular journals section (position 0, shift others down)
        """
        journal = self._get_owned_journal(journal_id, user_id)

        new_favorite_status = not journal.is_favorite

        try:
            if new_favorite_status:
                # Moving to favorites: place at bottom of favorites
                max_fav_position = self.session.exec(
                    select(func.max(Journal.position))
                    .where(Journal.user_id == user_id)
                    .where(col(Journal.is_favorite).is_(True))
                ).first()
                # Use explicit None check to preserve position 0
                journal.position = (max_fav_position if max_fav_position is not None else -1) + 1
            else:
                # Moving to regular: place at top of regular journals
                # First, shift all existing regular journals down
                journal_attrs = cast(Any, Journal)
                self.session.exec(
                    update(Journal)
                    .where(col(journal_attrs.user_id) == user_id)
                    .where(col(Journal.is_favorite).is_(False))
                    .where(col(journal_attrs.id) != journal_id)
                    .where(col(journal_attrs.position).isnot(None))
                    .values(position=col(journal_attrs.position) + 1)
                )
                journal.position = 0

            journal.is_favorite = new_favorite_status
            journal.updated_at = utc_now()
            self.session.add(journal)
            self.session.commit()
            self.session.refresh(journal)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Journal favorite toggled for {user_id}: {journal.id} -> {journal.is_favorite}, position -> {journal.position}")
        return journal

    def archive_journal(self, journal_id: uuid.UUID, user_id: uuid.UUID) -> Journal:
        """Archive a journal."""
        journal = self._get_owned_journal(journal_id, user_id)

        journal.is_archived = True
        journal.updated_at = utc_now()
        try:
            self.session.add(journal)
            self.session.commit()
            self.session.refresh(journal)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Journal archived for {user_id}: {journal.id}")
        return journal

    def unarchive_journal(self, journal_id: uuid.UUID, user_id: uuid.UUID) -> Journal:
        """Unarchive a journal."""
        journal = self._get_owned_journal(journal_id, user_id)

        journal.is_archived = False
        journal.updated_at = utc_now()
        try:
            self.session.add(journal)
            self.session.commit()
            self.session.refresh(journal)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Journal unarchived for {user_id}: {journal.id}")
        return journal

    def recalculate_journal_entry_count(self, journal_id: uuid.UUID, user_id: uuid.UUID) -> Journal:
        """
        Recalculate the entry count for a specific journal.

        This method counts the actual number of non-deleted entries in the journal
        and updates the journal's entry_count field. Also updates last_entry_at and total_words.
        """
        from app.models.entry import Entry

        journal = self._get_owned_journal(journal_id, user_id, include_deleted=True)

        stats = self.session.exec(
            select(
                func.count(Entry.id).label("count"),
                func.sum(Entry.word_count).label("total_words"),
                func.max(Entry.entry_datetime_utc).label("last_created")
            ).where(
                Entry.journal_id == journal_id,
                col(Entry.is_draft).is_(False)
            )
        ).first()
        entry_count = int(stats.count) if stats and stats.count is not None else 0
        total_words = int(stats.total_words) if stats and stats.total_words is not None else 0
        last_created = stats.last_created if stats else None

        journal.entry_count = entry_count
        journal.total_words = total_words
        journal.last_entry_at = last_created
        journal.updated_at = utc_now()
        try:
            self.session.add(journal)
            self.session.commit()
            self.session.refresh(journal)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Journal entry count recalculated for {user_id}: {journal.id} -> {entry_count} entries, {total_words} words")
        return journal

    def reorder_journals(self, user_id: uuid.UUID, updates: List[tuple[uuid.UUID, int]]) -> None:
        """
        Reorder journals for a user using batch update.

        Args:
            user_id: The user's ID
            updates: List of (journal_id, position) tuples

        Raises:
            JournalNotFoundError: If any journal not found or not owned by user
        """
        if not updates:
            return

        # Extract journal IDs
        journal_ids = [jid for jid, _ in updates]

        # Validate all journals exist and belong to user
        journal_attrs = cast(Any, Journal)
        existing_journals = self.session.exec(
            select(Journal)
            .where(col(journal_attrs.id).in_(journal_ids))
            .where(col(journal_attrs.user_id) == user_id)
        ).all()

        existing_ids = {j.id for j in existing_journals}
        missing_ids = set(journal_ids) - existing_ids

        if missing_ids:
            log_warning(f"Journals not found or not owned by user {user_id}: {missing_ids}")
            raise JournalNotFoundError(f"Journals not found: {missing_ids}")

        try:
            # Build CASE statement for efficient batch update
            # This updates all positions in a single query
            case_stmt = case(
                *[(col(journal_attrs.id) == journal_id, position) for journal_id, position in updates],
                else_=col(journal_attrs.position)
            )

            self.session.exec(
                update(Journal)
                .where(col(journal_attrs.user_id) == user_id)
                .where(col(journal_attrs.id).in_(journal_ids))
                .values(position=case_stmt, updated_at=utc_now())
            )

            self.session.commit()
            log_info(f"Reordered {len(updates)} journals for user {user_id}")
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
