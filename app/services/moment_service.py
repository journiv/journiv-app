"""
Moment service for unified timeline operations.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional, Tuple

from sqlalchemy import String, cast, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, col, delete, select

from app.core.db_utils import normalize_uuid_list
from app.core.exceptions import EntryNotFoundError, ValidationError
from app.core.logging_config import log_error, log_info
from app.core.time_utils import ensure_utc, local_date_for_user, utc_now
from app.models.activity import Activity
from app.models.entry import Entry
from app.models.moment import Moment, MomentMoodActivity
from app.models.mood import Mood
from app.schemas.entry import EntryCreate
from app.schemas.moment import (
    MomentCreate,
    MomentMoodActivityInput,
    MomentUpdate,
)
from app.services.goal_service import GoalService


class MomentNotFoundError(Exception):
    """Raised when a moment is not found."""


class MomentService:
    """Service class for moment operations."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _reference_date(moment: Moment) -> date:
        if moment.logged_date is not None:
            return moment.logged_date
        tz_name = (moment.logged_timezone or "UTC").strip() or "UTC"
        return local_date_for_user(ensure_utc(moment.logged_at), tz_name)

    def _commit(self) -> None:
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    def _get_owned_moment(self, user_id: uuid.UUID, moment_id: uuid.UUID) -> Moment:
        moment = self.session.exec(
            select(Moment).where(Moment.id == moment_id, Moment.user_id == user_id)
        ).first()
        if not moment:
            raise MomentNotFoundError("Moment not found")
        return moment

    def _normalize_moment_timestamp(
        self,
        *,
        logged_at: Optional[datetime],
        logged_date: Optional[date],
        logged_timezone: Optional[str],
        fallback_timezone: str,
    ) -> Tuple[datetime, date, str]:
        timezone_name = (logged_timezone or fallback_timezone or "UTC").strip() or "UTC"
        if logged_at is not None:
            normalized_dt = ensure_utc(logged_at)
        else:
            normalized_dt = utc_now()
        derived_date = logged_date or local_date_for_user(normalized_dt, timezone_name)
        return normalized_dt, derived_date, timezone_name

    def _validate_mood_activity_inputs(
        self,
        user_id: uuid.UUID,
        items: List[MomentMoodActivityInput],
        primary_mood_id: Optional[uuid.UUID],
    ) -> None:
        mood_ids = {item.mood_id for item in items if item.mood_id is not None}
        activity_ids = {item.activity_id for item in items if item.activity_id is not None}

        if primary_mood_id and primary_mood_id not in mood_ids:
            raise ValidationError("primary_mood_id must be part of the moment mood set")

        if mood_ids:
            normalized_ids = normalize_uuid_list(mood_ids)
            statement = select(Mood.id).where(
                col(Mood.is_active).is_(True),
                (col(Mood.user_id).is_(None)) | (col(Mood.user_id) == user_id),
            )
            if self.session.get_bind().dialect.name == "sqlite":
                string_ids = {str(uid) for uid in normalized_ids}
                string_ids.update({uid.hex for uid in normalized_ids})
                statement = statement.where(
                    or_(
                        col(Mood.id).in_(normalized_ids),
                        cast(col(Mood.id), String).in_(list(string_ids)),
                    )
                )
            else:
                statement = statement.where(col(Mood.id).in_(normalized_ids))
            existing_moods = self.session.exec(statement).all()
            if len(existing_moods) != len(mood_ids):
                raise ValidationError("One or more moods not found")

        if activity_ids:
            existing_activities = self.session.exec(
                select(Activity.id).where(
                    col(Activity.id).in_(normalize_uuid_list(activity_ids)),
                    col(Activity.user_id) == user_id,
                )
            ).all()
            if len(existing_activities) != len(activity_ids):
                raise ValidationError("One or more activities not found")

    def _validate_activity_ids(self, user_id: uuid.UUID, activity_ids: List[uuid.UUID]) -> None:
        if not activity_ids:
            return
        existing_activities = self.session.exec(
            select(Activity.id).where(
                col(Activity.id).in_(normalize_uuid_list(set(activity_ids))),
                col(Activity.user_id) == user_id,
            )
        ).all()
        if len(existing_activities) != len(set(activity_ids)):
            raise ValidationError("One or more activities not found")

    def _replace_mood_activity_links(
        self,
        moment_id: uuid.UUID,
        items: List[MomentMoodActivityInput],
    ) -> None:
        self.session.exec(
            delete(MomentMoodActivity).where(col(MomentMoodActivity.moment_id) == moment_id)
        )
        seen_pairs: set[tuple[Optional[uuid.UUID], Optional[uuid.UUID]]] = set()
        for item in items:
            pair = (item.mood_id, item.activity_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            link = MomentMoodActivity(
                moment_id=moment_id,
                mood_id=item.mood_id,
                activity_id=item.activity_id,
            )
            self.session.add(link)

    def _resolve_goal_logs(
        self,
        user_id: uuid.UUID,
        moment: Moment,
        items: Optional[List[MomentMoodActivityInput]],
    ) -> None:
        if not items:
            return
        activity_ids = [item.activity_id for item in items if item.activity_id is not None]
        if not activity_ids:
            return
        reference_date = self._reference_date(moment)
        GoalService(self.session).recalculate_for_activities(
            user_id=user_id,
            reference_date=reference_date,
            activity_ids=activity_ids,
        )

    def _sync_activity_links_for_entry(
        self,
        moment_id: uuid.UUID,
        activity_ids: List[uuid.UUID],
    ) -> None:
        self.session.exec(
            delete(MomentMoodActivity).where(
                col(MomentMoodActivity.moment_id) == moment_id,
                col(MomentMoodActivity.mood_id).is_(None),
            )
        )
        for activity_id in set(activity_ids):
            self.session.add(
                MomentMoodActivity(
                    moment_id=moment_id,
                    mood_id=None,
                    activity_id=activity_id,
                )
            )

    def create_moment(self, user_id: uuid.UUID, moment_data: MomentCreate) -> Moment:
        from app.services.entry_service import EntryService
        from app.services.user_service import UserService

        entry: Optional[Entry] = None
        if moment_data.entry is not None:
            entry_service = EntryService(self.session)
            entry_payload = EntryCreate.model_validate(moment_data.entry.model_dump())
            entry = entry_service.create_entry(
                user_id=user_id,
                entry_data=entry_payload,
                is_draft=False,
                skip_moment_sync=True,
                commit=False,
                run_side_effects=False,
            )

        user_service = UserService(self.session)
        user_tz = user_service.get_user_timezone(user_id)

        if entry:
            logged_at = entry.entry_datetime_utc
            logged_date = entry.entry_date
            logged_timezone = entry.entry_timezone
        else:
            logged_at = moment_data.logged_at
            logged_date = moment_data.logged_date
            logged_timezone = moment_data.logged_timezone

        normalized_at, normalized_date, normalized_tz = self._normalize_moment_timestamp(
            logged_at=logged_at,
            logged_date=logged_date,
            logged_timezone=logged_timezone,
            fallback_timezone=user_tz,
        )

        items = moment_data.mood_activity or []
        self._validate_mood_activity_inputs(user_id, items, moment_data.primary_mood_id)

        moment = Moment(
            user_id=user_id,
            entry_id=entry.id if entry else None,
            primary_mood_id=moment_data.primary_mood_id,
            logged_at=normalized_at,
            logged_date=normalized_date,
            logged_timezone=normalized_tz,
            note=moment_data.note,
            location_data=moment_data.location_data,
            weather_data=moment_data.weather_data,
        )

        try:
            self.session.add(moment)
            self.session.flush()
            if items:
                self._replace_mood_activity_links(moment.id, items)
            self._resolve_goal_logs(user_id, moment, items)
            self.session.commit()
            self.session.refresh(moment)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        if entry and not entry.is_draft:
            entry_service = EntryService(self.session)
            entry_service._run_entry_side_effects(entry, user_id, skip_moment_sync=True)

        log_info(f"Moment created for user {user_id}: {moment.id}")
        return moment

    def update_moment(self, moment_id: uuid.UUID, user_id: uuid.UUID, moment_data: MomentUpdate) -> Moment:
        from app.services.entry_service import EntryService

        moment = self._get_owned_moment(user_id, moment_id)
        created_entry: Optional[Entry] = None
        previous_activity_ids: List[uuid.UUID] = []
        if moment_data.mood_activity is not None:
            previous_activity_ids = [
                activity_id
                for activity_id in self.session.exec(
                    select(MomentMoodActivity.activity_id).where(
                        col(MomentMoodActivity.moment_id) == moment.id,
                        col(MomentMoodActivity.activity_id).is_not(None),
                    )
                ).all()
                if activity_id is not None
            ]

        entry_service = EntryService(self.session)
        if moment_data.entry_update is not None:
            if not moment.entry_id:
                raise EntryNotFoundError("Moment has no entry to update")
            entry_service.update_entry(moment.entry_id, user_id, moment_data.entry_update)
        elif moment_data.entry_create is not None:
            if moment.entry_id:
                raise ValidationError("Moment already has an entry")
            entry_payload = EntryCreate.model_validate(moment_data.entry_create.model_dump())
            created_entry = entry_service.create_entry(
                user_id=user_id,
                entry_data=entry_payload,
                is_draft=False,
                skip_moment_sync=True,
                commit=False,
                run_side_effects=False,
            )
            moment.entry_id = created_entry.id
            moment.logged_at = created_entry.entry_datetime_utc
            moment.logged_date = created_entry.entry_date
            moment.logged_timezone = created_entry.entry_timezone

        if moment_data.logged_at is not None:
            moment.logged_at = ensure_utc(moment_data.logged_at)
        if moment_data.logged_timezone is not None:
            moment.logged_timezone = (moment_data.logged_timezone or "UTC").strip() or "UTC"
        if moment_data.logged_date is not None:
            moment.logged_date = moment_data.logged_date
        elif moment_data.logged_at is not None or moment_data.logged_timezone is not None:
            moment.logged_date = local_date_for_user(moment.logged_at, moment.logged_timezone)
        if moment_data.note is not None:
            moment.note = moment_data.note
        if moment_data.location_data is not None:
            moment.location_data = moment_data.location_data
        if moment_data.weather_data is not None:
            moment.weather_data = moment_data.weather_data
        if moment_data.primary_mood_id is not None:
            moment.primary_mood_id = moment_data.primary_mood_id

        try:
            if moment_data.mood_activity is not None:
                self._validate_mood_activity_inputs(
                    user_id,
                    moment_data.mood_activity,
                    moment_data.primary_mood_id or moment.primary_mood_id,
                )
                self._replace_mood_activity_links(moment.id, moment_data.mood_activity)
                self._resolve_goal_logs(user_id, moment, moment_data.mood_activity)
                if previous_activity_ids:
                    reference_date = self._reference_date(moment)
                    GoalService(self.session).recalculate_for_activities(
                        user_id=user_id,
                        reference_date=reference_date,
                        activity_ids=previous_activity_ids,
                    )

            moment.updated_at = utc_now()
            self.session.add(moment)
            self.session.commit()
            self.session.refresh(moment)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        if created_entry and not created_entry.is_draft:
            entry_service._run_entry_side_effects(created_entry, user_id, skip_moment_sync=True)
        return moment

    def ensure_moment_for_entry(
        self,
        user_id: uuid.UUID,
        entry: Entry,
        activity_ids: Optional[List[uuid.UUID]] = None,
    ) -> Moment:
        moment = self.session.exec(
            select(Moment).where(Moment.entry_id == entry.id, Moment.user_id == user_id)
        ).first()
        if moment:
            return moment

        moment = Moment(
            user_id=user_id,
            entry_id=entry.id,
            primary_mood_id=None,
            logged_at=entry.entry_datetime_utc,
            logged_date=entry.entry_date,
            logged_timezone=entry.entry_timezone,
            note=None,
            location_data=entry.location_json,
            weather_data=entry.weather_json,
        )
        self.session.add(moment)
        try:
            self.session.flush()
            if activity_ids:
                self._validate_activity_ids(user_id, activity_ids)
                self._sync_activity_links_for_entry(moment.id, activity_ids)
            self._commit()
            self.session.refresh(moment)
        except IntegrityError:
            self.session.rollback()
            moment = self.session.exec(
                select(Moment).where(
                    Moment.entry_id == entry.id,
                    Moment.user_id == user_id,
                )
            ).first()
            if moment:
                return moment
            raise
        return moment

    def sync_entry_activity_links(
        self,
        user_id: uuid.UUID,
        moment_id: uuid.UUID,
        activity_ids: List[uuid.UUID],
    ) -> None:
        self._get_owned_moment(user_id, moment_id)
        self._validate_activity_ids(user_id, activity_ids)
        self._sync_activity_links_for_entry(moment_id, activity_ids)
        self._commit()

    def get_moments(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        cursor_logged_at: Optional[datetime] = None,
        cursor_id: Optional[uuid.UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Tuple[List[Moment], Optional[datetime], Optional[uuid.UUID]]:
        statement = select(Moment).where(Moment.user_id == user_id)

        if start_date:
            statement = statement.where(col(Moment.logged_date) >= start_date)
        if end_date:
            statement = statement.where(col(Moment.logged_date) <= end_date)

        if cursor_logged_at and cursor_id:
            statement = statement.where(
                (Moment.logged_at < cursor_logged_at)
                | ((Moment.logged_at == cursor_logged_at) & (Moment.id < cursor_id))
            )

        statement = statement.order_by(
            col(Moment.logged_at).desc(),
            col(Moment.id).desc(),
        )
        statement = statement.limit(limit + 1)

        rows = list(self.session.exec(statement))
        next_cursor_logged_at = None
        next_cursor_id = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor_logged_at = last.logged_at
            next_cursor_id = last.id
            rows = rows[:limit]
        return rows, next_cursor_logged_at, next_cursor_id

    def get_calendar_summary(
        self,
        user_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Moment]:
        statement = select(Moment).where(Moment.user_id == user_id)
        if start_date:
            statement = statement.where(col(Moment.logged_date) >= start_date)
        if end_date:
            statement = statement.where(col(Moment.logged_date) <= end_date)
        statement = statement.order_by(
            col(Moment.logged_date).desc(),
            col(Moment.logged_at).desc(),
        )
        return list(self.session.exec(statement))
