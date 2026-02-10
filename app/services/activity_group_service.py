"""
Activity Group service for managing activity groups.
"""
import uuid
from typing import List, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, func, select

from app.core.logging_config import log_error, log_info
from app.models.activity_group import ActivityGroup
from app.schemas.activity_group import ActivityGroupCreate, ActivityGroupUpdate
from app.services.reorder_utils import apply_position_updates


class ActivityGroupNotFoundError(Exception):
    """Raised when an activity group is not found."""
    pass

class ActivityGroupService:
    """Service class for activity group operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_group(self, user_id: uuid.UUID, group_data: ActivityGroupCreate) -> ActivityGroup:
        """Create a new activity group."""
        position = group_data.position
        if position is None:
            max_position = self.session.exec(
                select(func.coalesce(func.max(ActivityGroup.position), 0)).where(
                    ActivityGroup.user_id == user_id
                )
            ).one()
            position = int(max_position) + 10
        group = ActivityGroup(
            user_id=user_id,
            name=group_data.name,
            color_value=group_data.color_value,
            icon=group_data.icon,
            position=position
        )
        try:
            self.session.add(group)
            self.session.commit()
            self.session.refresh(group)
        except IntegrityError as exc:
            self.session.rollback()
            log_error(exc)
            orig = getattr(exc, "orig", None)
            orig_text = str(orig) if orig is not None else ""
            if "idx_activity_group_user_name" in orig_text:
                raise ValueError(f"Activity group with name '{group.name}' already exists") from exc
            raise ValueError("Database constraint violated") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Activity group created: {group.id} for user {user_id}")
        return group

    def get_user_groups(self, user_id: uuid.UUID) -> List[ActivityGroup]:
        """Get all activity groups for a user, ordered by position."""
        statement = (
            select(ActivityGroup)
            .where(ActivityGroup.user_id == user_id)
            .options(selectinload(ActivityGroup.activities))  # type: ignore[arg-type]
            .order_by(col(ActivityGroup.position), col(ActivityGroup.name))
        )

        groups = self.session.exec(statement).all()
        return list(groups)

    def get_group_by_id(self, group_id: uuid.UUID, user_id: uuid.UUID) -> Optional[ActivityGroup]:
        """Get a group by ID, ensuring it belongs to the user."""
        statement = select(ActivityGroup).where(
            ActivityGroup.id == group_id,
            ActivityGroup.user_id == user_id
        )
        return self.session.exec(statement).first()

    def update_group(
        self,
        group_id: uuid.UUID,
        user_id: uuid.UUID,
        group_data: ActivityGroupUpdate
    ) -> ActivityGroup:
        """Update an activity group."""
        group = self.get_group_by_id(group_id, user_id)
        if not group:
            raise ActivityGroupNotFoundError(f"Activity group {group_id} not found")

        update_data = group_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(group, key, value)

        try:
            self.session.add(group)
            self.session.commit()
            self.session.refresh(group)
        except IntegrityError as exc:
            self.session.rollback()
            log_error(exc)
            orig = getattr(exc, "orig", None)
            orig_text = str(orig) if orig is not None else ""
            if "idx_activity_group_user_name" in orig_text:
                raise ValueError(f"Activity group with name '{group.name}' already exists") from exc
            raise ValueError("Database constraint violated") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Activity group updated: {group_id}")
        return group

    def delete_group(self, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """
        Delete an activity group.
        Activities in this group will have group_id set to NULL (handled by ON DELETE SET NULL in DB if configured,
        or we can do it explicitly if needed, but SQLModel relationship 'ondelete' handles the schema definition,
        we trust the DB foreign key constraint 'SET NULL').
        """
        group = self.get_group_by_id(group_id, user_id)
        if not group:
            raise ActivityGroupNotFoundError(f"Activity group {group_id} not found")

        try:
            self.session.delete(group)
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Activity group deleted: {group_id}")

    def reorder_groups(self, user_id: uuid.UUID, updates: list[tuple[uuid.UUID, int]]) -> None:
        """Bulk update activity group positions for a user."""
        updated = apply_position_updates(self.session, ActivityGroup, user_id, updates)
        if updated:
            log_info(f"Activity groups reordered for user {user_id}")

    def get_group_with_activities(self, group_id: uuid.UUID, user_id: uuid.UUID) -> Optional[ActivityGroup]:
        """Get a group with its activities."""
        statement = (
            select(ActivityGroup)
            .where(
                ActivityGroup.id == group_id,
                ActivityGroup.user_id == user_id,
            )
            .options(selectinload(ActivityGroup.activities))  # type: ignore[arg-type]
        )
        return self.session.exec(statement).first()
