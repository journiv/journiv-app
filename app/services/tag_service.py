"""
Tag service for handling tag-related operations.
"""
import uuid
from typing import List, Optional, Dict, Any

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select, func

from app.core.exceptions import TagNotFoundError
from app.core.logging_config import log_error, log_info
from app.core.time_utils import utc_now
from app.models.entry import Entry
from app.models.tag import Tag, EntryTagLink
from app.schemas.tag import TagCreate, TagUpdate

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

    def add_tag_to_entry(self, entry_id: uuid.UUID, tag_id: uuid.UUID, user_id: uuid.UUID) -> EntryTagLink:
        """Add a tag to an entry."""
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
        ).order_by(Entry.entry_datetime_utc.desc()).offset(offset).limit(limit)
        return list(self.session.exec(statement))

    def get_tag_statistics(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """Get tag usage statistics for a user."""
        # Total tags
        total_tags = self.session.exec(
            select(func.count(Tag.id)).where(
                Tag.user_id == user_id,
            )
        ).first()

        # Tags with usage
        used_tags = self.session.exec(
            select(func.count(Tag.id)).where(
                Tag.user_id == user_id,
                Tag.usage_count > 0,
            )
        ).first()

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
        ).first() or 0

        return {
            'total_tags': total_tags,
            'used_tags': used_tags,
            'unused_tags': total_tags - used_tags,
            'most_used_tag': {
                'id': str(most_used_tag.id),
                'name': most_used_tag.name,
                'usage_count': most_used_tag.usage_count
            } if most_used_tag else None,
            'average_usage': round(avg_usage, 2)
        }

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
        entry = self.session.exec(
            select(Entry).where(
                Entry.id == entry_id,
                Entry.user_id == user_id,
            )
        ).first()

        if not entry:
            raise ValueError("Entry not found")

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
