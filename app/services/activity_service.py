"""
Activity service for managing activity definitions.
"""
import uuid
from typing import List, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, col, func, select

from app.core.logging_config import log_error, log_info
from app.core.time_utils import utc_now
from app.models.activity import Activity
from app.models.activity_group import ActivityGroup
from app.models.moment import Moment, MomentMoodActivity
from app.schemas.activity import ActivityCreate, ActivityUpdate
from app.services.reorder_utils import apply_position_updates


class ActivityNotFoundError(Exception):
    """Raised when an activity is not found."""


class ActivityService:
    """Service class for activity operations."""

    def __init__(self, session: Session):
        self.session = session

    def _commit(self) -> None:
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    def create_activity(self, user_id: uuid.UUID, activity_data: ActivityCreate) -> Activity:
        """Create a new activity for a user."""
        normalized_name = activity_data.name.strip()
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

        existing = self.session.exec(
            select(Activity).where(
                col(Activity.user_id) == user_id,
                func.lower(Activity.name) == normalized_name.lower(),
            )
        ).first()
        if existing:
            if existing.is_active:
                raise ValueError(f"Activity with name '{normalized_name}' already exists")

            existing.name = normalized_name
            existing.icon = activity_data.icon
            existing.color = activity_data.color
            existing.group_id = activity_data.group_id
            existing.position = position
            existing.is_active = True
            existing.updated_at = utc_now()
            self.session.add(existing)
            self._commit()
            self.session.refresh(existing)
            log_info(f"Activity reactivated: {existing.id} for user {user_id}")
            return existing

        activity = Activity(
            user_id=user_id,
            name=normalized_name,
            icon=activity_data.icon,
            color=activity_data.color,
            group_id=activity_data.group_id,
            position=position,
            is_active=True,
        )
        try:
            self.session.add(activity)
            self.session.commit()
            self.session.refresh(activity)
        except IntegrityError as exc:
            self.session.rollback()
            log_error(exc)
            if "idx_activity_user_name" in str(exc.orig):
                raise ValueError(f"Activity with name '{normalized_name}' already exists") from exc
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
        statement = select(Activity).where(
            Activity.user_id == user_id,
            col(Activity.is_active).is_(True),
        )

        if search:
            normalized = search.strip().lower()
            escaped = self._escape_like_pattern(normalized)
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

    @staticmethod
    def _escape_like_pattern(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def get_activity_by_id(
        self,
        activity_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        include_inactive: bool = False,
    ) -> Optional[Activity]:
        """Get an activity by ID, ensuring it belongs to the user."""
        statement = select(Activity).where(
            Activity.id == activity_id,
            Activity.user_id == user_id,
        )
        if not include_inactive:
            statement = statement.where(col(Activity.is_active).is_(True))
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

        activity.is_active = False
        activity.updated_at = utc_now()
        self.session.add(activity)
        self._commit()
        log_info(f"Activity soft-deleted: {activity_id}")

    def reorder_activities(self, user_id: uuid.UUID, updates: list[tuple[uuid.UUID, int]]) -> None:
        """Bulk update activity positions for a user."""
        if updates:
            requested_ids = [activity_id for activity_id, _ in updates]
            active_ids = set(
                self.session.exec(
                    select(Activity.id).where(
                        col(Activity.user_id) == user_id,
                        col(Activity.is_active).is_(True),
                        col(Activity.id).in_(requested_ids),
                    )
                ).all()
            )
            if len(active_ids) != len(set(requested_ids)):
                raise ActivityNotFoundError("One or more activities not found")
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
