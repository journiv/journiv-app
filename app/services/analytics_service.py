"""
Analytics service for managing analytics data.
"""
import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select, func

from app.core.logging_config import log_info, log_error
from app.models.analytics import WritingStreak
from app.core.time_utils import utc_now
from app.models.entry import Entry
from app.models.journal import Journal
from app.models.mood import MoodLog
from app.models.tag import Tag, EntryTagLink


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
        """Update writing streak when a new entry is created."""
        streak = self.get_writing_streak(user_id)
        if not streak:
            streak = self.create_writing_streak(user_id)

        # Calculate if this is a consecutive day
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

        # Update last entry date
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
        entries = self.session.exec(
            select(Entry).where(Entry.user_id == user_id).order_by(Entry.entry_date.desc())
        ).all()

        unique_dates = sorted(
            {e.entry_date for e in entries if e.entry_date is not None},
            reverse=True
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
            days_diff = (unique_dates[i - 1] - unique_dates[i]).days
            if days_diff == 1:
                current_streak += 1
                streak_start_date = unique_dates[i]
            else:
                break

        longest_streak = 1
        current_longest = 1
        for i in range(1, len(unique_dates)):
            days_diff = (unique_dates[i - 1] - unique_dates[i]).days
            if days_diff == 1:
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

        # Get entries by day
        entries_by_day = self.session.exec(
            select(
                Entry.entry_date.label('entry_date'),
                func.count(Entry.id).label('entry_count'),
                func.sum(Entry.word_count).label('total_words')
            )
            .where(
                Entry.user_id == user_id,
                Entry.entry_date >= start_date,
                Entry.entry_date <= end_date
            )
            .group_by(Entry.entry_date)
            .order_by(Entry.entry_date)
        ).all()

        # Get mood patterns
        mood_patterns = self.session.exec(
            select(
                MoodLog.logged_date.label('mood_date'),
                func.count(MoodLog.id).label('mood_count')
            )
            .where(
                MoodLog.user_id == user_id,
                MoodLog.logged_date >= start_date,
                MoodLog.logged_date <= end_date
            )
            .group_by(MoodLog.logged_date)
            .order_by(MoodLog.logged_date)
        ).all()

        # Get tag usage
        tag_usage = self.session.exec(
            select(
                Tag.name,
                func.count(EntryTagLink.entry_id).label('usage_count')
            )
            .join(EntryTagLink, Tag.id == EntryTagLink.tag_id)
            .join(Entry, EntryTagLink.entry_id == Entry.id)
            .where(
                Tag.user_id == user_id,
                Entry.user_id == user_id,
                Entry.entry_date >= start_date,
                Entry.entry_date <= end_date
            )
            .group_by(Tag.name)
            .order_by(func.count(EntryTagLink.entry_id).desc())
            .limit(10)
        ).all()

        return {
            'period_days': days,
            'entries_by_day': [
                {
                    'date': str(day.entry_date),
                    'entry_count': day.entry_count,
                    'total_words': day.total_words or 0
                }
                for day in entries_by_day
            ],
            'mood_patterns': [
                {
                    'date': str(day.mood_date),
                    'mood_count': day.mood_count
                }
                for day in mood_patterns
            ],
            'top_tags': [
                {
                    'tag_name': tag.name,
                    'usage_count': tag.usage_count
                }
                for tag in tag_usage
            ]
        }

    def get_productivity_metrics(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """Get productivity metrics for a user."""
        now = utc_now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        current_month_entries = self.session.exec(
            select(func.count(Entry.id))
            .where(
                Entry.user_id == user_id,
                Entry.entry_datetime_utc >= month_start
            )
        ).first() or 0

        current_month_words = self.session.exec(
            select(func.coalesce(func.sum(Entry.word_count), 0))
            .where(
                Entry.user_id == user_id,
                Entry.entry_datetime_utc >= month_start
            )
        ).first() or 0

        # Get last month stats for comparison
        last_month_end = month_start - timedelta(seconds=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        last_month_entries = self.session.exec(
            select(func.count(Entry.id))
            .where(
                Entry.user_id == user_id,
                Entry.entry_datetime_utc >= last_month_start,
                Entry.entry_datetime_utc < month_start
            )
        ).first() or 0

        # Calculate growth
        entry_growth = 0
        if last_month_entries and last_month_entries > 0:
            entry_growth = ((current_month_entries - last_month_entries) / last_month_entries) * 100

        return {
            'current_month_entries': current_month_entries,
            'current_month_words': current_month_words,
            'entry_growth_percentage': round(entry_growth, 2),
            'average_daily_entries': round(current_month_entries / now.day, 2) if now.day > 0 else 0,
            'average_words_per_day': round(current_month_words / now.day, 2) if now.day > 0 else 0
        }

    def get_journal_analytics(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """Get analytics for all journals of a user."""
        # Get journal stats
        journal_stats = self.session.exec(
            select(
                Journal.id,
                Journal.title,
                func.count(Entry.id).label('entry_count'),
                func.sum(Entry.word_count).label('total_words'),
                func.max(Entry.entry_datetime_utc).label('last_entry')
            )
            .outerjoin(Entry, Journal.id == Entry.journal_id)
            .where(
                Journal.user_id == user_id,
            )
            .group_by(Journal.id, Journal.title)
            .order_by(func.count(Entry.id).desc())
        ).all()

        return {
            'journals': [
                {
                    'journal_id': str(journal.id),
                    'title': journal.title,
                    'entry_count': journal.entry_count,
                    'total_words': journal.total_words or 0,
                    'last_entry': journal.last_entry
                }
                for journal in journal_stats
            ]
        }
