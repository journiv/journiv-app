"""
Person Group service for managing person groups.
"""
import uuid
from typing import List, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, func, select

from app.core.logging_config import log_error, log_info
from app.models.person_group import PersonGroup
from app.schemas.person import PersonGroupCreate, PersonGroupUpdate
from app.services.reorder_utils import apply_position_updates


class PersonGroupNotFoundError(Exception):
    """Raised when a person group is not found."""


class PersonGroupService:
    """Service class for person group operations."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _is_duplicate_group_name_error(exc: IntegrityError) -> bool:
        raw_message = str(getattr(exc, "orig", exc)).lower()
        return (
            "idx_person_group_user_name" in raw_message
            or "unique constraint failed: person_group.user_id, person_group.name" in raw_message
            or "person_group_user_id_name_key" in raw_message
        )

    def create_group(self, user_id: uuid.UUID, group_data: PersonGroupCreate) -> PersonGroup:
        """Create a new person group."""
        position = group_data.position
        if position is None:
            max_position = self.session.exec(
                select(func.coalesce(func.max(PersonGroup.position), 0)).where(
                    PersonGroup.user_id == user_id
                )
            ).one()
            position = int(max_position) + 10

        group = PersonGroup(
            user_id=user_id,
            name=group_data.name.strip(),
            color_value=group_data.color_value,
            icon=group_data.icon,
            position=position,
        )
        try:
            self.session.add(group)
            self.session.commit()
            self.session.refresh(group)
        except IntegrityError as exc:
            self.session.rollback()
            log_error(exc)
            if self._is_duplicate_group_name_error(exc):
                raise ValueError(f"Person group with name '{group.name}' already exists") from exc
            raise ValueError("Database constraint violated") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Person group created: {group.id} for user {user_id}")
        return group

    def get_user_groups(self, user_id: uuid.UUID) -> List[PersonGroup]:
        """Get all person groups for a user, ordered by position."""
        statement = (
            select(PersonGroup)
            .where(PersonGroup.user_id == user_id)
            .options(selectinload(PersonGroup.people))  # type: ignore[arg-type]
            .order_by(col(PersonGroup.position), col(PersonGroup.name))
        )
        groups = self.session.exec(statement).all()
        return list(groups)

    def get_group_by_id(self, group_id: uuid.UUID, user_id: uuid.UUID) -> Optional[PersonGroup]:
        """Get a group by ID, ensuring it belongs to the user."""
        statement = (
            select(PersonGroup)
            .where(PersonGroup.id == group_id, PersonGroup.user_id == user_id)
            .options(selectinload(PersonGroup.people))  # type: ignore[arg-type]
        )
        return self.session.exec(statement).first()

    def update_group(
        self,
        group_id: uuid.UUID,
        user_id: uuid.UUID,
        group_data: PersonGroupUpdate,
    ) -> PersonGroup:
        """Update a person group."""
        group = self.get_group_by_id(group_id, user_id)
        if not group:
            raise PersonGroupNotFoundError(f"Person group {group_id} not found")

        update_data = group_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "name" and isinstance(value, str):
                value = value.strip()
            setattr(group, key, value)

        try:
            self.session.add(group)
            self.session.commit()
            self.session.refresh(group)
        except IntegrityError as exc:
            self.session.rollback()
            log_error(exc)
            if self._is_duplicate_group_name_error(exc):
                raise ValueError(f"Person group with name '{group.name}' already exists") from exc
            raise ValueError("Database constraint violated") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Person group updated: {group_id}")
        return group

    def delete_group(self, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Delete a person group."""
        group = self.get_group_by_id(group_id, user_id)
        if not group:
            raise PersonGroupNotFoundError(f"Person group {group_id} not found")

        try:
            self.session.delete(group)
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Person group deleted: {group_id}")

    def reorder_groups(self, user_id: uuid.UUID, updates: list[tuple[uuid.UUID, int]]) -> None:
        """Bulk update person group positions for a user."""
        if not updates:
            return

        requested_ids = [group_id for group_id, _ in updates]
        if len(set(requested_ids)) != len(requested_ids):
            raise ValueError("Duplicate group IDs are not allowed in reorder updates")

        requested_ids = list(dict.fromkeys(requested_ids))
        existing_ids = set(
            self.session.exec(
                select(PersonGroup.id).where(
                    col(PersonGroup.user_id) == user_id,
                    col(PersonGroup.id).in_(requested_ids),
                )
            ).all()
        )
        if len(existing_ids) != len(requested_ids):
            raise PersonGroupNotFoundError("One or more person groups were not found")

        updated = apply_position_updates(self.session, PersonGroup, user_id, updates)
        expected = len(requested_ids)
        if updated != expected:
            raise PersonGroupNotFoundError("One or more person groups were not found")
        if updated:
            log_info(f"Person groups reordered for user {user_id}")
