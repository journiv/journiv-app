"""
Analytics service for managing analytics data.
"""
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, cast

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, func, select

from app.core.logging_config import log_error, log_info
from app.core.time_utils import utc_now
from app.models.analytics import WritingStreak
from app.models.entry import Entry
from app.models.journal import Journal
from app.models.moment import Moment
from app.models.moment_tag_link import MomentTagLink
from app.models.tag import Tag


class AnalyticsService:
    """Service class for analytics operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_writing_streak(self, user_id: uuid.UUID) -> Optional[WritingStreak]:
        """Get writing streak for a user."""
        statement = select(WritingStreak).where(
            WritingStreak.user_id == user_id,
        )
        return self.session.exec(statement).first()

    def create_writing_streak(self, user_id: uuid.UUID) -> WritingStreak:
        """Create a new writing streak record for a user."""
        streak = WritingStreak(user_id=user_id)
        try:
            self.session.add(streak)
            self.session.commit()
            self.session.refresh(streak)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Writing streak created for user {user_id}")
        return streak

    def update_writing_streak(self, user_id: uuid.UUID, entry_date: date) -> WritingStreak:
        """Update writing streak when a new entry is created.

        Note: If the entry is backdated (earlier than last_entry_date),
        we recalculate the entire streak to ensure accuracy.
        """
        if isinstance(entry_date, str):
            entry_date = date.fromisoformat(entry_date[:10])
        elif isinstance(entry_date, datetime):
            entry_date = entry_date.date()

        streak = self.get_writing_streak(user_id)
        if not streak:
            streak = self.create_writing_streak(user_id)

        # If backdated entry, recalculate everything from scratch
        if streak.last_entry_date and entry_date < streak.last_entry_date:
            log_info(f"Backdated entry detected for user {user_id}: {entry_date} < {streak.last_entry_date}. Recalculating streak.")
            # Flush the session to ensure the entry is visible in queries
            self.session.flush()
            result = self.recalculate_writing_streak_stats(user_id)
            return result if result is not None else streak

        # Calculate if this is a consecutive day (only for forward-dated or same-day entries)
        if streak.last_entry_date:
            days_diff = (entry_date - streak.last_entry_date).days
            if days_diff == 1:
                # Consecutive day - increment streak
                streak.current_streak += 1
                if streak.current_streak > streak.longest_streak:
                    streak.longest_streak = streak.current_streak
            elif days_diff > 1:
                # Gap in entries - reset streak
                streak.current_streak = 1
                streak.streak_start_date = entry_date
                # Update longest streak if needed
                if streak.current_streak > streak.longest_streak:
                    streak.longest_streak = streak.current_streak
            # If days_diff == 0, it's the same day, don't change streak
        else:
            # First entry
            streak.current_streak = 1
            streak.streak_start_date = entry_date
            # Update longest streak if needed
            if streak.current_streak > streak.longest_streak:
                streak.longest_streak = streak.current_streak

        # Update last entry date (only if current or future date)
        streak.last_entry_date = entry_date

        # Update total entries and words
        self._update_entry_stats(user_id, streak)

        try:
            self.session.add(streak)
            self.session.commit()
            self.session.refresh(streak)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Writing streak updated for user {user_id}")
        return streak

    def recalculate_writing_streak_stats(self, user_id: uuid.UUID) -> Optional[WritingStreak]:
        """
        Recalculate writing streak statistics for a user.

        This should be called when entries are deleted to ensure the cached
        total_entries, total_words, and streak metadata values are accurate.

        Returns:
            WritingStreak object if it exists, None otherwise
        """
        streak = self.get_writing_streak(user_id)
        if not streak:
            return None

        self._update_entry_stats(user_id, streak)

        streaks = self._recalculate_streak_metadata(user_id)
        streak.current_streak = streaks['current_streak']
        streak.longest_streak = streaks['longest_streak']
        streak.last_entry_date = streaks['last_entry_date']
        streak.streak_start_date = streaks['streak_start_date']

        try:
            self.session.add(streak)
            self.session.commit()
            self.session.refresh(streak)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Writing streak stats recalculated for user {user_id}")
        return streak

    def _update_entry_stats(self, user_id: uuid.UUID, streak: WritingStreak):
        """Update total entries and words statistics."""
        result = self.session.exec(
            select(
                func.count(Entry.id).label("entry_count"),
                func.coalesce(func.sum(Entry.word_count), 0).label("total_words"),
            ).where(
                Entry.user_id == user_id,
                col(Entry.is_draft).is_(False),
            )
        ).first()

        if result is None:
            total_entries = 0
            total_words = 0
        elif isinstance(result, tuple):
            total_entries = int(result[0] or 0)
            total_words = int(result[1] or 0)
        else:
            total_entries = int(getattr(result, "entry_count", 0) or 0)
            total_words = int(getattr(result, "total_words", 0) or 0)

        streak.total_entries = total_entries
        streak.total_words = total_words
        streak.average_words_per_entry = total_words / total_entries if total_entries > 0 else 0.0

    def _recalculate_streak_metadata(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """
        Recalculate streak metadata from all user entries.

        Streaks are based on UNIQUE days that have at least one entry.
        Multiple entries on the same day count as one day for streak purposes.

        Returns:
            Dict with current_streak, longest_streak, last_entry_date, streak_start_date
        """
        # Expire all to ensure we get fresh data from the database
        self.session.expire_all()

        statement = (
            select(Entry)
            .join(Moment, col(Entry.moment_id) == col(Moment.id), isouter=True)
            .where(
                Entry.user_id == user_id,
                col(Entry.is_draft).is_(False),
            )
            .order_by(col(Entry.created_at).desc())
            .options(joinedload(cast(Any, Entry.moment)))
        )
        entries = self.session.exec(statement).all()

        unique_dates = sorted(
            {
                logged_date
                for entry in entries
                if (logged_date := self._entry_logged_date(entry)) is not None
            },
            reverse=True,
        )

        if not unique_dates:
            return {
                'current_streak': 0,
                'longest_streak': 0,
                'last_entry_date': None,
                'streak_start_date': None
            }

        last_entry_date = unique_dates[0]
        current_streak = 1
        streak_start_date = unique_dates[0]
        for i in range(1, len(unique_dates)):
            if (unique_dates[i - 1] - unique_dates[i]).days == 1:
                current_streak += 1
                streak_start_date = unique_dates[i]
            else:
                break

        # Calculate longest streak historically from all entries
        longest_streak = 1
        current_longest = 1
        for i in range(1, len(unique_dates)):
            if (unique_dates[i - 1] - unique_dates[i]).days == 1:
                current_longest += 1
                longest_streak = max(longest_streak, current_longest)
            else:
                current_longest = 1

        return {
            'current_streak': current_streak,
            'longest_streak': longest_streak,
            'last_entry_date': last_entry_date,
            'streak_start_date': streak_start_date
        }

    def get_writing_analytics(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """Get comprehensive writing analytics for a user."""
        streak = self.get_writing_streak(user_id)
        if not streak:
            return {
                'current_streak': 0,
                'longest_streak': 0,
                'total_entries': 0,
                'total_words': 0,
                'average_words_per_entry': 0.0,
                'last_entry_date': None,
                'streak_start_date': None
            }

        return {
            'current_streak': streak.current_streak,
            'longest_streak': streak.longest_streak,
            'total_entries': streak.total_entries,
            'total_words': streak.total_words,
            'average_words_per_entry': round(streak.average_words_per_entry, 2),
            'last_entry_date': streak.last_entry_date,
            'streak_start_date': streak.streak_start_date
        }

    def get_writing_patterns(self, user_id: uuid.UUID, days: int = 30) -> Dict[str, Any]:
        """Get writing patterns for the last N days."""
        end_date = utc_now().date()
        start_date = end_date - timedelta(days=days)

        entries = self.session.exec(
            select(Entry)
            .join(Moment, col(Entry.moment_id) == col(Moment.id), isouter=True)
            .where(
                Entry.user_id == user_id,
                col(Entry.is_draft).is_(False),
            )
            .options(joinedload(cast(Any, Entry.moment)))
        ).all()
        entries_by_day_map: Dict[date, Dict[str, int]] = {}
        for entry in entries:
            logged_date = self._entry_logged_date(entry)
            if logged_date is None or logged_date < start_date or logged_date > end_date:
                continue
            bucket = entries_by_day_map.setdefault(
                logged_date,
                {"entry_count": 0, "total_words": 0},
            )
            bucket["entry_count"] += 1
            bucket["total_words"] += int(entry.word_count or 0)

        entries_by_day = [
            {
                "logged_date_tz": logged_date,
                "entry_count": stats["entry_count"],
                "total_words": stats["total_words"],
            }
            for logged_date, stats in sorted(entries_by_day_map.items())
        ]

        # Get mood patterns (primary mood per moment)
        mood_patterns = self.session.exec(
            select(
                col(Moment.logged_date_tz).label('mood_date'),
                func.count(Moment.id).label('mood_count')
            )
            .where(
                Moment.user_id == user_id,
                col(Moment.primary_mood_id).is_not(None),
                col(Moment.logged_date_tz) >= start_date,
                col(Moment.logged_date_tz) <= end_date
            )
            .group_by(col(Moment.logged_date_tz))
            .order_by(col(Moment.logged_date_tz))
        ).all()

        # Get tag usage (tags are now on moments via MomentTagLink)
        tag_usage = self.session.exec(
            select(
                Tag.name,
                func.count(MomentTagLink.moment_id).label('usage_count')
            )
            .join(MomentTagLink, Tag.id == MomentTagLink.tag_id)
            .join(Moment, MomentTagLink.moment_id == Moment.id)
            .where(
                Tag.user_id == user_id,
                Moment.user_id == user_id,
                col(Moment.logged_date_tz) >= start_date,
                col(Moment.logged_date_tz) <= end_date,
            )
            .group_by(Tag.name)
            .order_by(func.count(MomentTagLink.moment_id).desc())
            .limit(10)
        ).all()

        normalized_mood_patterns = []
        for row in mood_patterns:
            mood_date = self._row_value(row, 0, "mood_date")
            mood_count = self._row_value(row, 1, "mood_count") or 0
            normalized_mood_patterns.append(
                {
                    "date": str(self._coerce_date(mood_date)),
                    "mood_count": int(mood_count),
                }
            )

        normalized_tag_usage = []
        for row in tag_usage:
            tag_name = self._row_value(row, 0, "name")
            usage_count = self._row_value(row, 1, "usage_count") or 0
            normalized_tag_usage.append(
                {
                    "tag_name": tag_name,
                    "usage_count": int(usage_count),
                }
            )

        return {
            'period_days': days,
            'entries_by_day': [
                {
                    'date': str(day["logged_date_tz"]),
                    'entry_count': day["entry_count"],
                    'total_words': day["total_words"] or 0
                }
                for day in entries_by_day
            ],
            'mood_patterns': normalized_mood_patterns,
            'top_tags': normalized_tag_usage,
        }

    def get_productivity_metrics(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """Get productivity metrics for a user."""
        now = utc_now()
        today = now.date()
        month_start = today.replace(day=1)

        # Get last month stats for comparison
        last_month_end = month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        entries = self.session.exec(
            select(Entry)
            .join(Moment, col(Entry.moment_id) == col(Moment.id), isouter=True)
            .where(
                Entry.user_id == user_id,
                col(Entry.is_draft).is_(False),
            )
            .options(joinedload(cast(Any, Entry.moment)))
        ).all()

        current_month_entries = 0
        current_month_words = 0
        last_month_entries = 0
        for entry in entries:
            logged_date = self._entry_logged_date(entry)
            if logged_date is None:
                continue
            if logged_date >= month_start:
                current_month_entries += 1
                current_month_words += int(entry.word_count or 0)
            elif last_month_start <= logged_date < month_start:
                last_month_entries += 1

        # Calculate growth
        entry_growth = 0
        if last_month_entries and last_month_entries > 0:
            entry_growth = ((current_month_entries - last_month_entries) / last_month_entries) * 100

        today_day = today.day
        return {
            'current_month_entries': current_month_entries,
            'current_month_words': current_month_words,
            'entry_growth_percentage': round(entry_growth, 2),
            'average_daily_entries': round(current_month_entries / today_day, 2),
            'average_words_per_day': round(current_month_words / today_day, 2)
        }

    def _entry_logged_date(self, entry: Entry) -> Optional[date]:
        """Resolve the canonical analytics date for an entry."""
        if entry.moment is not None and entry.moment.logged_date_tz is not None:
            return self._coerce_date(entry.moment.logged_date_tz)
        if entry.created_at is not None:
            return entry.created_at.date()
        return None

    @staticmethod
    def _coerce_date(value: Any) -> Optional[date]:
        """Normalize DB values (date/datetime/iso-string) into date."""
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None

    @staticmethod
    def _row_value(row: Any, index: int, key: str) -> Any:
        """Extract values from tuple/Row/mapping objects across DB backends."""
        if isinstance(row, tuple):
            return row[index]
        mapping = getattr(row, "_mapping", None)
        if mapping is not None and key in mapping:
            return mapping[key]
        if isinstance(row, dict):
            return row.get(key)
        return getattr(row, key, None)

    def get_journal_analytics(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """Get analytics for all journals of a user."""
        # Get journal stats (last_entry timestamp from Moment.logged_at_utc)
        journal_stats = self.session.exec(
            select(  # type: ignore[no-matching-overload]
                Journal.id,
                Journal.title,
                func.count(Entry.id).label('entry_count'),
                func.sum(Entry.word_count).label('total_words'),
                func.max(Moment.logged_at_utc).label('last_entry')
            )
            .outerjoin(
                Entry,
                (col(Journal.id) == col(Entry.journal_id)) & (col(Entry.is_draft).is_(False))
            )
            .outerjoin(
                Moment,
                col(Entry.moment_id) == col(Moment.id)
            )
            .where(
                Journal.user_id == user_id,
            )
            .group_by(Journal.id, Journal.title)
            .order_by(func.count(Entry.id).desc())
        ).all()

        journals: list[Dict[str, Any]] = []
        for row in journal_stats:
            journal_id = self._row_value(row, 0, "id")
            title = self._row_value(row, 1, "title")
            entry_count = self._row_value(row, 2, "entry_count") or 0
            total_words = self._row_value(row, 3, "total_words") or 0
            last_entry = self._row_value(row, 4, "last_entry")
            journals.append(
                {
                    "journal_id": str(journal_id),
                    "title": title,
                    "entry_count": int(entry_count),
                    "total_words": int(total_words),
                    "last_entry": last_entry,
                }
            )

        return {"journals": journals}
