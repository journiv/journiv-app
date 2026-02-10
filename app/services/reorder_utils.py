"""
Helpers for bulk position updates with consistent error handling.
"""
import uuid
from typing import Any, Protocol, Sequence, Tuple, TypeVar, cast

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, select

from app.core.logging_config import log_error


class _ReorderableModel(Protocol):
    id: uuid.UUID
    position: int


_ModelT = TypeVar("_ModelT", bound=_ReorderableModel)


def apply_position_updates(
    session: Session,
    model: type[_ModelT],
    user_id: uuid.UUID,
    updates: Sequence[Tuple[uuid.UUID, int]],
) -> int:
    """Apply position updates for models that belong to a user.

    Returns the number of updated rows.
    """
    if not updates:
        return 0

    ids = [item_id for item_id, _ in updates]
    model_attrs = cast(Any, model)
    try:
        statement = select(model).where(
            col(model_attrs.user_id) == user_id,
            col(model_attrs.id).in_(ids),
        )
        items = session.exec(statement).all()
        item_map: dict[uuid.UUID, _ModelT] = {item.id: item for item in items}

        for item_id, position in updates:
            item = item_map.get(item_id)
            if item is not None:
                item.position = position

        for item in item_map.values():
            session.add(item)
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        log_error(exc)
        raise

    return len(item_map)
