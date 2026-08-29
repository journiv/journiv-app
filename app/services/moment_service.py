"""
Moment service for unified timeline operations.
"""

import calendar
import uuid
from datetime import date, datetime, timedelta
from typing import Any, List, Optional, Tuple

from sqlalchemy import String, and_, cast, extract, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, delete, select

from app.core.db_utils import normalize_uuid_list
from app.core.exceptions import EntryNotFoundError, ValidationError
from app.core.logging_config import log_error, log_info, log_warning
from app.core.time_utils import ensure_utc, local_date_for_user, utc_now
from app.models.activity import Activity
from app.models.entry import Entry
from app.models.goal import GoalLog
from app.models.moment import Moment, MomentMoodActivity
from app.models.moment_person_link import MomentPersonLink
from app.models.moment_tag_link import MomentTagLink
from app.models.mood import Mood
from app.models.user import UserSettings
from app.schemas.moment import (
    MemoriesAppliedFilter,
    MemoriesFilter,
    MomentCreate,
    MomentMoodActivityInput,
    MomentUpdate,
    PeopleMatch,
)
from app.services.goal_service import GoalService
from app.services.moment_lookup import get_owned_moment


class MomentService:
    """Service class for moment operations."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _reference_date(moment: Moment) -> date:
        if moment.logged_date_tz is not None:
            return moment.logged_date_tz
        tz_name = (moment.logged_timezone or "UTC").strip() or "UTC"
        return local_date_for_user(ensure_utc(moment.logged_at_utc), tz_name)

    def _commit(self) -> None:
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        except Exception as exc:
            log_error(exc, message="Error in _commit - rolling back session")
            self.session.rollback()
            raise

    def _get_owned_moment(self, user_id: uuid.UUID, moment_id: uuid.UUID) -> Moment:
        return get_owned_moment(self.session, user_id, moment_id)

    def _get_owned_moment_with_relations(
        self, user_id: uuid.UUID, moment_id: uuid.UUID
    ) -> Moment:
        return get_owned_moment(
            self.session,
            user_id,
            moment_id,
            options=[
                selectinload(Moment.entry),  # type: ignore[arg-type]
                selectinload(Moment.tags),  # type: ignore[arg-type]
                selectinload(Moment.people),  # type: ignore[arg-type]
                selectinload(Moment.mood_activity_links).selectinload(  # type: ignore[arg-type]
                    MomentMoodActivity.mood  # type: ignore[arg-type]
                ),
                selectinload(Moment.mood_activity_links).selectinload(  # type: ignore[arg-type]
                    MomentMoodActivity.activity  # type: ignore[arg-type]
                ),
            ],
        )

    def get_moment(self, user_id: uuid.UUID, moment_id: uuid.UUID) -> Moment:
        """Get a moment by ID."""
        return self.get_moment_by_id(user_id, moment_id)

    def get_moment_by_id(self, user_id: uuid.UUID, moment_id: uuid.UUID) -> Moment:
        """Get a user-owned moment by ID."""
        return self._get_owned_moment_with_relations(user_id, moment_id)

    def _normalize_moment_timestamp(
        self,
        *,
        logged_at_utc: Optional[datetime],
        logged_date_tz: Optional[date],
        logged_timezone: Optional[str],
        fallback_timezone: str,
    ) -> Tuple[datetime, date, str]:
        timezone_name = (logged_timezone or fallback_timezone or "UTC").strip() or "UTC"
        if logged_at_utc is not None:
            normalized_dt = ensure_utc(logged_at_utc)
        else:
            normalized_dt = utc_now()
        derived_date = logged_date_tz or local_date_for_user(
            normalized_dt, timezone_name
        )
        return normalized_dt, derived_date, timezone_name

    def _validate_mood_activity_inputs(
        self,
        user_id: uuid.UUID,
        items: List[MomentMoodActivityInput],
        primary_mood_id: Optional[uuid.UUID],
    ) -> None:
        mood_ids = {item.mood_id for item in items if item.mood_id is not None}
        activity_ids = {
            item.activity_id for item in items if item.activity_id is not None
        }

        if primary_mood_id and primary_mood_id not in mood_ids:
            raise ValidationError("primary_mood_id must be part of the moment mood set")

        if mood_ids:
            normalized_ids = normalize_uuid_list(mood_ids)
            statement = (
                select(Mood.id)
                .where(
                    col(Mood.is_active).is_(True),
                    col(Mood.user_id) == user_id,
                )
                .where(col(Mood.id).in_(normalized_ids))
            )
            existing_moods = self.session.exec(statement).all()
            if len(existing_moods) != len(mood_ids):
                raise ValidationError("One or more moods not found")

        if activity_ids:
            existing_activities = self.session.exec(
                select(Activity.id).where(
                    col(Activity.id).in_(normalize_uuid_list(activity_ids)),
                    col(Activity.user_id) == user_id,
                    col(Activity.is_active).is_(True),
                )
            ).all()
            if len(existing_activities) != len(activity_ids):
                raise ValidationError("One or more activities not found")

    def _ensure_active_mood_exists(
        self, user_id: uuid.UUID, mood_id: uuid.UUID
    ) -> bool:
        """Helper to check if a mood exists and is active for the user."""
        statement = select(Mood.id).where(
            col(Mood.is_active).is_(True),
            col(Mood.user_id) == user_id,
            col(Mood.id) == mood_id,
        )
        return self.session.exec(statement).first() is not None

    def _validate_activity_ids(
        self, user_id: uuid.UUID, activity_ids: List[uuid.UUID]
    ) -> None:
        if not activity_ids:
            return
        existing_activities = self.session.exec(
            select(Activity.id).where(
                col(Activity.id).in_(normalize_uuid_list(set(activity_ids))),
                col(Activity.user_id) == user_id,
                col(Activity.is_active).is_(True),
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
            delete(MomentMoodActivity).where(
                col(MomentMoodActivity.moment_id) == moment_id
            )
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
        activity_ids = [
            item.activity_id for item in items if item.activity_id is not None
        ]
        if not activity_ids:
            return
        reference_date = self._reference_date(moment)
        GoalService(self.session).recalculate_for_activities(
            user_id=user_id,
            reference_date=reference_date,
            activity_ids=activity_ids,
            triggering_moment_id=moment.id,
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

    @staticmethod
    def _note_has_content(note: Optional[str]) -> bool:
        return bool(note and note.strip())

    @staticmethod
    def _json_has_content(value: Optional[dict]) -> bool:
        return bool(value and len(value) > 0)

    def is_meaningful_moment(self, moment: Moment) -> bool:
        """Return True when a moment contains user-meaningful context."""
        if moment.entry is not None:
            return True
        if self._note_has_content(moment.note):
            return True
        if moment.primary_mood_id is not None:
            return True
        if moment.prompt_id is not None:
            return True
        if moment.media_count > 0:
            return True
        if moment.is_pinned:
            return True
        if self._json_has_content(moment.location_json):
            return True
        if self._json_has_content(moment.weather_json):
            return True
        if moment.weather_summary and moment.weather_summary.strip():
            return True
        if moment.latitude is not None or moment.longitude is not None:
            return True
        if bool(moment.tags):
            return True
        if bool(moment.people):
            return True
        if bool(moment.mood_activity_links):
            return True
        if bool(moment.goal_logs):
            return True
        return False

    def prune_empty_moments(
        self,
        user_id: uuid.UUID,
        moment_ids: Optional[List[uuid.UUID]] = None,
        *,
        commit: bool = True,
    ) -> int:
        """Delete user moments that no longer have meaningful content."""
        statement = (
            select(Moment)
            .where(Moment.user_id == user_id)
            .options(
                selectinload(Moment.entry),  # type: ignore[arg-type]
                selectinload(Moment.tags),  # type: ignore[arg-type]
                selectinload(Moment.people),  # type: ignore[arg-type]
                selectinload(Moment.mood_activity_links),  # type: ignore[arg-type]
                selectinload(Moment.goal_logs),  # type: ignore[arg-type]
            )
        )
        if moment_ids:
            filtered_ids = [
                moment_id for moment_id in moment_ids if moment_id is not None
            ]
            if filtered_ids:
                statement = statement.where(
                    col(Moment.id).in_(normalize_uuid_list(set(filtered_ids)))
                )

        candidates = list(self.session.exec(statement))
        deleted_count = 0
        for moment in candidates:
            if self.is_meaningful_moment(moment):
                continue
            self.session.delete(moment)
            deleted_count += 1

        if deleted_count == 0:
            return 0

        if commit:
            self._commit()
        else:
            self.session.flush()
        return deleted_count

    def _create_associated_entry(
        self,
        user_id: uuid.UUID,
        moment_id: uuid.UUID,
        entry_data: Any,
    ) -> Optional[Entry]:
        """Helper to create an entry associated with a moment."""
        from app.schemas.entry import EntryCreate
        from app.services.entry_service import EntryService

        entry_service = EntryService(self.session)
        entry_payload = EntryCreate(
            title=entry_data.title,
            content_delta=entry_data.content_delta,
            journal_id=entry_data.journal_id,
            moment_id=moment_id,
        )
        return entry_service.create_entry(
            user_id=user_id,
            entry_data=entry_payload,
            is_draft=False,
            skip_moment_sync=True,
            commit=False,
            run_side_effects=False,
        )

    def _sync_narrative(
        self,
        *,
        user_id: uuid.UUID,
        moment: Moment,
        moment_data: MomentUpdate,
        entry_service: Any,
    ) -> Optional[Entry]:
        if (
            moment_data.entry_update is not None
            and moment_data.entry_create is not None
        ):
            raise ValidationError("Provide only one of entry_update or entry_create")

        if moment_data.entry_update is not None:
            entry = self.session.exec(
                select(Entry).where(Entry.moment_id == moment.id)
            ).first()
            if not entry:
                raise EntryNotFoundError("Moment has no entry to update")
            entry_service.update_entry(entry.id, user_id, moment_data.entry_update)
            return None

        if moment_data.entry_create is not None:
            existing_entry = self.session.exec(
                select(Entry).where(Entry.moment_id == moment.id)
            ).first()
            if existing_entry:
                raise ValidationError("Moment already has an entry")
            return self._create_associated_entry(
                user_id, moment.id, moment_data.entry_create
            )

        return None

    def create_moment(self, user_id: uuid.UUID, moment_data: MomentCreate) -> Moment:
        from app.services.entry_service import EntryService
        from app.services.user_service import UserService

        user_service = UserService(self.session)
        user_tz = user_service.get_user_timezone(user_id)

        normalized_at, normalized_date, normalized_tz = (
            self._normalize_moment_timestamp(
                logged_at_utc=moment_data.logged_at_utc,
                logged_date_tz=moment_data.logged_date_tz,
                logged_timezone=moment_data.logged_timezone,
                fallback_timezone=user_tz,
            )
        )

        items = moment_data.mood_activity or []
        self._validate_mood_activity_inputs(user_id, items, moment_data.primary_mood_id)

        moment = Moment(
            user_id=user_id,
            primary_mood_id=moment_data.primary_mood_id,
            prompt_id=moment_data.prompt_id,
            logged_at_utc=normalized_at,
            logged_date_tz=normalized_date,
            logged_timezone=normalized_tz,
            note=moment_data.note,
            location_json=moment_data.location_json,
            latitude=moment_data.latitude,
            longitude=moment_data.longitude,
            weather_json=moment_data.weather_json,
            weather_summary=moment_data.weather_summary,
            is_pinned=moment_data.is_pinned,
        )

        created_entry: Optional[Entry] = None

        try:
            self.session.add(moment)
            self.session.flush()

            if moment_data.entry is not None:
                created_entry = self._create_associated_entry(
                    user_id, moment.id, moment_data.entry
                )

            if items:
                self._replace_mood_activity_links(moment.id, items)

            self._resolve_goal_logs(user_id, moment, items)

            self.session.commit()
            self.session.refresh(moment)
            if created_entry:
                self.session.refresh(created_entry)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        except Exception as exc:
            log_error(exc, message="Error in create_moment - rolling back session")
            self.session.rollback()
            raise

        if created_entry and not created_entry.is_draft:
            entry_service = EntryService(self.session)
            entry_service._run_entry_side_effects(
                created_entry, user_id, skip_moment_sync=True
            )

        log_info(f"Moment created for user {user_id}: {moment.id}")
        return moment

    def update_moment(
        self, moment_id: uuid.UUID, user_id: uuid.UUID, moment_data: MomentUpdate
    ) -> Moment:
        from app.services.entry_service import EntryService

        moment = self._get_owned_moment(user_id, moment_id)
        fields_set = moment_data.model_fields_set

        # Track previous activities for goal recalculation if needed
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

        # Handle Entry Updates/Creation
        created_entry: Optional[Entry] = None
        entry_service = EntryService(self.session)

        created_entry = self._sync_narrative(
            user_id=user_id,
            moment=moment,
            moment_data=moment_data,
            entry_service=entry_service,
        )

        # Update Moment Fields
        if "logged_at_utc" in fields_set and moment_data.logged_at_utc is not None:
            moment.logged_at_utc = ensure_utc(moment_data.logged_at_utc)
        if "logged_timezone" in fields_set:
            moment.logged_timezone = (
                moment_data.logged_timezone or "UTC"
            ).strip() or "UTC"

        # Update derived logged_date_tz
        if "logged_date_tz" in fields_set:
            moment.logged_date_tz = (
                moment_data.logged_date_tz
                if moment_data.logged_date_tz is not None
                else local_date_for_user(moment.logged_at_utc, moment.logged_timezone)
            )
        elif "logged_at_utc" in fields_set or "logged_timezone" in fields_set:
            moment.logged_date_tz = local_date_for_user(
                moment.logged_at_utc, moment.logged_timezone
            )

        # Update other scalar fields
        for field in [
            "note",
            "location_json",
            "latitude",
            "longitude",
            "weather_json",
            "weather_summary",
            "is_pinned",
            "prompt_id",
            "primary_mood_id",
        ]:
            if field in fields_set:
                value = getattr(moment_data, field)
                if field == "primary_mood_id" and value is not None:
                    if not self._ensure_active_mood_exists(user_id, value):
                        raise ValidationError("Invalid or inactive primary mood")
                setattr(moment, field, value)

        # Update Relationships
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
            if created_entry:
                self.session.refresh(created_entry)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        except Exception as exc:
            log_error(exc, message="Error in update_moment - rolling back session")
            self.session.rollback()
            raise

        if created_entry and not created_entry.is_draft:
            entry_service._run_entry_side_effects(
                created_entry, user_id, skip_moment_sync=True
            )

        return moment

    def ensure_moment_for_entry(
        self,
        user_id: uuid.UUID,
        entry: Entry,
        activity_ids: Optional[List[uuid.UUID]] = None,
        primary_mood_id: Optional[uuid.UUID] = None,
        *,
        commit: bool = True,
    ) -> Moment:
        """Validate and sync the moment linked from `entry.moment_id`."""
        moment = self.session.exec(
            select(Moment).where(
                Moment.id == entry.moment_id, Moment.user_id == user_id
            )
        ).first()
        if moment is None:
            raise ValidationError("Moment not found for entry")

        needs_commit = False
        if primary_mood_id is not None and moment.primary_mood_id != primary_mood_id:
            # Validate that the mood exists and is active
            if not self._ensure_active_mood_exists(user_id, primary_mood_id):
                raise ValidationError("Invalid or inactive primary mood")

            moment.primary_mood_id = primary_mood_id
            needs_commit = True

        if activity_ids is not None:
            self._validate_activity_ids(user_id, activity_ids)
            self._sync_activity_links_for_entry(moment.id, activity_ids)
            needs_commit = True

        if needs_commit:
            moment.updated_at = utc_now()
            self.session.add(moment)
            if commit:
                self._commit()
                self.session.refresh(moment)
            else:
                self.session.flush()

        return moment

    def _apply_journal_join(
        self, statement: Any, journal_id: Optional[uuid.UUID]
    ) -> Any:
        """Join Entry table based on journal_id or for general filtering."""
        if journal_id:
            # Filter by journal via entry relationship (Entry.moment_id → Moment.id)
            return statement.join(Entry, Entry.moment_id == Moment.id).where(
                Entry.journal_id == journal_id
            )
        # Left outer join to include moments without entries (Quick Logs)
        return statement.outerjoin(Entry, Entry.moment_id == Moment.id)

    def _apply_draft_filter(
        self,
        statement: Any,
        include_drafts: bool,
        entry_id: Optional[uuid.UUID],
    ) -> Any:
        """Apply filter to exclude drafts unless requested or fetching a specific entry."""
        if not include_drafts and not entry_id:
            # Exclude moments whose entries are drafts
            # Logic: (no entry linked) OR (entry is not a draft)
            return statement.where(
                (col(Entry.id).is_(None)) | (col(Entry.is_draft).is_(False))
            )
        return statement

    def _apply_mood_filter(
        self, statement: Any, mood_ids: Optional[List[uuid.UUID]]
    ) -> Any:
        """Apply filter for moments associated with specific moods.

        A moment "has" a mood when it is the moment's ``primary_mood_id`` (how
        the web editor records mood) or when it appears in the moment's
        mood/activity links (the multi-mood path). Either qualifies.
        """
        if not mood_ids:
            return statement
        # Filter by moments that have ANY of the specified mood_ids
        normalized_mood_ids = normalize_uuid_list(mood_ids)
        return statement.where(
            or_(
                col(Moment.primary_mood_id).in_(normalized_mood_ids),
                col(Moment.id).in_(
                    select(MomentMoodActivity.moment_id).where(
                        col(MomentMoodActivity.mood_id).in_(normalized_mood_ids)
                    )
                ),
            )
        )

    def _apply_search_filter(self, statement: Any, search: Optional[str]) -> Any:
        """Apply search filter on moment notes and entry content."""
        if not search:
            return statement
        escaped_search = (
            search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        search_pattern = f"%{escaped_search}%"
        # Search in Moment note OR Entry title/content
        # Entry is already joined, so we can access it directly
        return statement.where(
            or_(
                col(Moment.note).ilike(search_pattern, escape="\\"),
                col(Entry.title).ilike(search_pattern, escape="\\"),
                col(Entry.content_plain_text).ilike(search_pattern, escape="\\"),
            )
        )

    def _apply_people_filter(
        self,
        statement: Any,
        person_ids: Optional[List[uuid.UUID]],
        people_match: PeopleMatch,
    ) -> Any:
        """Apply filter for moments associated with specific people."""
        if not person_ids:
            return statement
        normalized_person_ids = normalize_uuid_list(person_ids)
        if people_match == PeopleMatch.all:
            required_count = len(set(normalized_person_ids))
            subquery = (
                select(MomentPersonLink.moment_id)
                .where(col(MomentPersonLink.person_id).in_(normalized_person_ids))
                .group_by(col(MomentPersonLink.moment_id))
                .having(
                    func.count(func.distinct(MomentPersonLink.person_id))
                    == required_count
                )
            )
            return statement.where(col(Moment.id).in_(subquery))
        return statement.where(
            col(Moment.id).in_(
                select(MomentPersonLink.moment_id).where(
                    col(MomentPersonLink.person_id).in_(normalized_person_ids)
                )
            )
        )

    def _apply_tag_filter(
        self, statement: Any, tag_ids: Optional[List[uuid.UUID]]
    ) -> Any:
        """Filter to moments carrying ANY of the given tags."""
        if not tag_ids:
            return statement
        normalized_tag_ids = normalize_uuid_list(tag_ids)
        return statement.where(
            col(Moment.id).in_(
                select(MomentTagLink.moment_id).where(
                    col(MomentTagLink.tag_id).in_(normalized_tag_ids)
                )
            )
        )

    def _apply_activity_filter(
        self, statement: Any, activity_ids: Optional[List[uuid.UUID]]
    ) -> Any:
        """Filter to moments logging ANY of the given activities."""
        if not activity_ids:
            return statement
        normalized_activity_ids = normalize_uuid_list(activity_ids)
        return statement.where(
            col(Moment.id).in_(
                select(MomentMoodActivity.moment_id).where(
                    col(MomentMoodActivity.activity_id).in_(normalized_activity_ids)
                )
            )
        )

    def _apply_goal_filter(
        self, statement: Any, goal_id: Optional[uuid.UUID]
    ) -> Any:
        """Filter to moments a completed period of this goal was logged against."""
        if not goal_id:
            return statement
        return statement.where(
            col(Moment.id).in_(
                select(GoalLog.moment_id).where(
                    col(GoalLog.goal_id) == goal_id,
                    col(GoalLog.moment_id).is_not(None),
                )
            )
        )

    def _apply_cursor_filter(
        self,
        statement: Any,
        cursor_logged_at_utc: Optional[datetime],
        cursor_id: Optional[uuid.UUID],
    ) -> Any:
        """Apply cursor-based pagination filter."""
        if cursor_logged_at_utc and cursor_id:
            return statement.where(
                (Moment.logged_at_utc < cursor_logged_at_utc)
                | (
                    (Moment.logged_at_utc == cursor_logged_at_utc)
                    & (Moment.id < cursor_id)
                )
            )
        return statement

    def _apply_date_filter(
        self,
        statement: Any,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> Any:
        """Apply date range filter on logged_date_tz."""
        if start_date:
            statement = statement.where(col(Moment.logged_date_tz) >= start_date)
        if end_date:
            statement = statement.where(col(Moment.logged_date_tz) <= end_date)
        return statement

    def _apply_non_empty_filter(self, statement: Any, include_empty: bool) -> Any:
        """Exclude structurally empty moments unless explicitly requested."""
        if include_empty:
            return statement
        location_json_text = func.trim(cast(col(Moment.location_json), String))
        weather_json_text = func.trim(cast(col(Moment.weather_json), String))
        return statement.where(
            or_(
                col(Entry.id).is_not(None),
                and_(col(Moment.note).is_not(None), func.trim(col(Moment.note)) != ""),
                col(Moment.primary_mood_id).is_not(None),
                col(Moment.prompt_id).is_not(None),
                col(Moment.is_pinned).is_(True),
                col(Moment.media_count) > 0,
                col(Moment.latitude).is_not(None),
                col(Moment.longitude).is_not(None),
                and_(
                    col(Moment.location_json).is_not(None),
                    location_json_text != "",
                    func.lower(location_json_text).notin_(["{}", "[]", "null"]),
                ),
                and_(
                    col(Moment.weather_json).is_not(None),
                    weather_json_text != "",
                    func.lower(weather_json_text).notin_(["{}", "[]", "null"]),
                ),
                and_(
                    col(Moment.weather_summary).is_not(None),
                    func.trim(col(Moment.weather_summary)) != "",
                ),
                col(Moment.id).in_(select(MomentTagLink.moment_id)),
                col(Moment.id).in_(select(MomentPersonLink.moment_id)),
                col(Moment.id).in_(select(MomentMoodActivity.moment_id)),
                col(Moment.id).in_(
                    select(GoalLog.moment_id).where(col(GoalLog.moment_id).is_not(None))
                ),
            )
        )

    def _base_moment_statement(self, user_id: uuid.UUID) -> Any:
        return (
            select(Moment)
            .where(Moment.user_id == user_id)
            .options(
                selectinload(Moment.entry),  # type: ignore[arg-type]
                selectinload(Moment.tags),  # type: ignore[arg-type]
                selectinload(Moment.people),  # type: ignore[arg-type]
                selectinload(Moment.mood_activity_links).selectinload(  # type: ignore[arg-type]
                    MomentMoodActivity.mood  # type: ignore[arg-type]
                ),
                selectinload(Moment.mood_activity_links).selectinload(  # type: ignore[arg-type]
                    MomentMoodActivity.activity  # type: ignore[arg-type]
                ),
            )
            .outerjoin(Entry, col(Entry.moment_id) == col(Moment.id))
            .where((col(Entry.id).is_(None)) | (col(Entry.is_draft).is_(False)))
        )

    def _resolve_user_local_today(self, user_id: uuid.UUID) -> date:
        now_utc = utc_now()
        timezone_name = (
            self.session.exec(
                select(UserSettings.time_zone).where(UserSettings.user_id == user_id)
            ).first()
            or "UTC"
        )
        try:
            return local_date_for_user(now_utc, timezone_name)
        except Exception as exc:
            log_warning(
                exc,
                message="Invalid user timezone encountered while resolving memories date; falling back to UTC",
                user_id=str(user_id),
                timezone=timezone_name,
            )
            return now_utc.date()

    @staticmethod
    def _to_applied_filter(memories_filter: MemoriesFilter) -> MemoriesAppliedFilter:
        if memories_filter == MemoriesFilter.last_years:
            return MemoriesAppliedFilter.last_years
        if memories_filter == MemoriesFilter.last_year:
            return MemoriesAppliedFilter.last_year
        if memories_filter == MemoriesFilter.last_month:
            return MemoriesAppliedFilter.last_month
        return MemoriesAppliedFilter.last_week

    @staticmethod
    def _last_month_window(today_local: date) -> tuple[date, date]:
        current_month_start = today_local.replace(day=1)
        previous_month_end = current_month_start - timedelta(days=1)
        previous_month_start = previous_month_end.replace(day=1)
        return previous_month_start, previous_month_end

    @staticmethod
    def _last_year_window(today_local: date) -> tuple[date, date]:
        previous_year = today_local.year - 1
        return date(previous_year, 1, 1), date(previous_year, 12, 31)

    @staticmethod
    def _last_year_anniversary_date(today_local: date) -> date:
        previous_year = today_local.year - 1
        previous_year_month_days = calendar.monthrange(
            previous_year, today_local.month
        )[1]
        return date(
            previous_year,
            today_local.month,
            min(today_local.day, previous_year_month_days),
        )

    @staticmethod
    def _last_week_window(today_local: date) -> tuple[date, date]:
        week_start = today_local - timedelta(days=7)
        week_end = today_local - timedelta(days=1)
        return week_start, week_end

    def _apply_memories_filter(
        self,
        statement: Any,
        *,
        memories_filter: MemoriesFilter,
        today_local: date,
    ) -> Any:
        if memories_filter == MemoriesFilter.last_years:
            return (
                statement.where(
                    extract("month", col(Moment.logged_date_tz)) == today_local.month
                )
                .where(extract("day", col(Moment.logged_date_tz)) == today_local.day)
                .where(extract("year", col(Moment.logged_date_tz)) < today_local.year)
            )
        if memories_filter == MemoriesFilter.last_year:
            previous_year_start, previous_year_end = self._last_year_window(today_local)
            return statement.where(
                col(Moment.logged_date_tz) >= previous_year_start
            ).where(col(Moment.logged_date_tz) <= previous_year_end)
        if memories_filter == MemoriesFilter.last_month:
            previous_month_start, previous_month_end = self._last_month_window(
                today_local
            )
            return statement.where(
                col(Moment.logged_date_tz) >= previous_month_start
            ).where(col(Moment.logged_date_tz) <= previous_month_end)

        week_start, week_end = self._last_week_window(today_local)
        return statement.where(col(Moment.logged_date_tz) >= week_start).where(
            col(Moment.logged_date_tz) <= week_end
        )

    def _base_memories_probe_statement(self, user_id: uuid.UUID) -> Any:
        return (
            select(Moment.id)
            .where(Moment.user_id == user_id)
            .outerjoin(Entry, col(Entry.moment_id) == col(Moment.id))
            .where((col(Entry.id).is_(None)) | (col(Entry.is_draft).is_(False)))
        )

    def _fetch_memories(
        self,
        user_id: uuid.UUID,
        *,
        today_local: date,
        memories_filter: MemoriesFilter,
        limit: int,
    ) -> List[Moment]:
        statement = (
            self._apply_memories_filter(
                self._base_moment_statement(user_id),
                memories_filter=memories_filter,
                today_local=today_local,
            )
            .order_by(
                col(Moment.logged_date_tz).desc(),
                col(Moment.logged_at_utc).desc(),
                col(Moment.id).desc(),
            )
            .limit(limit)
        )
        return list(self.session.exec(statement))

    def _fetch_last_year_auto_memories(
        self,
        user_id: uuid.UUID,
        *,
        today_local: date,
        limit: int,
    ) -> List[Moment]:
        target_date = self._last_year_anniversary_date(today_local)
        statement = self._apply_memories_filter(
            self._base_moment_statement(user_id),
            memories_filter=MemoriesFilter.last_year,
            today_local=today_local,
        )
        memories = list(self.session.exec(statement))
        memories.sort(
            key=lambda moment: (
                abs((moment.logged_date_tz - target_date).days),
                -moment.logged_date_tz.toordinal(),
                -ensure_utc(moment.logged_at_utc).timestamp(),
                str(moment.id),
            )
        )
        return memories[:limit]

    def _has_memories(
        self,
        user_id: uuid.UUID,
        *,
        today_local: date,
        memories_filter: MemoriesFilter,
    ) -> bool:
        probe_statement = self._apply_memories_filter(
            self._base_memories_probe_statement(user_id),
            memories_filter=memories_filter,
            today_local=today_local,
        )
        return self.session.exec(probe_statement.limit(1)).first() is not None

    def get_memories(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 10,
        memories_filter: MemoriesFilter = MemoriesFilter.auto,
    ) -> Tuple[List[Moment], MemoriesAppliedFilter]:
        today_local = self._resolve_user_local_today(user_id)

        if memories_filter != MemoriesFilter.auto:
            return (
                self._fetch_memories(
                    user_id,
                    today_local=today_local,
                    memories_filter=memories_filter,
                    limit=limit,
                ),
                self._to_applied_filter(memories_filter),
            )

        # Auto fallback: exact anniversaries -> sliding recent history -> nearby dates in
        # the previous year -> broader previous-month history.
        auto_candidates: List[Tuple[MemoriesFilter, int]] = [
            (MemoriesFilter.last_years, limit),
            (MemoriesFilter.last_week, limit),
        ]
        for candidate, candidate_limit in auto_candidates:
            if self._has_memories(
                user_id,
                today_local=today_local,
                memories_filter=candidate,
            ):
                return (
                    self._fetch_memories(
                        user_id,
                        today_local=today_local,
                        memories_filter=candidate,
                        limit=candidate_limit,
                    ),
                    self._to_applied_filter(candidate),
                )

        last_year_limit = min(limit, 3)
        if self._has_memories(
            user_id,
            today_local=today_local,
            memories_filter=MemoriesFilter.last_year,
        ):
            return (
                self._fetch_last_year_auto_memories(
                    user_id,
                    today_local=today_local,
                    limit=last_year_limit,
                ),
                MemoriesAppliedFilter.last_year,
            )

        if self._has_memories(
            user_id,
            today_local=today_local,
            memories_filter=MemoriesFilter.last_month,
        ):
            return (
                self._fetch_memories(
                    user_id,
                    today_local=today_local,
                    memories_filter=MemoriesFilter.last_month,
                    limit=limit,
                ),
                MemoriesAppliedFilter.last_month,
            )

        return [], MemoriesAppliedFilter.last_week

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
        cursor_logged_at_utc: Optional[datetime] = None,
        cursor_id: Optional[uuid.UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        journal_id: Optional[uuid.UUID] = None,
        mood_ids: Optional[List[uuid.UUID]] = None,
        person_ids: Optional[List[uuid.UUID]] = None,
        people_match: PeopleMatch = PeopleMatch.any,
        tag_ids: Optional[List[uuid.UUID]] = None,
        activity_ids: Optional[List[uuid.UUID]] = None,
        goal_id: Optional[uuid.UUID] = None,
        search: Optional[str] = None,
        include_drafts: bool = False,
        include_empty: bool = False,
    ) -> Tuple[List[Moment], Optional[datetime], Optional[uuid.UUID]]:
        """Get moments for a user with filtering."""
        statement = (
            select(Moment)
            .where(Moment.user_id == user_id)
            .options(
                selectinload(Moment.entry),  # type: ignore[arg-type]
                selectinload(Moment.tags),  # type: ignore[arg-type]
                selectinload(Moment.people),  # type: ignore[arg-type]
                selectinload(Moment.mood_activity_links).selectinload(  # type: ignore[arg-type]
                    MomentMoodActivity.mood  # type: ignore[arg-type]
                ),
                selectinload(Moment.mood_activity_links).selectinload(  # type: ignore[arg-type]
                    MomentMoodActivity.activity  # type: ignore[arg-type]
                ),
            )
        )

        statement = self._apply_journal_join(statement, journal_id)
        statement = self._apply_draft_filter(statement, include_drafts, None)
        statement = self._apply_mood_filter(statement, mood_ids)
        statement = self._apply_people_filter(statement, person_ids, people_match)
        statement = self._apply_tag_filter(statement, tag_ids)
        statement = self._apply_activity_filter(statement, activity_ids)
        statement = self._apply_goal_filter(statement, goal_id)
        statement = self._apply_search_filter(statement, search)
        statement = self._apply_cursor_filter(
            statement, cursor_logged_at_utc, cursor_id
        )
        statement = self._apply_date_filter(statement, start_date, end_date)
        statement = self._apply_non_empty_filter(statement, include_empty)

        statement = statement.order_by(
            col(Moment.logged_at_utc).desc(),
            col(Moment.id).desc(),
        )
        statement = statement.limit(limit + 1)

        rows = list(self.session.exec(statement))
        next_cursor_logged_at_utc = None
        next_cursor_id = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor_logged_at_utc = last.logged_at_utc
            next_cursor_id = last.id
            rows = rows[:limit]
        return rows, next_cursor_logged_at_utc, next_cursor_id

    def get_calendar_summary(
        self,
        user_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        journal_id: Optional[uuid.UUID] = None,
    ) -> List[Moment]:
        statement = select(Moment).where(Moment.user_id == user_id)
        if journal_id:
            statement = statement.join(
                Entry, col(Entry.moment_id) == col(Moment.id)
            ).where(
                col(Entry.journal_id) == journal_id
            )
        if start_date:
            statement = statement.where(col(Moment.logged_date_tz) >= start_date)
        if end_date:
            statement = statement.where(col(Moment.logged_date_tz) <= end_date)
        statement = statement.order_by(
            col(Moment.logged_date_tz).desc(),
            col(Moment.logged_at_utc).desc(),
        )
        return list(self.session.exec(statement))

    def delete_moment(self, moment_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
        """
        Hard delete a moment and all related data (entry, media, mood/activity links).
        Identifies and cleans up physical media records post-commit to avoid dangling references.

        Returns a result dict: {"deleted": True, "cleanup_failures": count, "errors": list}.
        Cleanup failures are logged and can be retried by a background cleanup job.
        """
        moment = self._get_owned_moment(user_id, moment_id)

        from app.models.moment import MomentMedia
        from app.services.media_service import MediaService

        media_service = MediaService(self.session)

        # 1. Collect all media metadata BEFORE DB deletion (cascades will remove them from DB)
        media_items = self.session.exec(
            select(MomentMedia).where(MomentMedia.moment_id == moment_id)
        ).all()

        media_files_to_clean = []
        immich_assets = []
        for media in media_items:
            force = media.checksum is None
            file_info = media_service._build_file_deletion_info(media, force=force)
            if file_info:
                media_files_to_clean.append(file_info)

            if media_service._should_remove_immich_asset(self.session, media, user_id):
                immich_assets.append(media.external_asset_id)

        # 2. Delete the Moment record (and linked Entry/Media via DB cascade)
        # Note: We delete the moment itself; the database handles CASCADE to entry and moment_media.
        self.session.delete(moment)
        self._commit()
        log_info(f"Moment DB record deleted for user {user_id}: {moment_id}")

        # 3. Queue physical/remote media cleanup as background task.
        cleaned_assets = [asset_id for asset_id in immich_assets if asset_id]
        try:
            from app.core.celery_app import celery_app

            celery_app.send_task(
                "app.tasks.media.cleanup_moment_media_files",
                args=[str(user_id), media_files_to_clean, cleaned_assets],
            )
            return {
                "deleted": True,
                "cleanup_queued": True,
                "cleanup_failures": 0,
                "errors": [],
            }
        except Exception as exc:
            # Fallback to synchronous cleanup to avoid leaving orphaned files if task dispatch fails.
            log_warning(
                f"Failed to enqueue moment media cleanup task; running sync fallback: {exc}"
            )
            deletion_errors = []
            try:
                media_service.delete_media_files_post_commit(
                    user_id,
                    media_files_to_clean,
                    cleaned_assets,
                )
            except Exception as sync_exc:
                log_error(
                    sync_exc,
                    message="Failed synchronous media cleanup after moment deletion",
                )
                deletion_errors.append(sync_exc)

            if deletion_errors:
                error_summaries = [str(e) for e in deletion_errors]
                log_error(
                    Exception(
                        "Failed to delete orphaned media files after moment deletion"
                    ),
                    message=f"Failed to delete {len(deletion_errors)} orphaned media files after moment deletion",
                    moment_id=str(moment_id),
                    error_count=len(deletion_errors),
                    errors=error_summaries,
                )
                return {
                    "deleted": True,
                    "cleanup_queued": False,
                    "cleanup_failures": len(deletion_errors),
                    "errors": [
                        f"Physical cleanup failed for {len(deletion_errors)} files"
                    ],
                }

            return {
                "deleted": True,
                "cleanup_queued": False,
                "cleanup_failures": 0,
                "errors": [],
            }
