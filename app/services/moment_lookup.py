"""
Shared moment ownership lookup helpers.
"""
import uuid
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, select

from app.models.entry import Entry
from app.models.moment import Moment
from app.services.journal_access import JournalAccessDeniedError, JournalAccessService


class MomentNotFoundError(Exception):
    """Raised when a moment is not found for the user."""


def draft_author_condition(user_id: uuid.UUID) -> ColumnElement[bool]:
    """Match the draft author, falling back to the entry owner for older rows."""
    return func.coalesce(col(Entry.created_by_user_id), col(Entry.user_id)) == user_id


def is_draft_author(entry: Entry, user_id: uuid.UUID) -> bool:
    """Check draft authorship, including entries without creator attribution."""
    return (entry.created_by_user_id or entry.user_id) == user_id


def get_owned_moment(
    session: Session,
    user_id: uuid.UUID,
    moment_id: uuid.UUID,
    *,
    options: Optional[list[Any]] = None,
) -> Moment:
    """Fetch a user-owned moment with optional ORM loading options."""
    statement = select(Moment).where(Moment.id == moment_id, Moment.user_id == user_id)
    if options:
        statement = statement.options(*options)
    moment = session.exec(statement).first()
    if not moment:
        raise MomentNotFoundError("Moment not found")
    entry = session.exec(select(Entry).where(Entry.moment_id == moment_id)).first()
    if entry and entry.is_draft and not is_draft_author(entry, user_id):
        raise MomentNotFoundError("Moment not found")
    return moment


def get_accessible_moment(
    session: Session,
    user_id: uuid.UUID,
    moment_id: uuid.UUID,
    *,
    edit: bool = False,
    options: Optional[list[Any]] = None,
) -> Moment:
    """Fetch a private Moment or a journal-backed Moment the actor can access."""
    statement = select(Moment).where(Moment.id == moment_id)
    if options:
        statement = statement.options(*options)
    moment = session.exec(statement).first()
    if not moment:
        raise MomentNotFoundError("Moment not found")
    entry = session.exec(select(Entry).where(Entry.moment_id == moment_id)).first()
    if entry is None:
        # Standalone quick logs never become shared just because another journal is shared.
        if moment.user_id != user_id:
            raise MomentNotFoundError("Moment not found")
        return moment
    if entry.is_draft and not is_draft_author(entry, user_id):
        # Drafts remain private to their author until they are finalized.
        raise MomentNotFoundError("Moment not found")
    try:
        JournalAccessService(session).require(entry.journal_id, user_id, edit=edit)
    except JournalAccessDeniedError:
        raise MomentNotFoundError("Moment not found") from None
    return moment
