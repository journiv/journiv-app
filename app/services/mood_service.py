"""
Mood service for handling mood-related operations.
"""
import threading
import uuid
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select, func

from app.core.exceptions import MoodNotFoundError, EntryNotFoundError
from app.core.logging_config import log_error
from app.core.time_utils import utc_now, local_date_for_user, ensure_utc, to_utc
from app.models.entry import Entry
from app.models.enums import MoodCategory
from app.models.mood import Mood, MoodLog
from app.schemas.mood import MoodLogCreate, MoodLogUpdate

DEFAULT_MOOD_PAGE_LIMIT = 50
MAX_MOOD_PAGE_LIMIT = 100


class MoodService:
    """Service class for mood operations."""

    _mood_cache: Dict[str, List[Mood]] = {}
    _cache_lock = threading.RLock()

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _cache_key(category: Optional[str] = None) -> str:
        return category or "__all__"

    @classmethod
    def invalidate_mood_cache(cls) -> None:
        """Clear the mood cache. Thread-safe."""
        with cls._cache_lock:
            cls._mood_cache.clear()

    @classmethod
    def _store_cache(cls, key: str, moods: List[Mood]) -> None:
        """Store moods in cache. Thread-safe."""
        with cls._cache_lock:
            # Create copies to avoid session-related issues
            cls._mood_cache[key] = [
                Mood(
                    id=mood.id,
                    name=mood.name,
                    icon=mood.icon,
                    category=mood.category,
                    created_at=mood.created_at,
                    updated_at=mood.updated_at
                ) for mood in moods
            ]

    @classmethod
    def _get_cached_moods(cls, key: str) -> Optional[List[Mood]]:
        """Get moods from cache. Thread-safe."""
        with cls._cache_lock:
            cached = cls._mood_cache.get(key)
            if cached is None:
                return None
            # Return copies to avoid session-related issues
            return [
                Mood(
                    id=mood.id,
                    name=mood.name,
                    icon=mood.icon,
                    category=mood.category,
                    created_at=mood.created_at,
                    updated_at=mood.updated_at
                ) for mood in cached
            ]

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        if limit <= 0:
            return DEFAULT_MOOD_PAGE_LIMIT
        return min(limit, MAX_MOOD_PAGE_LIMIT)

    @staticmethod
    def _normalize_category(category: str) -> str:
        try:
            return MoodCategory(category.lower()).value
        except ValueError as exc:
            raise MoodNotFoundError(f"Invalid mood category '{category}'") from exc

    @staticmethod
    def _normalize_mood_name(mood_name: str) -> str:
        """Normalize mood name for lookup - handles case variations and common aliases."""
        if not mood_name:
            raise MoodNotFoundError("Mood name cannot be empty")

        # Normalize case and strip whitespace
        normalized = mood_name.strip().lower()

        # Handle common mood name variations/aliases
        mood_aliases = {
            'happy': ['joy', 'cheerful', 'glad', 'pleased'],
            'sad': ['unhappy', 'down', 'blue', 'melancholy'],
            'angry': ['mad', 'furious', 'irritated', 'annoyed'],
            'excited': ['thrilled', 'pumped', 'enthusiastic'],
            'calm': ['peaceful', 'serene', 'relaxed', 'tranquil'],
            'stressed': ['anxious', 'worried', 'overwhelmed'],
            'grateful': ['thankful', 'appreciative'],
            'focused': ['concentrated', 'attentive', 'mindful'],
            'tired': ['exhausted', 'sleepy', 'drained'],
            'lonely': ['isolated', 'alone', 'disconnected']
        }

        # Check if normalized name matches any alias
        for mood, aliases in mood_aliases.items():
            if normalized == mood or normalized in aliases:
                return mood

        return normalized

    def _commit(self) -> None:
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    def _normalize_log_timestamp(
        self,
        *,
        logged_date: Optional[date],
        logged_datetime_utc: Optional[datetime],
        logged_timezone: Optional[str],
        fallback_timezone: str
    ) -> tuple[datetime, str, date]:
        timezone_name = (logged_timezone or fallback_timezone or "UTC").strip() or "UTC"

        if logged_datetime_utc is not None:
            normalized_dt = ensure_utc(logged_datetime_utc)
        elif logged_date is not None:
            local_now = datetime.now(ZoneInfo(timezone_name))
            local_dt = datetime.combine(logged_date, local_now.time())
            normalized_dt = to_utc(local_dt, timezone_name)
        else:
            normalized_dt = utc_now()

        derived_date = local_date_for_user(normalized_dt, timezone_name)
        return normalized_dt, timezone_name, derived_date

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("UTC"))

    # Mood Management (System moods)
    def get_all_moods(self) -> List[Mood]:
        """Get all system moods."""
        cache_key = self._cache_key()
        cached = self._get_cached_moods(cache_key)
        if cached is not None:
            return cached

        statement = select(Mood).order_by(Mood.category, Mood.name)
        moods = list(self.session.exec(statement))
        self._store_cache(cache_key, moods)
        return moods

    def get_mood_by_id(self, mood_id: uuid.UUID) -> Optional[Mood]:
        """Get a mood by ID."""
        statement = select(Mood).where(Mood.id == mood_id)
        return self.session.exec(statement).first()

    def get_moods_by_category(self, category: str) -> List[Mood]:
        """Get moods by category."""
        normalized = self._normalize_category(category)
        cache_key = self._cache_key(normalized)
        cached = self._get_cached_moods(cache_key)
        if cached is not None:
            return cached

        statement = select(Mood).where(Mood.category == normalized).order_by(Mood.name)
        moods = list(self.session.exec(statement))
        self._store_cache(cache_key, moods)
        return moods

    def find_mood_by_name(self, mood_name: str) -> Optional[Mood]:
        """Find a mood by name with symbolic lookup support."""
        normalized_name = self._normalize_mood_name(mood_name)

        # First try exact match (case-insensitive)
        statement = select(Mood).where(func.lower(Mood.name) == normalized_name)
        mood = self.session.exec(statement).first()

        if mood:
            return mood

        # If no exact match, try partial match
        statement = select(Mood).where(func.lower(Mood.name).like(f"%{normalized_name}%"))
        moods = list(self.session.exec(statement))

        if len(moods) == 1:
            return moods[0]
        elif len(moods) > 1:
            # Multiple matches - return the first one or raise an error
            # Could be enhanced to return all matches
            return moods[0]

        return None


    # Mood Logging (User moods)
    def log_mood(self, user_id: uuid.UUID, mood_log_data: MoodLogCreate) -> MoodLog:
        """Log a mood for a user."""
        from app.services.user_service import UserService
        # Verify the mood exists
        mood = self.get_mood_by_id(mood_log_data.mood_id)
        if not mood:
            raise MoodNotFoundError("Mood not found")

        if mood_log_data.entry_id:
            entry = self.session.exec(
                select(Entry).where(
                    Entry.id == mood_log_data.entry_id,
                    Entry.user_id == user_id
                )
            ).first()
            if not entry:
                raise EntryNotFoundError("Entry not found")
            logged_datetime_utc = self._as_utc(entry.entry_datetime_utc)
            logged_timezone = entry.entry_timezone
            logged_date = entry.entry_date
        else:
            user_service = UserService(self.session)
            user_tz = user_service.get_user_timezone(user_id)
            logged_datetime_utc, logged_timezone, logged_date = self._normalize_log_timestamp(
                logged_date=None,
                logged_datetime_utc=mood_log_data.logged_datetime_utc,
                logged_timezone=mood_log_data.logged_timezone,
                fallback_timezone=user_tz
            )

        mood_log = MoodLog(
            user_id=user_id,
            mood_id=mood_log_data.mood_id,
            entry_id=mood_log_data.entry_id,
            note=mood_log_data.note,
            logged_date=logged_date,
            logged_datetime_utc=logged_datetime_utc,
            logged_timezone=logged_timezone
        )

        self.session.add(mood_log)
        self._commit()
        self.session.refresh(mood_log)
        return mood_log

    def get_user_mood_logs(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        mood_id: Optional[uuid.UUID] = None,
        entry_id: Optional[uuid.UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[MoodLog]:
        """Get mood logs for a user with optional filters."""
        statement = select(MoodLog).where(MoodLog.user_id == user_id)

        if mood_id:
            statement = statement.where(MoodLog.mood_id == mood_id)

        if entry_id:
            statement = statement.where(MoodLog.entry_id == entry_id)

        if start_date:
            statement = statement.where(MoodLog.logged_date >= start_date)

        if end_date:
            statement = statement.where(MoodLog.logged_date <= end_date)

        statement = statement.order_by(MoodLog.logged_datetime_utc.desc()).offset(offset).limit(self._normalize_limit(limit))
        return list(self.session.exec(statement))

    def get_mood_log_by_id(self, mood_log_id: uuid.UUID, user_id: uuid.UUID) -> Optional[MoodLog]:
        """Get a specific mood log by ID for a user."""
        statement = select(MoodLog).where(
            MoodLog.id == mood_log_id,
            MoodLog.user_id == user_id
        )
        return self.session.exec(statement).first()

    def update_mood_log(self, mood_log_id: uuid.UUID, user_id: uuid.UUID, mood_log_data: MoodLogUpdate) -> MoodLog:
        """Update a mood log."""
        mood_log = self.get_mood_log_by_id(mood_log_id, user_id)
        if not mood_log:
            raise MoodNotFoundError("Mood log not found")

        if mood_log_data.mood_id is not None:
            # Verify the new mood exists
            mood = self.get_mood_by_id(mood_log_data.mood_id)
            if not mood:
                raise MoodNotFoundError("Mood not found")
            mood_log.mood_id = mood_log_data.mood_id

        if mood_log_data.note is not None:
            mood_log.note = mood_log_data.note

        if mood_log_data.logged_timezone is not None:
            tz_value = (mood_log_data.logged_timezone or "UTC").strip() or "UTC"
            mood_log.logged_timezone = tz_value
        timestamp_changed = False

        if mood_log_data.logged_datetime_utc is not None:
            mood_log.logged_datetime_utc = ensure_utc(mood_log_data.logged_datetime_utc)
            timestamp_changed = True

        if timestamp_changed or mood_log_data.logged_timezone is not None:
            base_dt = self._as_utc(mood_log.logged_datetime_utc)
            mood_log.logged_date = local_date_for_user(base_dt, mood_log.logged_timezone)

        mood_log.updated_at = utc_now()
        self.session.add(mood_log)
        self._commit()
        self.session.refresh(mood_log)
        return mood_log

    def delete_mood_log(self, mood_log_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Delete a mood log."""
        mood_log = self.get_mood_log_by_id(mood_log_id, user_id)
        if not mood_log:
            raise MoodNotFoundError("Mood log not found")

        self.session.delete(mood_log)
        self._commit()
        return True

    def get_mood_statistics(
        self,
        user_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Get mood statistics for a user."""
        # Default to last 30 days if no date range provided
        if not end_date:
            end_date = utc_now().date()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Get mood counts
        mood_counts = list(self.session.exec(
            select(
                Mood.name,
                Mood.category,
                func.count(MoodLog.id).label('count')
            )
            .join(MoodLog, Mood.id == MoodLog.mood_id)
            .where(
                MoodLog.user_id == user_id,
                MoodLog.logged_date >= start_date,
                MoodLog.logged_date <= end_date
            )
            .group_by(Mood.id, Mood.name, Mood.category)
            .order_by(func.count(MoodLog.id).desc())
        ))

        # Get daily mood trends
        daily_moods = list(self.session.exec(
            select(
                MoodLog.logged_date.label('date'),
                Mood.category,
                func.count(MoodLog.id).label('count')
            )
            .join(Mood, Mood.id == MoodLog.mood_id)
            .where(
                MoodLog.user_id == user_id,
                MoodLog.logged_date >= start_date,
                MoodLog.logged_date <= end_date
            )
            .group_by(MoodLog.logged_date, Mood.category)
            .order_by(MoodLog.logged_date)
        ))

        # Get most frequent mood
        most_frequent = mood_counts[0] if mood_counts else None

        # Calculate mood distribution
        total_logs = sum(count.count for count in mood_counts)
        mood_distribution = {
            'positive': 0,
            'negative': 0,
            'neutral': 0
        }

        for mood_count in mood_counts:
            mood_distribution[mood_count.category] += mood_count.count

        # Convert to percentages
        if total_logs > 0:
            for category in mood_distribution:
                mood_distribution[category] = round(
                    (mood_distribution[category] / total_logs) * 100, 2
                )

        return {
            'total_logs': total_logs,
            'date_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'mood_distribution': mood_distribution,
            'most_frequent_mood': {
                'name': most_frequent.name,
                'category': most_frequent.category,
                'count': most_frequent.count
            } if most_frequent else None,
            'mood_counts': [
                {
                    'name': count.name,
                    'category': count.category,
                    'count': count.count,
                    'percentage': round((count.count / total_logs) * 100, 2) if total_logs > 0 else 0
                }
                for count in mood_counts
            ],
        'daily_trends': [
            {
                'date': trend.date,  # func.date() already returns a string
                'category': trend.category,
                'count': trend.count
            }
            for trend in daily_moods
        ]
        }

    def get_recent_moods(self, user_id: uuid.UUID, limit: int = 10) -> List[MoodLog]:
        """Get recent mood logs for a user."""
        statement = (
            select(MoodLog)
            .join(Mood, MoodLog.mood_id == Mood.id)
            .where(MoodLog.user_id == user_id)
            .order_by(MoodLog.logged_datetime_utc.desc())
            .limit(limit)
        )
        mood_logs = list(self.session.exec(statement))

        # Load the mood relationship for each mood log
        for mood_log in mood_logs:
            if not hasattr(mood_log, 'mood') or mood_log.mood is None:
                mood = self.get_mood_by_id(mood_log.mood_id)
                if mood:
                    mood_log.mood = mood

        return mood_logs

    def get_mood_streak(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """Get current mood logging streak for a user."""
        from app.services.user_service import UserService
        from app.core.time_utils import local_date_for_user

        # Get all mood log dates for the user
        mood_dates = list(self.session.exec(
            select(MoodLog.logged_date.label('date'))
            .where(MoodLog.user_id == user_id)
            .distinct()
            .order_by(MoodLog.logged_date.desc())
        ))

        if not mood_dates:
            return {'current_streak': 0, 'longest_streak': 0}

        # Calculate current streak
        current_streak = 0
        # Get today's date in user's timezone
        user_service = UserService(self.session)
        user_tz = user_service.get_user_timezone(user_id)
        today = local_date_for_user(utc_now(), user_tz)
        yesterday = today - timedelta(days=1)

        # Check if user logged mood today or yesterday
        # mood_dates now contains date objects directly from logged_date field
        latest_date = mood_dates[0]
        if latest_date == today or latest_date == yesterday:
            current_streak = 1
            for i in range(1, len(mood_dates)):
                expected_date = today - timedelta(days=i)
                mood_date = mood_dates[i]
                if mood_date == expected_date:
                    current_streak += 1
                else:
                    break

        # Calculate longest streak
        longest_streak = 1
        temp_streak = 1
        for i in range(1, len(mood_dates)):
            current_date = mood_dates[i]
            previous_date = mood_dates[i-1]
            if (previous_date - current_date).days == 1:
                temp_streak += 1
                longest_streak = max(longest_streak, temp_streak)
            else:
                temp_streak = 1

        return {
            'current_streak': current_streak,
            'longest_streak': longest_streak,
            'total_days_logged': len(mood_dates)
        }

    # Bulk Operations
    def bulk_update_mood_logs(
        self,
        user_id: uuid.UUID,
        updates: List[Dict[str, Any]]
    ) -> List[MoodLog]:
        """Bulk update multiple mood logs for a user."""
        if not updates:
            return []

        # Validate all mood log IDs belong to the user
        mood_log_ids = [update.get('id') for update in updates if 'id' in update]
        if mood_log_ids:
            existing_logs = self.session.exec(
                select(MoodLog).where(
                    MoodLog.id.in_(mood_log_ids),
                    MoodLog.user_id == user_id
                )
            )

            if len(existing_logs) != len(mood_log_ids):
                raise MoodNotFoundError("One or more mood logs not found")

        updated_logs = []
        for update_data in updates:
            mood_log_id = update_data.get('id')
            if not mood_log_id:
                continue

            mood_log = self.get_mood_log_by_id(mood_log_id, user_id)
            if not mood_log:
                continue

            # Update fields
            if 'mood_id' in update_data:
                mood = self.get_mood_by_id(update_data['mood_id'])
                if not mood:
                    raise MoodNotFoundError("Mood not found")
                mood_log.mood_id = update_data['mood_id']

            if 'note' in update_data:
                mood_log.note = update_data['note']

            mood_log.updated_at = utc_now()
            self.session.add(mood_log)
            updated_logs.append(mood_log)

        self._commit()
        return updated_logs

    def bulk_delete_mood_logs(self, user_id: uuid.UUID, mood_log_ids: List[uuid.UUID]) -> int:
        """Bulk delete mood logs for a user."""
        if not mood_log_ids:
            return 0

        # Verify all logs belong to user
        existing_logs = self.session.exec(
            select(MoodLog).where(
                MoodLog.id.in_(mood_log_ids),
                MoodLog.user_id == user_id
            )
        )

        if len(existing_logs) != len(mood_log_ids):
            raise MoodNotFoundError("One or more mood logs not found")

        # Delete all logs
        for mood_log in existing_logs:
            self.session.delete(mood_log)

        self._commit()
        return len(existing_logs)
