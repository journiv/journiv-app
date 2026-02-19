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

    def _get_owned_journal(self, journal_id: uuid.UUID, user_id: uuid.UUID) -> Journal:
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
        """
        Create a new journal for a user.

        New journals are placed at position 0 in the regular (non-favorite) section,
        and existing regular journals are shifted down by 1.
        """
        try:
            # Shift all existing regular journals down to make room at position 0
            journal_attrs = cast(Any, Journal)
            self.session.exec(
                update(Journal)
                .where(col(journal_attrs.user_id) == user_id)
                .where(col(Journal.is_favorite).is_(False))
                .where(col(journal_attrs.position).isnot(None))
                .values(position=col(journal_attrs.position) + 1)
            )

            # Create new journal with position 0
            journal = Journal(
                title=journal_data.title,
                description=journal_data.description,
                color=journal_data.color,
                icon=journal_data.icon,
                user_id=user_id,
                position=0,  # New journals appear at the top of regular section
            )

            self.session.add(journal)
            self.session.commit()
            self.session.refresh(journal)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Journal created for user {user_id}: {journal.id} at position 0")
        return journal

    def get_journal_by_id(self, journal_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Journal]:
        """Get a journal by ID for a specific user."""
        statement = select(Journal).where(
            Journal.id == journal_id,
            Journal.user_id == user_id,
        )
        return self.session.exec(statement).first()

    def get_user_journals(
        self,
        user_id: uuid.UUID,
        include_archived: bool = False,
    ) -> List[Journal]:
        """Get all journals for a user."""
        statement = select(Journal).where(Journal.user_id == user_id)

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

    def delete_journal(self, journal_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """
        Hard delete a journal and its entries while preserving moments as quick logs.

        In moment-first architecture, deleting entries must not delete their moments.
        """
        journal = self._get_owned_journal(journal_id, user_id)

        # Hard delete the journal itself
        self.session.delete(journal)

        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        # Recalculate user-level streak once after successful deletion.
        try:
            from app.services.analytics_service import AnalyticsService

            AnalyticsService(self.session).recalculate_writing_streak_stats(user_id)
        except Exception as exc:
            log_warning(f"Failed to update writing streak stats after journal deletion: {exc}")
            try:
                self.session.rollback()
            except Exception:
                # Session cleanup is best-effort only.
                pass

        log_info(
            f"Journal deleted and entries removed; moments preserved as quick logs for {user_id}: {journal_id}"
        )
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

        journal = self._get_owned_journal(journal_id, user_id)

        from app.models.moment import Moment

        stats = self.session.exec(
            select(
                func.count(Entry.id).label("count"),
                func.sum(Entry.word_count).label("total_words"),
                func.max(Moment.logged_at_utc).label("last_created")
            )
            .join(Moment, Entry.moment_id == Moment.id)
            .where(
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
