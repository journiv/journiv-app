"""
Tag service for handling tag-related operations.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from importlib import import_module
from typing import Any, Dict, List, Optional, Union

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, func, select

from app.core.config import settings
from app.core.exceptions import TagNotFoundError
from app.core.logging_config import log_error, log_info
from app.core.time_utils import utc_now
from app.models.moment import Moment
from app.models.moment_tag_link import MomentTagLink
from app.models.tag import Tag
from app.schemas.tag import (
    TagAnalyticsResponse,
    TagCreate,
    TagDetailAnalyticsResponse,
    TagStatisticsResponse,
    TagSummary,
    TagUpdate,
)
from app.schemas.tag_plus import (
    MonthlyUsageData,
)

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

    @staticmethod
    def _escape_like_term(term: str) -> str:
        """Escape LIKE wildcards so user input is treated as literal text."""
        return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

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

        tag = Tag(name=tag_data.name, user_id=user_id)

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
        search: Optional[str] = None,
    ) -> List[Tag]:
        """Get tags for a user with optional search."""
        statement = select(Tag).where(
            Tag.user_id == user_id,
        )

        if search:
            escaped_search = self._escape_like_term(search)
            statement = statement.where(
                col(Tag.name).ilike(f"%{escaped_search}%", escape="\\")
            )

        statement = (
            statement.order_by(col(Tag.usage_count).desc(), col(Tag.name).asc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.exec(statement))

    def get_popular_tags(
        self, user_id: uuid.UUID, limit: int = DEFAULT_TAG_PAGE_LIMIT
    ) -> List[Tag]:
        """Get most popular tags for a user (excludes soft-deleted)."""
        statement = (
            select(Tag)
            .where(
                Tag.user_id == user_id,
                Tag.usage_count > 0,
            )
            .order_by(col(Tag.usage_count).desc(), col(Tag.name).asc())
            .limit(limit)
        )
        return list(self.session.exec(statement))

    def update_tag(
        self, tag_id: uuid.UUID, user_id: uuid.UUID, tag_data: TagUpdate
    ) -> Tag:
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
        """Hard delete a tag. MomentTagLink rows are removed by DB cascade."""
        tag = self.get_tag_by_id(tag_id, user_id)
        if not tag:
            raise TagNotFoundError("Tag not found")

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

    def _get_moment_for_user(self, moment_id: uuid.UUID, user_id: uuid.UUID) -> Moment:
        """Load a moment and ensure it belongs to the user."""
        moment = self.session.exec(
            select(Moment).where(
                Moment.id == moment_id,
                Moment.user_id == user_id,
            )
        ).first()
        if not moment:
            raise ValueError("Moment not found")
        return moment

    def add_tag_to_moment(
        self, moment_id: uuid.UUID, tag_id: uuid.UUID, user_id: uuid.UUID
    ) -> MomentTagLink:
        """Add a tag to a moment."""
        self._get_moment_for_user(moment_id, user_id)

        tag = self.get_tag_by_id(tag_id, user_id)
        if not tag:
            raise TagNotFoundError("Tag not found")

        existing_link = self.session.exec(
            select(MomentTagLink).where(
                MomentTagLink.moment_id == moment_id, MomentTagLink.tag_id == tag_id
            )
        ).first()

        if existing_link:
            return existing_link

        link = MomentTagLink(moment_id=moment_id, tag_id=tag_id)

        self.session.add(link)

        tag.usage_count += 1
        self.session.add(tag)

        self._commit()
        self.session.refresh(link)
        return link

    def remove_tag_from_moment(
        self, moment_id: uuid.UUID, tag_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Remove a tag from a moment."""
        self._get_moment_for_user(moment_id, user_id)

        tag = self.get_tag_by_id(tag_id, user_id)
        if not tag:
            raise TagNotFoundError("Tag not found")

        link = self.session.exec(
            select(MomentTagLink).where(
                MomentTagLink.moment_id == moment_id,
                MomentTagLink.tag_id == tag_id,
            )
        ).first()

        if link:
            self.session.delete(link)
            tag.usage_count = max(0, tag.usage_count - 1)
            self.session.add(tag)
            self._commit()
            return True
        return False

    def get_moment_tags(self, moment_id: uuid.UUID, user_id: uuid.UUID) -> List[Tag]:
        """Get all tags for a moment."""
        self._get_moment_for_user(moment_id, user_id)
        statement = (
            select(Tag)
            .join(MomentTagLink)
            .where(
                MomentTagLink.moment_id == moment_id,
                Tag.user_id == user_id,
            )
            .order_by(col(Tag.name).asc())
        )
        return list(self.session.exec(statement))

    def get_moments_by_tag(
        self,
        tag_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = DEFAULT_TAG_PAGE_LIMIT,
        offset: int = 0,
    ) -> List[Moment]:
        """Get moments that have a specific tag."""
        tag = self.get_tag_by_id(tag_id, user_id)
        if not tag:
            raise TagNotFoundError("Tag not found")

        statement = (
            select(Moment)
            .join(MomentTagLink)
            .where(
                MomentTagLink.tag_id == tag_id,
                Moment.user_id == user_id,
            )
            .order_by(col(Moment.logged_at_utc).desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.exec(statement))

    def get_tag_statistics(
        self, user_id: uuid.UUID, include_usage_over_time: bool = False
    ) -> TagStatisticsResponse:
        """Get tag usage statistics for a user.

        Privacy: All queries filter by user_id to prevent cross-user data leakage.
        """
        # Total tags
        total_tags = (
            self.session.exec(
                select(func.count(Tag.id)).where(
                    Tag.user_id == user_id,
                )
            ).first()
            or 0
        )

        # Tags with usage
        used_tags = (
            self.session.exec(
                select(func.count(Tag.id)).where(
                    Tag.user_id == user_id,
                    Tag.usage_count > 0,
                )
            ).first()
            or 0
        )

        # Most used tag
        most_used_tag = self.session.exec(
            select(Tag)
            .where(
                Tag.user_id == user_id,
            )
            .order_by(col(Tag.usage_count).desc())
        ).first()

        # Average usage per tag
        avg_usage = (
            self.session.exec(
                select(func.avg(Tag.usage_count)).where(
                    Tag.user_id == user_id,
                )
            ).first()
            or 0.0
        )

        # Tag usage ranking - ALL tags sorted by usage count (descending)
        all_tags = self.session.exec(
            select(Tag)
            .where(
                Tag.user_id == user_id,
            )
            .order_by(col(Tag.usage_count).desc(), col(Tag.name).asc())
        ).all()

        tag_usage_ranking = [
            TagSummary(id=tag.id, name=tag.name, usage_count=tag.usage_count)
            for tag in all_tags
        ]

        # Recently created tags (last 20)
        recently_created_tags = self.session.exec(
            select(Tag)
            .where(
                Tag.user_id == user_id,
            )
            .order_by(col(Tag.created_at).desc())
            .limit(20)
        ).all()

        recently_created_summary = [
            TagSummary(id=tag.id, name=tag.name, usage_count=tag.usage_count)
            for tag in recently_created_tags
        ]

        # Usage over time (optional, computed if requested)
        usage_over_time: Optional[Dict[str, int]] = None
        if include_usage_over_time:
            usage_data = self._compute_usage_over_time(user_id)
            usage_over_time = {item.month_key: item.count for item in usage_data}

        most_used_summary = None
        if most_used_tag:
            most_used_summary = TagSummary(
                id=most_used_tag.id,
                name=most_used_tag.name,
                usage_count=most_used_tag.usage_count,
            )

        return TagStatisticsResponse(
            total_tags=total_tags,
            used_tags=used_tags,
            unused_tags=total_tags - used_tags,
            most_used_tag=most_used_summary,
            average_usage=round(float(avg_usage), 2),
            tag_usage_ranking=tag_usage_ranking,
            recently_created_tags=recently_created_summary,
            usage_over_time=usage_over_time,
        )

    def _compute_usage_over_time(
        self,
        user_id: uuid.UUID,
        tag_id: Optional[uuid.UUID] = None,
        start_date: Optional[Union[datetime, date]] = None,
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
        if settings.database_type == "postgres":
            month_expr = func.to_char(Moment.logged_date_tz, "YYYY-MM")
        else:
            month_expr = func.strftime("%Y-%m", Moment.logged_date_tz)

        statement = (
            select(month_expr.label("month_key"), func.count().label("count"))
            .select_from(MomentTagLink)
            .join(Moment, Moment.id == MomentTagLink.moment_id)
            .join(Tag, Tag.id == MomentTagLink.tag_id)
            .where(
                Tag.user_id == user_id,
                Moment.user_id == user_id,
            )
        )

        if tag_id:
            statement = statement.where(MomentTagLink.tag_id == tag_id)

        if start_date:
            statement = statement.where(col(Moment.logged_date_tz) >= start_date)

        # Group by month
        statement = statement.group_by(month_expr)

        # Execute
        results = self.session.exec(statement).all()

        return [
            MonthlyUsageData(month_key=row.month_key, count=row.count)
            for row in results
        ]

    def merge_tags(
        self, source_id: uuid.UUID, target_id: uuid.UUID, user_id: uuid.UUID
    ) -> Tag:
        """Merge source tag into target tag.

        Case-normalization rules:
        - Normalize both source and target tag names before merge
        - Prevent merging into a tag that differs only by case
        - Move all moment-tag links from source to target
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
            raise ValueError(
                "Target tag name conflicts with existing tag (case-insensitive)"
            )

        # Move all moment-tag links from source to target using explicit
        # delete-old + insert-new pattern (avoid in-place composite PK mutation).
        source_links = self.session.exec(
            select(MomentTagLink).where(MomentTagLink.tag_id == source_id)
        ).all()

        for link in source_links:
            # Check if target already has this moment tagged
            existing_target_link = self.session.exec(
                select(MomentTagLink).where(
                    MomentTagLink.moment_id == link.moment_id,
                    MomentTagLink.tag_id == target_id,
                )
            ).first()

            if existing_target_link:
                # Moment already has target tag, just delete source link
                self.session.delete(link)
            else:
                # Delete old link and create new one
                self.session.delete(link)
                self.session.add(
                    MomentTagLink(moment_id=link.moment_id, tag_id=target_id)
                )

        # Recompute denormalized usage_count from link-table source of truth.
        target_usage_count = self.session.exec(
            select(func.count()).where(MomentTagLink.tag_id == target_id)
        ).one()
        target_tag.usage_count = int(target_usage_count or 0)

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
                        tag = Tag(name=normalized_name, user_id=user_id)
                        self.session.add(tag)
                        self._commit()
                        self.session.refresh(tag)
                    except Exception as e:
                        # If creation fails (e.g., due to unique constraint), rollback and get existing
                        self.session.rollback()
                        tag = self.get_tag_by_name(user_id, normalized_name)
                        if not tag:
                            # If we still can't find it, something went wrong
                            raise ValueError(
                                f"Failed to create or find tag '{normalized_name}': {str(e)}"
                            ) from None
                tags.append(tag)
        return tags

    def bulk_add_tags_to_moment(
        self, moment_id: uuid.UUID, tag_names: List[str], user_id: uuid.UUID
    ) -> List[Tag]:
        """Add multiple tags to a moment by name.

        Creates tags if they don't exist, then associates them with the moment.
        Returns all tags that are associated with the moment after the operation.
        """
        self._get_moment_for_user(moment_id, user_id)

        tags = self.create_or_get_tags(user_id, tag_names)
        if not tags:
            return self.get_moment_tags(moment_id, user_id)

        tag_ids = [tag.id for tag in tags]
        existing_tag_ids = set(
            self.session.exec(
                select(MomentTagLink.tag_id).where(
                    MomentTagLink.moment_id == moment_id,
                    col(MomentTagLink.tag_id).in_(tag_ids),
                )
            ).all()
        )

        created_any = False
        for tag in tags:
            if tag.id in existing_tag_ids:
                continue
            self.session.add(MomentTagLink(moment_id=moment_id, tag_id=tag.id))
            tag.usage_count += 1
            self.session.add(tag)
            created_any = True

        if created_any:
            self._commit()

        return self.get_moment_tags(moment_id, user_id)

    def search_tags(
        self,
        user_id: uuid.UUID,
        query: str,
        limit: int = DEFAULT_TAG_PAGE_LIMIT,
        include_unused: bool = True,
    ) -> List[Tag]:
        """Search tags by name."""
        statement = select(Tag).where(
            Tag.user_id == user_id,
            col(Tag.name).ilike(f"%{self._escape_like_term(query)}%", escape="\\"),
        )
        if not include_unused:
            statement = statement.where(Tag.usage_count > 0)
        statement = statement.order_by(
            col(Tag.usage_count).desc(), col(Tag.name).asc()
        ).limit(limit)
        return list(self.session.exec(statement))

    # ------------------------------------------------------------------
    # Plus analytics (inline mode only — license_data from get_plus_factory)
    # ------------------------------------------------------------------

    def get_tag_analytics(
        self,
        user_id: uuid.UUID,
        license_data: Dict[str, Any],
    ) -> TagAnalyticsResponse:
        """Compute overall tag analytics via Plus (inline mode only)."""
        try:
            plus_svc = self._load_plus_tag_service(
                user_id=user_id,
                license_data=license_data,
            )
            r = plus_svc.compute_tag_analytics()
            return TagAnalyticsResponse.model_validate(r.model_dump())
        except RuntimeError:
            raise
        except Exception as exc:
            message = "Failed to compute Plus tag analytics."
            log_error(exc)
            raise RuntimeError(message) from exc

    def get_tag_detail_analytics(
        self,
        tag_id: uuid.UUID,
        user_id: uuid.UUID,
        license_data: Dict[str, Any],
        days: int = 365,
    ) -> TagDetailAnalyticsResponse:
        """Compute per-tag analytics via Plus (inline mode only)."""
        tag = self.get_tag_by_id(tag_id, user_id)
        if not tag:
            raise TagNotFoundError("Tag not found")

        try:
            plus_svc = self._load_plus_tag_service(
                user_id=user_id,
                license_data=license_data,
            )
            r = plus_svc.compute_tag_detail_analytics(
                tag_id=str(tag_id), tag_name=tag.name, days=days
            )
            return TagDetailAnalyticsResponse.model_validate(r.model_dump())
        except RuntimeError:
            raise
        except Exception as exc:
            message = "Failed to compute Plus tag detail analytics."
            log_error(exc)
            raise RuntimeError(message) from exc

    def _load_plus_tag_service(
        self,
        *,
        user_id: uuid.UUID,
        license_data: Dict[str, Any],
    ) -> Any:
        try:
            plus_module = import_module("app.plus.features._tags_plus")
            PlusTagService = plus_module.TagService
        except (ImportError, ModuleNotFoundError, AttributeError) as exc:
            message = (
                "Plus tag analytics module unavailable. "
                "Ensure Journiv Plus is installed and compatible with this backend."
            )
            log_error(exc)
            raise RuntimeError(message) from exc

        return PlusTagService(
            db=self.session, user_id=user_id, license_data=license_data
        )
