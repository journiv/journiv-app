"""
Tag service for handling tag-related operations.
"""
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, date


from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select, func

from app.core.config import settings
from app.core.exceptions import TagNotFoundError
from app.core.logging_config import log_error, log_info
from app.core.time_utils import utc_now
from app.models.entry import Entry
from app.models.tag import Tag, EntryTagLink
from app.schemas.tag import TagCreate, TagUpdate, TagStatisticsResponse, TagAnalyticsResponse, TagSummary, TagDetailAnalyticsResponse, PeakMonth
from app.schemas.tag_plus import TagAnalyticsRawData, TagRawData, MonthlyUsageData, TagDetailAnalyticsRawData

DEFAULT_TAG_PAGE_LIMIT = 50
MAX_TAG_PAGE_LIMIT = 100


class TagService:
    """Service class for tag operations."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        """Normalize pagination limit to valid range."""
        if limit <= 0:
            return DEFAULT_TAG_PAGE_LIMIT
        return min(limit, MAX_TAG_PAGE_LIMIT)

    def _commit(self) -> None:
        """Commit database changes with proper error handling."""
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    def create_tag(self, user_id: uuid.UUID, tag_data: TagCreate) -> Tag:
        """Create a new tag."""
        # Check if tag already exists for this user
        existing_tag = self.get_tag_by_name(user_id, tag_data.name)
        if existing_tag:
            return existing_tag

        tag = Tag(
            name=tag_data.name,
            user_id=user_id
        )

        self.session.add(tag)
        self._commit()
        self.session.refresh(tag)
        return tag

    def get_tag_by_id(self, tag_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Tag]:
        """Get a tag by ID for a specific user."""
        statement = select(Tag).where(
            Tag.id == tag_id,
            Tag.user_id == user_id,
        )
        return self.session.exec(statement).first()

    def get_tag_by_name(self, user_id: uuid.UUID, name: str) -> Optional[Tag]:
        """Get a tag by name for a specific user."""
        statement = select(Tag).where(
            Tag.name == name.lower().strip(),
            Tag.user_id == user_id,
        )
        return self.session.exec(statement).first()

    def get_user_tags(
        self,
        user_id: uuid.UUID,
        limit: int = DEFAULT_TAG_PAGE_LIMIT,
        offset: int = 0,
        search: Optional[str] = None
    ) -> List[Tag]:
        """Get tags for a user with optional search."""
        statement = select(Tag).where(
            Tag.user_id == user_id,
        )

        if search:
            statement = statement.where(Tag.name.ilike(f"%{search}%"))

        statement = statement.order_by(Tag.usage_count.desc(), Tag.name.asc()).offset(offset).limit(limit)
        return list(self.session.exec(statement))

    def get_popular_tags(self, user_id: uuid.UUID, limit: int = DEFAULT_TAG_PAGE_LIMIT) -> List[Tag]:
        """Get most popular tags for a user (excludes soft-deleted)."""
        statement = select(Tag).where(
            Tag.user_id == user_id,
            Tag.usage_count > 0,
        ).order_by(Tag.usage_count.desc(), Tag.name.asc()).limit(limit)
        return list(self.session.exec(statement))

    def update_tag(self, tag_id: uuid.UUID, user_id: uuid.UUID, tag_data: TagUpdate) -> Tag:
        """Update a tag."""
        tag = self.get_tag_by_id(tag_id, user_id)
        if not tag:
            raise TagNotFoundError("Tag not found")

        # Check if new name already exists for this user
        if tag_data.name and tag_data.name.lower().strip() != tag.name:
            existing_tag = self.get_tag_by_name(user_id, tag_data.name)
            if existing_tag:
                raise ValueError("Tag with this name already exists")

        if tag_data.name:
            tag.name = tag_data.name.lower().strip()

        tag.updated_at = utc_now()
        self.session.add(tag)
        self._commit()
        self.session.refresh(tag)
        return tag

    def delete_tag(self, tag_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Hard delete a tag and its related records."""
        tag = self.get_tag_by_id(tag_id, user_id)
        if not tag:
            raise TagNotFoundError("Tag not found")

        # Hard delete related EntryTagLink records
        tag_link_statement = select(EntryTagLink).where(EntryTagLink.tag_id == tag_id)
        tag_link_records = self.session.exec(tag_link_statement).all()
        for tag_link in tag_link_records:
            self.session.delete(tag_link)

        # Hard delete the tag
        self.session.delete(tag)

        try:
            self._commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        log_info(f"Tag hard-deleted for user {user_id}: {tag_id}")
        return True

    def _get_entry_for_user(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> Entry:
        """Load an entry and ensure it belongs to the user."""
        entry = self.session.exec(
            select(Entry).where(
                Entry.id == entry_id,
                Entry.user_id == user_id,
            )
        ).first()
        if not entry:
            raise ValueError("Entry not found")
        return entry

    def add_tag_to_entry(self, entry_id: uuid.UUID, tag_id: uuid.UUID, user_id: uuid.UUID) -> EntryTagLink:
        """Add a tag to an entry."""
        # Verify entry belongs to user
        self._get_entry_for_user(entry_id, user_id)

        # Verify tag belongs to user
        tag = self.get_tag_by_id(tag_id, user_id)
        if not tag:
            raise TagNotFoundError("Tag not found")

        # Check if association already exists (including soft-deleted)
        existing_link = self.session.exec(
            select(EntryTagLink).where(
                EntryTagLink.entry_id == entry_id,
                EntryTagLink.tag_id == tag_id
            )
        ).first()

        if existing_link:
            # Link already exists, just return it
            return existing_link

        # Create new association
        link = EntryTagLink(
            entry_id=entry_id,
            tag_id=tag_id
        )

        self.session.add(link)

        # Update tag usage count
        tag.usage_count += 1
        self.session.add(tag)

        self._commit()
        self.session.refresh(link)
        return link

    def remove_tag_from_entry(self, entry_id: uuid.UUID, tag_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Remove a tag from an entry (soft delete)."""
        # Verify entry belongs to user
        self._get_entry_for_user(entry_id, user_id)

        # Verify tag belongs to user
        tag = self.get_tag_by_id(tag_id, user_id)
        if not tag:
            raise TagNotFoundError("Tag not found")

        # Find the association (only non-deleted)
        link = self.session.exec(
            select(EntryTagLink).where(
                EntryTagLink.entry_id == entry_id,
                EntryTagLink.tag_id == tag_id,
            )
        ).first()

        if link:
            # Hard delete the link
            self.session.delete(link)

            # Update tag usage count
            tag.usage_count = max(0, tag.usage_count - 1)
            self.session.add(tag)

            self._commit()
            return True
        return False

    def get_entry_tags(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> List[Tag]:
        """Get all tags for an entry"""
        self._get_entry_for_user(entry_id, user_id)
        statement = select(Tag).join(EntryTagLink).where(
            EntryTagLink.entry_id == entry_id,
            Tag.user_id == user_id,
        ).order_by(Tag.name.asc())
        return list(self.session.exec(statement))

    def get_entries_by_tag(
        self,
        tag_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = DEFAULT_TAG_PAGE_LIMIT,
        offset: int = 0
    ) -> List[Entry]:
        """Get entries that have a specific tag."""
        # Verify tag belongs to user
        tag = self.get_tag_by_id(tag_id, user_id)
        if not tag:
            raise TagNotFoundError("Tag not found")

        statement = select(Entry).join(EntryTagLink).where(
            EntryTagLink.tag_id == tag_id,
            Entry.user_id == user_id,
            Entry.is_draft.is_(False),
        ).order_by(Entry.entry_datetime_utc.desc()).offset(offset).limit(limit)
        return list(self.session.exec(statement))

    def get_tag_statistics(self, user_id: uuid.UUID, include_usage_over_time: bool = False) -> TagStatisticsResponse:
        """Get tag usage statistics for a user.

        Privacy: All queries filter by user_id to prevent cross-user data leakage.
        """
        # Total tags
        total_tags = self.session.exec(
            select(func.count(Tag.id)).where(
                Tag.user_id == user_id,
            )
        ).first() or 0

        # Tags with usage
        used_tags = self.session.exec(
            select(func.count(Tag.id)).where(
                Tag.user_id == user_id,
                Tag.usage_count > 0,
            )
        ).first() or 0

        # Most used tag
        most_used_tag = self.session.exec(
            select(Tag).where(
                Tag.user_id == user_id,
            ).order_by(Tag.usage_count.desc())
        ).first()

        # Average usage per tag
        avg_usage = self.session.exec(
            select(func.avg(Tag.usage_count)).where(
                Tag.user_id == user_id,
            )
        ).first() or 0.0

        # Tag usage ranking - ALL tags sorted by usage count (descending)
        all_tags = self.session.exec(
            select(Tag).where(
                Tag.user_id == user_id,
            ).order_by(Tag.usage_count.desc(), Tag.name.asc())
        ).all()

        tag_usage_ranking = [
            TagSummary(
                id=tag.id,
                name=tag.name,
                usage_count=tag.usage_count
            )
            for tag in all_tags
        ]

        # Recently created tags (last 20)
        recently_created_tags = self.session.exec(
            select(Tag).where(
                Tag.user_id == user_id,
            ).order_by(Tag.created_at.desc()).limit(20)
        ).all()

        recently_created_summary = [
            TagSummary(
                id=tag.id,
                name=tag.name,
                usage_count=tag.usage_count
            )
            for tag in recently_created_tags
        ]

        # Usage over time (optional, computed if requested)
        usage_over_time: Optional[Dict[str, int]] = None
        if include_usage_over_time:
            usage_data = self._compute_usage_over_time(user_id)
            usage_over_time = {
                item.month_key: item.count for item in usage_data
            }

        most_used_summary = None
        if most_used_tag:
            most_used_summary = TagSummary(
                id=most_used_tag.id,
                name=most_used_tag.name,
                usage_count=most_used_tag.usage_count
            )

        return TagStatisticsResponse(
            total_tags=total_tags,
            used_tags=used_tags,
            unused_tags=total_tags - used_tags,
            most_used_tag=most_used_summary,
            average_usage=round(float(avg_usage), 2),
            tag_usage_ranking=tag_usage_ranking,
            recently_created_tags=recently_created_summary,
            usage_over_time=usage_over_time
        )

    def _compute_usage_over_time(
        self,
        user_id: uuid.UUID,
        tag_id: Optional[uuid.UUID] = None,
        start_date: Optional[datetime | date] = None
    ) -> List[MonthlyUsageData]:
        """
        Compute tag usage over time grouped by month using efficient SQL aggregation.

        Args:
            user_id: User UUID
            tag_id: Optional tag UUID to filter by specific tag
            start_date: Optional start date to filter entries

        Returns:
            List of MonthlyUsageData objects
        """
        # Use centralized database type detection from settings
        if settings.database_type == 'postgres':
            # PostgreSQL: Use to_char for date formatting
            month_expr = func.to_char(Entry.entry_date, 'YYYY-MM')
        else:
            # SQLite: Use strftime for date formatting
            month_expr = func.strftime('%Y-%m', Entry.entry_date)

        # Build query
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
            Tag.user_id == user_id,
            Entry.user_id == user_id,
            Entry.is_draft.is_(False),
        )

        # Apply filters
        if tag_id:
            statement = statement.where(EntryTagLink.tag_id == tag_id)

        if start_date:
            statement = statement.where(Entry.entry_date >= start_date)

        # Group by month
        statement = statement.group_by(month_expr)

        # Execute
        results = self.session.exec(statement).all()

        return [
            MonthlyUsageData(month_key=row.month_key, count=row.count)
            for row in results
        ]

    def get_tag_analytics(self, user_id: uuid.UUID, plus_factory) -> TagAnalyticsResponse:
        """
        Get advanced tag analytics with required time-series data (Journiv Plus feature).

        This method performs all database queries and delegates computation to Plus.

        Args:
            user_id: User UUID
            plus_factory: PlusFeatureFactory instance (validated by dependency)

        Returns:
            TagAnalyticsResponse with computed analytics from Plus

        Raises:
            PermissionError: If Plus license is invalid (should be caught by dependency)
        """
        # =====================================================================
        # DATABASE QUERIES - Backend responsibility
        # =====================================================================

        # Total tags count
        total_tags = self.session.exec(
            select(func.count(Tag.id)).where(
                Tag.user_id == user_id,
            )
        ).first() or 0

        # Tags with usage > 0
        used_tags = self.session.exec(
            select(func.count(Tag.id)).where(
                Tag.user_id == user_id,
                Tag.usage_count > 0,
            )
        ).first() or 0

        # All tags sorted by usage count (descending), then name (ascending)
        # Optimization: Select only required fields to avoid ORM overhead for large number of tags
        statement = select(
            Tag.id, Tag.name, Tag.usage_count, Tag.created_at
        ).where(
            Tag.user_id == user_id,
        ).order_by(Tag.usage_count.desc(), Tag.name.asc())

        # Returns list of tuples/rows: (id, name, usage_count, created_at)
        all_tags_rows = self.session.exec(statement).all()

        # Most used tag (first in sorted list)
        most_used_row = all_tags_rows[0] if all_tags_rows else None

        # Recently created tags
        # Optimization: Sort in memory from result to save a DB query
        # This is safe because we already fetched all tags for the ranking distribution in Plus
        recently_created_rows = sorted(
            all_tags_rows,
            key=lambda r: r.created_at,
            reverse=True
        )[:20]

        # Average usage per tag
        avg_usage = self.session.exec(
            select(func.avg(Tag.usage_count)).where(
                Tag.user_id == user_id,
            )
        ).first() or 0.0

        # Monthly usage data (SQL-aggregated)
        monthly_usage_raw = self._compute_usage_over_time(user_id)

        # =====================================================================
        # BUILD RAW DATA DTO
        # =====================================================================

        raw_data = TagAnalyticsRawData(
            total_tags=total_tags,
            used_tags=used_tags,
            all_tags=[
                TagRawData(
                    id=row.id,
                    name=row.name,
                    usage_count=row.usage_count
                )
                for row in all_tags_rows
            ],
            most_used_tag=TagRawData(
                id=most_used_row.id,
                name=most_used_row.name,
                usage_count=most_used_row.usage_count
            ) if most_used_row else None,
            recently_created_tags=[
                TagRawData(
                    id=row.id,
                    name=row.name,
                    usage_count=row.usage_count
                )
                for row in recently_created_rows
            ],
            monthly_usage_raw=monthly_usage_raw,
            average_usage=float(avg_usage)
        )

        # =====================================================================
        # CALL PLUS SERVICE TO COMPUTE ANALYTICS
        # =====================================================================

        tag_service = plus_factory.get_tag_service()
        plus_result = tag_service.compute_tag_analytics(raw_data)

        # =====================================================================
        # CONVERT PLUS RESULT TO BACKEND SCHEMA
        # =====================================================================

        # Convert Plus TagSummary (id as string) back to backend TagSummary (id as UUID)
        tag_usage_ranking = [
            TagSummary(
                id=uuid.UUID(tag.id),
                name=tag.name,
                usage_count=tag.usage_count
            )
            for tag in plus_result.tag_usage_ranking
        ]

        recently_created_summary = [
            TagSummary(
                id=uuid.UUID(tag.id),
                name=tag.name,
                usage_count=tag.usage_count
            )
            for tag in plus_result.recently_created_tags
        ]

        most_used_summary = None
        if plus_result.most_used_tag:
            most_used_summary = TagSummary(
                id=uuid.UUID(plus_result.most_used_tag.id),
                name=plus_result.most_used_tag.name,
                usage_count=plus_result.most_used_tag.usage_count
            )

        return TagAnalyticsResponse(
            total_tags=plus_result.total_tags,
            used_tags=plus_result.used_tags,
            unused_tags=plus_result.unused_tags,
            most_used_tag=most_used_summary,
            average_usage=plus_result.average_usage,
            tag_usage_ranking=tag_usage_ranking,
            recently_created_tags=recently_created_summary,
            usage_over_time=plus_result.usage_over_time,
            tag_distribution=plus_result.tag_distribution
        )

    def merge_tags(self, source_id: uuid.UUID, target_id: uuid.UUID, user_id: uuid.UUID) -> Tag:
        """Merge source tag into target tag.

        Case-normalization rules:
        - Normalize both source and target tag names before merge
        - Prevent merging into a tag that differs only by case
        - Move all entry-tag links from source to target
        - Delete source tag
        """
        # Get both tags and verify they belong to user
        source_tag = self.get_tag_by_id(source_id, user_id)
        if not source_tag:
            raise TagNotFoundError("Source tag not found")

        target_tag = self.get_tag_by_id(target_id, user_id)
        if not target_tag:
            raise TagNotFoundError("Target tag not found")

        # Normalize both tag names
        source_normalized = source_tag.name.strip().lower()
        target_normalized = target_tag.name.strip().lower()

        # Prevent merging into self (case-insensitive)
        if source_normalized == target_normalized:
            raise ValueError("Cannot merge tag into itself (case-insensitive match)")

        # Check if target tag name already exists with different case
        existing_tag = self.get_tag_by_name(user_id, target_tag.name)
        if existing_tag and existing_tag.id != target_id:
            raise ValueError("Target tag name conflicts with existing tag (case-insensitive)")

        # Move all entry-tag links from source to target
        source_links = self.session.exec(
            select(EntryTagLink).where(EntryTagLink.tag_id == source_id)
        ).all()

        for link in source_links:
            # Check if target already has this entry tagged
            existing_target_link = self.session.exec(
                select(EntryTagLink).where(
                    EntryTagLink.entry_id == link.entry_id,
                    EntryTagLink.tag_id == target_id
                )
            ).first()

            if existing_target_link:
                # Entry already has target tag, just delete source link
                self.session.delete(link)
                # Decrement source tag usage
                source_tag.usage_count = max(0, source_tag.usage_count - 1)
            else:
                # Update link to point to target tag
                link.tag_id = target_id
                self.session.add(link)
                # Update usage counts
                source_tag.usage_count = max(0, source_tag.usage_count - 1)
                target_tag.usage_count += 1

        # Delete source tag
        self.session.delete(source_tag)
        self.session.add(target_tag)
        self._commit()
        self.session.refresh(target_tag)

        log_info(f"Tag merged: {source_id} -> {target_id} for user {user_id}")
        return target_tag

    def create_or_get_tags(self, user_id: uuid.UUID, tag_names: List[str]) -> List[Tag]:
        """Create tags if they don't exist, or get existing ones.

        This method handles the race condition where multiple requests might try to create
        the same tag simultaneously. It uses a try-catch pattern to handle unique constraint
        violations gracefully by rolling back and fetching the existing tag.
        """
        tags = []
        for name in tag_names:
            if name.strip():
                normalized_name = name.lower().strip()
                # Try to get existing tag first
                tag = self.get_tag_by_name(user_id, normalized_name)
                if not tag:
                    try:
                        # Try to create the tag, handle unique constraint violation
                        tag = Tag(
                            name=normalized_name,
                            user_id=user_id
                        )
                        self.session.add(tag)
                        self._commit()
                        self.session.refresh(tag)
                    except Exception as e:
                        # If creation fails (e.g., due to unique constraint), rollback and get existing
                        self.session.rollback()
                        tag = self.get_tag_by_name(user_id, normalized_name)
                        if not tag:
                            # If we still can't find it, something went wrong
                            raise ValueError(f"Failed to create or find tag '{normalized_name}': {str(e)}")
                tags.append(tag)
        return tags

    def bulk_add_tags_to_entry(self, entry_id: uuid.UUID, tag_names: List[str], user_id: uuid.UUID) -> List[Tag]:
        """Add multiple tags to an entry by name.

        Creates tags if they don't exist, then associates them with the entry.
        Returns all tags that are associated with the entry after the operation.
        """
        # Verify entry exists and belongs to user
        self._get_entry_for_user(entry_id, user_id)

        # Get or create tags
        tags = self.create_or_get_tags(user_id, tag_names)

        # Add each tag to the entry
        for tag in tags:
            try:
                self.add_tag_to_entry(entry_id, tag.id, user_id)
            except Exception:
                # Tag already associated or other error, skip
                pass

        # Return all tags currently associated with the entry
        return self.get_entry_tags(entry_id, user_id)

    def search_tags(self, user_id: uuid.UUID, query: str, limit: int = DEFAULT_TAG_PAGE_LIMIT) -> List[Tag]:
        """Search tags by name."""
        statement = select(Tag).where(
            Tag.user_id == user_id,
            Tag.name.ilike(f"%{query}%"),
        ).order_by(Tag.usage_count.desc(), Tag.name.asc()).limit(limit)
        return list(self.session.exec(statement))

    def get_tag_detail_analytics(
        self,
        tag_id: uuid.UUID,
        user_id: uuid.UUID,
        plus_factory,
        days: int = 365
    ) -> TagDetailAnalyticsResponse:
        """
        Get per-tag analytics with trend analysis and insights (Journiv Plus feature).

        This method performs all database queries for a specific tag and delegates
        computation to Plus.

        Args:
            tag_id: Tag UUID
            user_id: User UUID
            plus_factory: PlusFeatureFactory instance (validated by dependency)
            days: Number of days to analyze (default: 365)

        Returns:
            TagDetailAnalyticsResponse with computed analytics from Plus

        Raises:
            TagNotFoundError: If tag doesn't exist or doesn't belong to user
            PermissionError: If Plus license is invalid (should be caught by dependency)
        """
        # =====================================================================
        # VERIFY TAG EXISTS AND BELONGS TO USER
        # =====================================================================

        tag = self.get_tag_by_id(tag_id, user_id)
        if not tag:
            raise TagNotFoundError("Tag not found")

        # =====================================================================
        # DATABASE QUERIES - Backend responsibility
        # =====================================================================

        # Calculate date range for analysis
        cutoff_date = utc_now().date() - timedelta(days=days)

        # Total usage count for this tag (all time)
        total_usage_count = tag.usage_count

        # Monthly usage data (SQL-aggregated)
        monthly_usage_raw = self._compute_usage_over_time(
            user_id=user_id,
            tag_id=tag_id,
            start_date=cutoff_date
        )

        # Get first and last usage dates for this tag
        first_used_query = select(func.min(Entry.entry_datetime_utc)).select_from(
            EntryTagLink
        ).join(
            Entry, Entry.id == EntryTagLink.entry_id
        ).where(
            EntryTagLink.tag_id == tag_id,
            Entry.user_id == user_id,
            Entry.is_draft.is_(False),
        )
        first_used = self.session.exec(first_used_query).first()

        last_used_query = select(func.max(Entry.entry_datetime_utc)).select_from(
            EntryTagLink
        ).join(
            Entry, Entry.id == EntryTagLink.entry_id
        ).where(
            EntryTagLink.tag_id == tag_id,
            Entry.user_id == user_id,
            Entry.is_draft.is_(False),
        )
        last_used = self.session.exec(last_used_query).first()

        # =====================================================================
        # BUILD RAW DATA DTO
        # =====================================================================

        raw_data = TagDetailAnalyticsRawData(
            tag_id=tag_id,
            tag_name=tag.name,
            total_usage_count=total_usage_count,
            monthly_usage=monthly_usage_raw,
            first_used=first_used,
            last_used=last_used,
            days_requested=days
        )

        # =====================================================================
        # CALL PLUS SERVICE TO COMPUTE ANALYTICS
        # =====================================================================

        tag_service = plus_factory.get_tag_service()
        plus_result = tag_service.compute_tag_detail_analytics(raw_data)

        # =====================================================================
        # CONVERT PLUS RESULT TO BACKEND SCHEMA
        # =====================================================================

        # Convert string datetime back to datetime objects
        first_used_dt = datetime.fromisoformat(plus_result.first_used) if plus_result.first_used else None
        last_used_dt = datetime.fromisoformat(plus_result.last_used) if plus_result.last_used else None

        # Convert PeakMonthResult to PeakMonth (if present)

        peak_month = None
        if plus_result.peak_month:
            peak_month = PeakMonth(
                month=plus_result.peak_month.month,
                count=plus_result.peak_month.count
            )

        return TagDetailAnalyticsResponse(
            tag_id=uuid.UUID(plus_result.tag_id),
            tag_name=plus_result.tag_name,
            usage_count=plus_result.usage_count,
            usage_over_time=plus_result.usage_over_time,
            first_used=first_used_dt,
            last_used=last_used_dt,
            peak_month=peak_month,
            trend=plus_result.trend,
            growth_rate=plus_result.growth_rate,
            days_analyzed=plus_result.days_analyzed
        )
