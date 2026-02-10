"""
Goal service for creating, listing, and logging goal completions.
"""
import uuid
from calendar import monthrange
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, cast

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, delete, select

from app.core.db_utils import normalize_uuid_list
from app.core.exceptions import ValidationError
from app.core.logging_config import log_error, log_info
from app.core.time_utils import local_date_for_user, utc_now
from app.models.activity import Activity
from app.models.enums import GoalFrequency, GoalLogSource, GoalLogStatus, GoalType
from app.models.goal import Goal, GoalLog, GoalManualLog
from app.models.goal_category import GoalCategory
from app.models.moment import Moment, MomentMoodActivity
from app.models.user import UserSettings
from app.schemas.goal import GoalCreate, GoalUpdate
from app.services.reorder_utils import apply_position_updates


class GoalNotFoundError(Exception):
    """Raised when a goal is not found."""


class GoalService:
    """Service class for goal operations."""

    def __init__(self, session: Session):
        self.session = session

    def _commit(self) -> None:
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    def _get_user_settings(self, user_id: uuid.UUID) -> Optional[UserSettings]:
        return self.session.exec(
            select(UserSettings).where(col(UserSettings.user_id) == user_id)
        ).first()

    def _get_week_range(self, user_id: uuid.UUID, reference_date: Optional[date] = None) -> tuple[date, date]:
        settings = self._get_user_settings(user_id)
        tz_name = settings.time_zone if settings else "UTC"
        ref_date = reference_date or local_date_for_user(utc_now(), tz_name)
        start_of_week_day = settings.start_of_week_day if settings else 0  # 0=Mon ... 6=Sun
        if start_of_week_day < 0 or start_of_week_day > 6:
            start_of_week_day = 0
        delta = (ref_date.weekday() - start_of_week_day) % 7
        week_start = ref_date - timedelta(days=delta)
        week_end = week_start + timedelta(days=6)
        return week_start, week_end

    def _get_period_range(
        self,
        user_id: uuid.UUID,
        frequency_type: GoalFrequency,
        reference_date: date,
    ) -> tuple[date, date]:
        if frequency_type == GoalFrequency.DAILY:
            return reference_date, reference_date
        if frequency_type == GoalFrequency.MONTHLY:
            last_day = monthrange(reference_date.year, reference_date.month)[1]
            start = reference_date.replace(day=1)
            end = reference_date.replace(day=last_day)
            return start, end
        return self._get_week_range(user_id, reference_date)

    def _get_activity_days(
        self,
        user_id: uuid.UUID,
        activity_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> Set[date]:
        rows = self.session.exec(
            select(col(Moment.logged_date))
            .join(
                MomentMoodActivity,
                col(MomentMoodActivity.moment_id) == col(Moment.id),
            )
            .where(
                col(Moment.user_id) == user_id,
                col(MomentMoodActivity.activity_id) == activity_id,
                col(Moment.logged_date) >= period_start,
                col(Moment.logged_date) <= period_end,
            )
            .distinct()
        ).all()
        return {row for row in rows if row is not None}

    def _get_manual_logs(
        self,
        goal_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> List[GoalManualLog]:
        return list(
            self.session.exec(
                select(GoalManualLog).where(
                    col(GoalManualLog.goal_id) == goal_id,
                    col(GoalManualLog.logged_date) >= period_start,
                    col(GoalManualLog.logged_date) <= period_end,
                )
            )
        )

    def _apply_manual_overrides(
        self,
        goal_type: GoalType,
        base_days: Set[date],
        manual_logs: List[GoalManualLog],
    ) -> Set[date]:
        days = set(base_days)
        for manual in manual_logs:
            if goal_type == GoalType.ACHIEVE:
                if manual.status == GoalLogStatus.SUCCESS:
                    days.add(manual.logged_date)
                else:
                    days.discard(manual.logged_date)
            else:
                if manual.status == GoalLogStatus.SUCCESS:
                    days.discard(manual.logged_date)
                else:
                    days.add(manual.logged_date)
        return days

    @staticmethod
    def _status_from_count(goal_type: GoalType, target_count: int, count: int) -> GoalLogStatus:
        if goal_type == GoalType.ACHIEVE:
            return GoalLogStatus.SUCCESS if count >= target_count else GoalLogStatus.FAIL
        return GoalLogStatus.FAIL if count > 0 else GoalLogStatus.SUCCESS

    def _compute_period_progress(
        self,
        goal: Goal,
        period_start: date,
        period_end: date,
    ) -> tuple[int, GoalLogStatus]:
        activity_days: Set[date] = set()
        if goal.activity_id:
            activity_days = self._get_activity_days(
                goal.user_id,
                goal.activity_id,
                period_start,
                period_end,
            )
        manual_logs = self._get_manual_logs(goal.id, period_start, period_end)
        days = self._apply_manual_overrides(goal.goal_type, activity_days, manual_logs)
        count = len(days)
        status = self._status_from_count(goal.goal_type, goal.target_count, count)
        return count, status

    def recalculate_period(
        self,
        goal: Goal,
        reference_date: date,
        is_period_closed: bool = False,
    ) -> None:
        period_start, period_end = self._get_period_range(
            goal.user_id,
            goal.frequency_type,
            reference_date,
        )
        count, status = self._compute_period_progress(goal, period_start, period_end)
        existing = self.session.exec(
            select(GoalLog).where(
                col(GoalLog.goal_id) == goal.id,
                col(GoalLog.period_start) == period_start,
            )
        ).first()

        if goal.goal_type == GoalType.AVOID and count == 0 and not is_period_closed:
            if existing is not None and existing.source == GoalLogSource.AUTO:
                self.session.delete(existing)
            return

        if existing is None:
            log = GoalLog(
                goal_id=goal.id,
                user_id=goal.user_id,
                logged_date=period_start,
                period_start=period_start,
                period_end=period_end,
                status=status,
                count=count,
                source=GoalLogSource.AUTO,
                last_updated_at=utc_now(),
            )
            self.session.add(log)
        else:
            if existing.source != GoalLogSource.MANUAL:
                existing.logged_date = period_start
                existing.period_start = period_start
                existing.period_end = period_end
                existing.status = status
                existing.count = count
                existing.last_updated_at = utc_now()
                self.session.add(existing)

    def recalculate_for_activities(
        self,
        user_id: uuid.UUID,
        reference_date: date,
        activity_ids: List[uuid.UUID],
    ) -> None:
        if not activity_ids:
            return
        goals = list(
            self.session.exec(
                select(Goal).where(
                    col(Goal.user_id) == user_id,
                    col(Goal.archived_at).is_(None),
                    col(Goal.is_paused).is_(False),
                    col(Goal.activity_id).in_(normalize_uuid_list(activity_ids)),
                )
            )
        )
        for goal in goals:
            self.recalculate_period(goal, reference_date)

    def create_goal(self, user_id: uuid.UUID, data: GoalCreate) -> Goal:
        try:
            goal_type = GoalType(data.goal_type)
            frequency_type = GoalFrequency(data.frequency_type)
        except ValueError as exc:
            raise ValidationError("Invalid goal type or frequency") from exc

        if data.activity_id is not None:
            self._validate_activity_id(user_id, data.activity_id)
        if data.category_id is not None:
            self._validate_category_id(user_id, data.category_id)
        position = data.position
        if position is None:
            max_position = self.session.exec(
                select(func.coalesce(func.max(Goal.position), 0)).where(Goal.user_id == user_id)
            ).one()
            position = int(max_position) + 10

        goal = Goal(
            user_id=user_id,
            activity_id=data.activity_id,
            category_id=data.category_id,
            title=data.title,
            goal_type=goal_type,
            frequency_type=frequency_type,
            target_count=data.target_count,
            reminder_time=data.reminder_time,
            is_paused=data.is_paused,
            icon=data.icon,
            color_value=data.color_value,
            position=position,
            archived_at=None,
        )
        self.session.add(goal)
        self._commit()
        self.session.refresh(goal)
        if goal.activity_id and goal.goal_type == GoalType.ACHIEVE:
            self._backfill_goal(goal)
        log_info(f"Goal created for user {user_id}: {goal.id}")
        return goal

    def _backfill_goal(self, goal: Goal) -> None:
        if not goal.activity_id:
            return
        min_date = self.session.exec(
            select(func.min(Moment.logged_date))
            .join(MomentMoodActivity, MomentMoodActivity.moment_id == Moment.id)
            .where(
                col(Moment.user_id) == goal.user_id,
                col(MomentMoodActivity.activity_id) == goal.activity_id,
            )
        ).first()
        if not min_date:
            return
        start_date = min_date
        today = utc_now().date()
        cursor = start_date
        while cursor <= today:
            period_start, period_end = self._get_period_range(goal.user_id, goal.frequency_type, cursor)
            self.recalculate_period(goal, cursor, is_period_closed=True)
            cursor = period_end + timedelta(days=1)
        self._commit()

    def update_goal(self, goal_id: uuid.UUID, user_id: uuid.UUID, data: GoalUpdate) -> Goal:
        goal = self.get_goal(goal_id, user_id)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            try:
                if field == "goal_type" and value is not None:
                    value = GoalType(value)
                if field == "frequency_type" and value is not None:
                    value = GoalFrequency(value)
            except ValueError as exc:
                raise ValidationError("Invalid goal update value") from exc
            if field == "activity_id" and value is not None:
                self._validate_activity_id(user_id, cast(uuid.UUID, value))
            if field == "category_id" and value is not None:
                self._validate_category_id(user_id, cast(uuid.UUID, value))
            setattr(goal, field, value)
        goal.updated_at = utc_now()
        self.session.add(goal)
        self._commit()
        self.session.refresh(goal)
        return goal

    def get_goal(self, goal_id: uuid.UUID, user_id: uuid.UUID) -> Goal:
        goal = self.session.exec(
            select(Goal).where(col(Goal.id) == goal_id, col(Goal.user_id) == user_id)
        ).first()
        if not goal:
            raise GoalNotFoundError("Goal not found")
        return goal

    def list_goals_with_progress(
        self,
        user_id: uuid.UUID,
        include_archived: bool = False,
        reference_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        statement = select(Goal).where(col(Goal.user_id) == user_id)
        if not include_archived:
            statement = statement.where(col(Goal.archived_at).is_(None))
        goals = list(
            self.session.exec(
                statement.order_by(col(Goal.position), col(Goal.title))
            )
        )
        if not goals:
            return []

        ref_date = reference_date or utc_now().date()
        period_ranges: Dict[uuid.UUID, Tuple[date, date]] = {}
        for goal in goals:
            period_ranges[goal.id] = self._get_period_range(user_id, goal.frequency_type, ref_date)

        min_start = min(start for start, _ in period_ranges.values())
        max_end = max(end for _, end in period_ranges.values())

        activity_ids = [goal.activity_id for goal in goals if goal.activity_id]
        activity_days_map = self._get_activity_days_for_activities(
            user_id,
            activity_ids,
            min_start,
            max_end,
        )
        manual_logs_map = self._get_manual_logs_for_goals(
            [goal.id for goal in goals],
            min_start,
            max_end,
        )

        results: List[Dict[str, Any]] = []
        for goal in goals:
            period_start, period_end = period_ranges[goal.id]
            activity_days = activity_days_map.get(goal.activity_id, set()) if goal.activity_id else set()
            days = {day for day in activity_days if period_start <= day <= period_end}
            manual_logs = [
                log for log in manual_logs_map.get(goal.id, [])
                if period_start <= log.logged_date <= period_end
            ]
            days = self._apply_manual_overrides(goal.goal_type, days, manual_logs)
            count = len(days)
            status = self._status_from_count(goal.goal_type, goal.target_count, count)
            results.append(
                {
                    "goal": goal,
                    "current_period_completed": int(count),
                    "status": status,
                }
            )
        return results

    def _get_activity_days_for_activities(
        self,
        user_id: uuid.UUID,
        activity_ids: List[uuid.UUID],
        period_start: date,
        period_end: date,
    ) -> Dict[uuid.UUID, Set[date]]:
        if not activity_ids:
            return {}
        rows = self.session.exec(
            select(
                col(MomentMoodActivity.activity_id),
                col(Moment.logged_date),
            )
            .join(
                Moment,
                col(MomentMoodActivity.moment_id) == col(Moment.id),
            )
            .where(
                col(Moment.user_id) == user_id,
                col(MomentMoodActivity.activity_id).in_(normalize_uuid_list(activity_ids)),
                col(Moment.logged_date) >= period_start,
                col(Moment.logged_date) <= period_end,
            )
            .distinct()
        ).all()
        activity_days: Dict[uuid.UUID, Set[date]] = {activity_id: set() for activity_id in activity_ids}
        for activity_id, logged_date in rows:
            if activity_id is not None and logged_date is not None:
                activity_days.setdefault(activity_id, set()).add(logged_date)
        return activity_days

    def _get_manual_logs_for_goals(
        self,
        goal_ids: List[uuid.UUID],
        period_start: date,
        period_end: date,
    ) -> Dict[uuid.UUID, List[GoalManualLog]]:
        if not goal_ids:
            return {}
        logs = list(
            self.session.exec(
                select(GoalManualLog).where(
                    col(GoalManualLog.goal_id).in_(normalize_uuid_list(goal_ids)),
                    col(GoalManualLog.logged_date) >= period_start,
                    col(GoalManualLog.logged_date) <= period_end,
                )
            )
        )
        result: Dict[uuid.UUID, List[GoalManualLog]] = {goal_id: [] for goal_id in goal_ids}
        for log in logs:
            result.setdefault(log.goal_id, []).append(log)
        return result

    def close_avoidance_periods_for_user(self, user_id: uuid.UUID) -> int:
        settings = self._get_user_settings(user_id)
        timezone_name = settings.time_zone if settings else "UTC"
        start_of_week_day = settings.start_of_week_day if settings else 0
        today_local = local_date_for_user(utc_now(), timezone_name)
        close_date = today_local - timedelta(days=1)
        should_close_weekly = today_local.weekday() == start_of_week_day
        should_close_monthly = today_local.day == 1

        goals = list(
            self.session.exec(
                select(Goal).where(
                    col(Goal.user_id) == user_id,
                    col(Goal.goal_type) == GoalType.AVOID,
                    col(Goal.archived_at).is_(None),
                    col(Goal.is_paused).is_(False),
                )
            )
        )
        if not goals:
            return 0

        processed = 0
        for goal in goals:
            if goal.activity_id is None:
                continue
            if close_date < goal.created_at.date():
                continue
            if goal.frequency_type == GoalFrequency.DAILY:
                self.recalculate_period(goal, close_date, is_period_closed=True)
                processed += 1
            elif goal.frequency_type == GoalFrequency.WEEKLY and should_close_weekly:
                self.recalculate_period(goal, close_date, is_period_closed=True)
                processed += 1
            elif goal.frequency_type == GoalFrequency.MONTHLY and should_close_monthly:
                self.recalculate_period(goal, close_date, is_period_closed=True)
                processed += 1

        if processed:
            self._commit()
        return processed

    def reorder_goals(self, user_id: uuid.UUID, updates: list[tuple[uuid.UUID, int]]) -> None:
        updated = apply_position_updates(self.session, Goal, user_id, updates)
        if updated:
            log_info(f"Goals reordered for user {user_id}")

    def archive_goal(self, goal_id: uuid.UUID, user_id: uuid.UUID) -> Goal:
        goal = self.get_goal(goal_id, user_id)
        if goal.archived_at is None:
            goal.archived_at = utc_now()
            goal.updated_at = utc_now()
            self.session.add(goal)
            self._commit()
            self.session.refresh(goal)
        return goal

    def toggle_goal_completion(
        self,
        goal_id: uuid.UUID,
        user_id: uuid.UUID,
        logged_date: date,
        status: Optional[str] = None,
    ) -> bool:
        goal = self.get_goal(goal_id, user_id)
        if goal.archived_at is not None:
            raise ValidationError("Cannot toggle an archived goal")

        existing = self.session.exec(
            select(GoalManualLog).where(
                col(GoalManualLog.goal_id) == goal_id,
                col(GoalManualLog.logged_date) == logged_date,
            )
        ).first()

        if status is None:
            if existing:
                self.session.exec(
                    delete(GoalManualLog).where(
                        col(GoalManualLog.goal_id) == goal_id,
                        col(GoalManualLog.logged_date) == logged_date,
                    )
                )
                self.recalculate_period(goal, logged_date)
                self._commit()
                return False
            new_log = GoalManualLog(
                goal_id=goal_id,
                user_id=user_id,
                logged_date=logged_date,
                status=GoalLogStatus.SUCCESS,
            )
            self.session.add(new_log)
            self.recalculate_period(goal, logged_date)
            self._commit()
            return True

        try:
            parsed_status = GoalLogStatus(status)
        except ValueError as exc:
            raise ValidationError("Invalid goal status") from exc

        if existing:
            existing.status = parsed_status
            existing.updated_at = utc_now()
            self.session.add(existing)
        else:
            new_log = GoalManualLog(
                goal_id=goal_id,
                user_id=user_id,
                logged_date=logged_date,
                status=parsed_status,
            )
            self.session.add(new_log)
        self.recalculate_period(goal, logged_date)
        self._commit()
        return parsed_status == GoalLogStatus.SUCCESS

    def _validate_activity_id(self, user_id: uuid.UUID, activity_id: uuid.UUID) -> None:
        exists = self.session.exec(
            select(Activity.id).where(
                col(Activity.id) == activity_id,
                col(Activity.user_id) == user_id,
            )
        ).first()
        if not exists:
            raise ValidationError("Activity not found")

    def _validate_category_id(self, user_id: uuid.UUID, category_id: uuid.UUID) -> None:
        exists = self.session.exec(
            select(GoalCategory.id).where(
                col(GoalCategory.id) == category_id,
                col(GoalCategory.user_id) == user_id,
            )
        ).first()
        if not exists:
            raise ValidationError("Goal category not found")

    def log_completions_for_activities(
        self,
        user_id: uuid.UUID,
        logged_date: date,
        activity_ids: List[uuid.UUID],
    ) -> None:
        self.recalculate_for_activities(user_id, logged_date, activity_ids)
        self._commit()
