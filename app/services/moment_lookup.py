"""
Shared moment ownership lookup helpers.
"""
import uuid
from typing import Any, Optional

from sqlmodel import Session, select

from app.models.moment import Moment


class MomentNotFoundError(Exception):
    """Raised when a moment is not found for the user."""


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
    return moment
