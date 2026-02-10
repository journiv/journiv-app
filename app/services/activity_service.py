"""
Activity service for managing activity definitions.
"""
import uuid
from typing import List, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, col, func, select

from app.core.logging_config import log_error, log_info
from app.models.activity import Activity
from app.models.activity_group import ActivityGroup
from app.models.moment import Moment, MomentMoodActivity
from app.schemas.activity import ActivityCreate, ActivityUpdate
from app.services.entry_service import EntryService
from app.services.reorder_utils import apply_position_updates


class ActivityNotFoundError(Exception):
    """Raised when an activity is not found."""


class ActivityService:
    """Service class for activity operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_activity(self, user_id: uuid.UUID, activity_data: ActivityCreate) -> Activity:
        """Create a new activity for a user."""
        if activity_data.group_id is not None:
            self._validate_group_id(user_id, activity_data.group_id)
        position = activity_data.position
        if position is None:
            max_position = self.session.exec(
                select(func.max(Activity.position)).where(
                    Activity.user_id == user_id,
                    Activity.group_id == activity_data.group_id,
                )
            ).first()
            position = (max_position or 0) + 1

        activity = Activity(
            user_id=user_id,
            name=activity_data.name,
            icon=activity_data.icon,
            color=activity_data.color,
            group_id=activity_data.group_id,
            position=position,
        )
        try:
            self.session.add(activity)
            self.session.commit()
            self.session.refresh(activity)
        except IntegrityError as exc:
            self.session.rollback()
            log_error(exc)
            if "idx_activity_user_name" in str(exc.orig):
                raise ValueError(f"Activity with name '{activity_data.name}' already exists") from exc
            raise ValueError("Database constraint violated") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Activity created: {activity.id} for user {user_id}")
        return activity

    def get_user_activities(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
    ) -> List[Activity]:
        """Get all activities for a user with optional search."""
        statement = select(Activity).where(Activity.user_id == user_id)

        if search:
            normalized = search.strip().lower()
            escaped = EntryService._escape_like_pattern(normalized)
            statement = statement.where(
                func.lower(Activity.name).like(f"%{escaped}%", escape="\\")
            )

        statement = statement.order_by(
            col(Activity.group_id),
            col(Activity.position),
            col(Activity.name),
        ).limit(limit).offset(offset)
        activities = self.session.exec(statement).all()
        return list(activities)

    def get_activity_by_id(self, activity_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Activity]:
        """Get an activity by ID, ensuring it belongs to the user."""
        statement = select(Activity).where(
            Activity.id == activity_id,
            Activity.user_id == user_id,
        )
        return self.session.exec(statement).first()

    def update_activity(
        self,
        activity_id: uuid.UUID,
        user_id: uuid.UUID,
        activity_data: ActivityUpdate,
    ) -> Activity:
        """Update an activity."""
        activity = self.get_activity_by_id(activity_id, user_id)
        if not activity:
            raise ActivityNotFoundError(f"Activity {activity_id} not found")

        update_data = activity_data.model_dump(exclude_unset=True)
        if "group_id" in update_data and update_data["group_id"] is not None:
            self._validate_group_id(user_id, update_data["group_id"])
        for key, value in update_data.items():
            setattr(activity, key, value)

        try:
            self.session.add(activity)
            self.session.commit()
            self.session.refresh(activity)
        except IntegrityError as exc:
            self.session.rollback()
            log_error(exc)
            raise ValueError("Activity name already exists") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Activity updated: {activity_id}")
        return activity

    def delete_activity(self, activity_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Delete an activity and all associated moment links (CASCADE)."""
        activity = self.get_activity_by_id(activity_id, user_id)
        if not activity:
            raise ActivityNotFoundError(f"Activity {activity_id} not found")

        try:
            self.session.delete(activity)
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Activity deleted: {activity_id}")

    def reorder_activities(self, user_id: uuid.UUID, updates: list[tuple[uuid.UUID, int]]) -> None:
        """Bulk update activity positions for a user."""
        updated = apply_position_updates(self.session, Activity, user_id, updates)
        if updated != len({activity_id for activity_id, _ in updates}):
            raise ActivityNotFoundError("One or more activities not found")
        if updated:
            log_info(f"Activities reordered for user {user_id}")

    def get_activity_usage_count(self, activity_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Calculate usage count from MomentMoodActivity links."""
        activity_count = self.session.exec(
            select(func.count(MomentMoodActivity.id))
            .join(Moment, MomentMoodActivity.moment_id == Moment.id)
            .where(
                MomentMoodActivity.activity_id == activity_id,
                Moment.user_id == user_id,
            )
        ).first() or 0
        return activity_count

    def _validate_group_id(self, user_id: uuid.UUID, group_id: uuid.UUID) -> None:
        exists = self.session.exec(
            select(ActivityGroup.id).where(
                ActivityGroup.id == group_id,
                ActivityGroup.user_id == user_id,
            )
        ).first()
        if not exists:
            raise ValueError("Activity group not found")
