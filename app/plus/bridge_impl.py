"""
Journiv implementation of the Plus Host Bridge.

This module provides the concrete implementation of the IHostBridge protocol,
allowing Plus features to access data from the Journiv backend while maintaining
strict privacy controls and separation of concerns.

PRIVACY: All operations are automatically scoped to a user_id.
All SQL queries MUST filter by user_id to ensure Plus features cannot access
other users' data.

PERFORMANCE: Sorting and aggregation happen at the SQL level for efficiency.
"""
import logging
from datetime import date
from typing import List, Optional
from uuid import UUID

from sqlmodel import Session, col, func, select

from app.core.config import settings
from app.core.logging_config import LogCategory
from app.models.entry import Entry
from app.models.tag import EntryTagLink, Tag
from app.plus.bridge_exceptions import BridgeDataError
from app.plus.contract import (
    MonthlyUsageRecord,
    TagUsageRecord,
    TagUsageTimeframe,
)

logger = logging.getLogger(LogCategory.PLUS)


class JournivBridge:
    """
    Concrete implementation of IHostBridge for Journiv backend.

    This bridge provides Plus features with controlled access to user data
    while enforcing privacy boundaries and maintaining database abstraction.

    All operations are automatically scoped to a specific user for privacy.
    """

    def __init__(self, db: Session, user_id: UUID):
        """
        Initialize bridge for a specific user session.

        Args:
            db: SQLModel database session
            user_id: User UUID - all operations are scoped to this user
        """
        self.db = db
        self.user_id = user_id
        logger.debug(f"JournivBridge initialized for user_id={user_id}")

    def fetch_tags_with_usage(self) -> List[TagUsageRecord]:
        """
        Fetch all tags with usage counts for the authenticated user.

        Returns:
            List[TagUsageRecord]: Tags sorted by usage_count DESC, name ASC

        Raises:
            BridgeDataError: If database query fails
        """
        try:
            # SQL-level sorting (much faster than Python sorting)
            statement = select(
                Tag.id, Tag.name, Tag.usage_count, Tag.created_at
            ).where(
                Tag.user_id == self.user_id  # Privacy: user-scoped
            ).order_by(
                col(Tag.usage_count).desc(),  # Primary sort: usage
                col(Tag.name).asc()            # Secondary sort: name
            )

            rows = self.db.exec(statement).all()

            # Build typed dictionaries
            # Row order: Tag.id, Tag.name, Tag.usage_count, Tag.created_at
            result: List[TagUsageRecord] = [
                {
                    "id": str(row[0]),  # Tag.id
                    "name": row[1],  # Tag.name
                    "usage_count": row[2],  # Tag.usage_count
                    "created_at": row[3].isoformat() if row[3] else ""  # Tag.created_at
                }
                for row in rows
            ]

            logger.debug(
                f"fetch_tags_with_usage: Fetched {len(result)} tags for user {self.user_id}"
            )
            return result

        except Exception as e:
            logger.error(
                f"Error fetching tags with usage for user {self.user_id}: {e}",
                exc_info=True
            )
            raise BridgeDataError(f"Failed to fetch tags: {e}") from e

    def fetch_tag_monthly_usage(
        self,
        tag_id: Optional[str] = None,
        start_date: Optional[str] = None
    ) -> List[MonthlyUsageRecord]:
        """
        Fetch monthly tag usage data.

        Args:
            tag_id: Optional tag UUID string (all tags if None)
            start_date: Optional ISO date string to filter from

        Returns:
            List[MonthlyUsageRecord]: Unsorted monthly usage data

        Raises:
            BridgeDataError: If database query fails
        """
        try:
            # Database-specific month formatting (SQL-level operation)
            if settings.database_type == 'postgres':
                month_expr = func.to_char(Entry.entry_date, 'YYYY-MM')
            else:
                month_expr = func.strftime('%Y-%m', Entry.entry_date)

            # Build query with user_id scoping (privacy)
            statement = select(
                month_expr.label('month_key'),
                func.count().label('count')
            ).select_from(
                EntryTagLink
            ).join(
                Entry, Entry.id == EntryTagLink.entry_id
            ).join(
                Tag, Tag.id == EntryTagLink.tag_id
            ).where(
                Tag.user_id == self.user_id,
                Entry.user_id == self.user_id,
                col(Entry.is_draft).is_(False)
            )

            # Apply optional filters
            if tag_id:
                statement = statement.where(EntryTagLink.tag_id == UUID(tag_id))

            if start_date:
                parsed_date = date.fromisoformat(start_date)
                statement = statement.where(Entry.entry_date >= parsed_date)

            # SQL-level aggregation
            statement = statement.group_by(month_expr)

            # Execute
            rows = self.db.exec(statement).all()

            # Build typed dictionaries
            result: List[MonthlyUsageRecord] = [
                {
                    "month_key": row.month_key,
                    "count": row.count
                }
                for row in rows
            ]

            logger.debug(
                f"fetch_tag_monthly_usage: Fetched {len(result)} months "
                f"for user {self.user_id}, tag_id={tag_id}, start_date={start_date}"
            )
            return result

        except Exception as e:
            logger.error(
                f"Error fetching monthly usage for user {self.user_id}: {e}",
                exc_info=True
            )
            raise BridgeDataError(f"Failed to fetch monthly usage: {e}") from e

    def fetch_tag_usage_timeframe(self, tag_id: str) -> TagUsageTimeframe:
        """
        Fetch first and last usage timestamps for a tag.

        Args:
            tag_id: Tag UUID as string

        Returns:
            TagUsageTimeframe: First and last usage timestamps (may be None)

        Raises:
            BridgeDataError: If tag not found or query fails
        """
        try:
            tag_uuid = UUID(tag_id)

            # SQL-level MIN/MAX aggregation (fast)
            # First used
            first_query = select(
                func.min(Entry.entry_datetime_utc)
            ).select_from(
                EntryTagLink
            ).join(
                Entry, Entry.id == EntryTagLink.entry_id
            ).where(
                EntryTagLink.tag_id == tag_uuid,
                Entry.user_id == self.user_id,      # Privacy: user-scoped
                col(Entry.is_draft).is_(False)
            )
            first_used = self.db.exec(first_query).first()

            # Last used
            last_query = select(
                func.max(Entry.entry_datetime_utc)
            ).select_from(
                EntryTagLink
            ).join(
                Entry, Entry.id == EntryTagLink.entry_id
            ).where(
                EntryTagLink.tag_id == tag_uuid,
                Entry.user_id == self.user_id,      # Privacy: user-scoped
                col(Entry.is_draft).is_(False)
            )
            last_used = self.db.exec(last_query).first()

            # Build typed dictionary
            result: TagUsageTimeframe = {
                "first_used": first_used.isoformat() if first_used else None,
                "last_used": last_used.isoformat() if last_used else None
            }

            logger.debug(
                f"fetch_tag_usage_timeframe: tag_id={tag_id}, "
                f"first={result['first_used']}, last={result['last_used']}"
            )
            return result

        except Exception as e:
            logger.error(
                f"Error fetching usage timeframe for tag {tag_id}, user {self.user_id}: {e}",
                exc_info=True
            )
            raise BridgeDataError(f"Failed to fetch usage timeframe: {e}") from e

    def log_event(self, level: str, message: str) -> None:
        """
        Log an event from Plus features.

        Args:
            level: Log level string
            message: Log message
        """
        log_level = getattr(logging, level.upper(), logging.INFO)
        logger.log(
            log_level,
            f"[Plus Feature] {message}",
            extra={"user_id": str(self.user_id)}
        )


__all__ = ["JournivBridge"]
