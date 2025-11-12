"""
Prompt service for handling prompt-related operations.
"""
import random
import threading
import uuid
from typing import List, Optional, Dict, Any

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select, func

from app.core.exceptions import PromptNotFoundError
from app.core.logging_config import log_error
from app.core.time_utils import utc_now
from app.models.entry import Entry
from app.models.enums import PromptCategory
from app.models.journal import Journal
from app.models.prompt import Prompt
from app.schemas.prompt import PromptCreate, PromptUpdate

DEFAULT_PROMPT_PAGE_LIMIT = 50
MAX_PROMPT_PAGE_LIMIT = 100


class PromptService:
    """Service class for prompt operations."""

    _system_prompt_cache: Dict[str, List[Prompt]] = {}
    _cache_lock = threading.RLock()

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        if limit <= 0:
            return DEFAULT_PROMPT_PAGE_LIMIT
        return min(limit, MAX_PROMPT_PAGE_LIMIT)

    @staticmethod
    def _normalize_category(category: Optional[str]) -> Optional[str]:
        if category is None:
            return None
        try:
            return PromptCategory(category.lower()).value
        except ValueError as exc:
            raise PromptNotFoundError(f"Invalid prompt category '{category}'") from exc

    @classmethod
    def _cache_key(cls, *, category: Optional[str], difficulty_level: Optional[int], limit: int) -> str:
        return f"{category or 'any'}::{difficulty_level or 'any'}::{limit}"

    @classmethod
    def invalidate_cache(cls) -> None:
        """Clear the prompt cache. Thread-safe."""
        with cls._cache_lock:
            cls._system_prompt_cache.clear()

    @classmethod
    def _store_cache(cls, key: str, prompts: List[Prompt]) -> None:
        """Store prompts in cache. Thread-safe."""
        with cls._cache_lock:
            # Create copies to avoid session-related issues
            cls._system_prompt_cache[key] = [
                Prompt(
                    id=prompt.id,
                    text=prompt.text,
                    category=prompt.category,
                    difficulty_level=prompt.difficulty_level,
                    estimated_time_minutes=prompt.estimated_time_minutes,
                    is_active=prompt.is_active,
                    usage_count=prompt.usage_count,
                    user_id=prompt.user_id,
                    created_at=prompt.created_at,
                    updated_at=prompt.updated_at
                ) for prompt in prompts
            ]

    @classmethod
    def _get_cached_prompts(cls, key: str) -> Optional[List[Prompt]]:
        """Get prompts from cache. Thread-safe."""
        with cls._cache_lock:
            cached = cls._system_prompt_cache.get(key)
            if cached is None:
                return None
            # Return copies to avoid session-related issues
            return [
                Prompt(
                    id=prompt.id,
                    text=prompt.text,
                    category=prompt.category,
                    difficulty_level=prompt.difficulty_level,
                    estimated_time_minutes=prompt.estimated_time_minutes,
                    is_active=prompt.is_active,
                    usage_count=prompt.usage_count,
                    user_id=prompt.user_id,
                    created_at=prompt.created_at,
                    updated_at=prompt.updated_at
                ) for prompt in cached
            ]

    def _commit(self) -> None:
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    def _get_owned_prompt(
        self,
        prompt_id: uuid.UUID,
        user_id: Optional[uuid.UUID],
        *,
        include_deleted: bool = False
    ) -> Prompt:
        statement = select(Prompt).where(Prompt.id == prompt_id)

        if user_id is None:
            statement = statement.where(Prompt.user_id.is_(None))
        else:
            statement = statement.where(Prompt.user_id == user_id)

        prompt = self.session.exec(statement).first()
        if not prompt:
            raise PromptNotFoundError("Prompt not found")
        return prompt

    def create_prompt(self, user_id: Optional[uuid.UUID], prompt_data: PromptCreate) -> Prompt:
        """Create a new prompt for a user or system."""
        normalized_category = self._normalize_category(prompt_data.category) if prompt_data.category else None
        text = prompt_data.text.strip()

        duplicate_stmt = select(Prompt).where(
            func.lower(Prompt.text) == text.lower(),
        )

        if user_id is None:
            duplicate_stmt = duplicate_stmt.where(Prompt.user_id.is_(None))
        else:
            duplicate_stmt = duplicate_stmt.where(Prompt.user_id == user_id)

        if normalized_category:
            duplicate_stmt = duplicate_stmt.where(Prompt.category == normalized_category)

        existing = self.session.exec(duplicate_stmt).first()
        if existing:
            raise ValueError("A prompt with the same text and category already exists.")

        prompt = Prompt(
            text=text,
            category=normalized_category,
            difficulty_level=prompt_data.difficulty_level,
            estimated_time_minutes=prompt_data.estimated_time_minutes,
            user_id=user_id,
        )

        self.session.add(prompt)
        self._commit()
        self.session.refresh(prompt)
        self.invalidate_cache()
        return prompt

    def update_prompt(
        self,
        prompt_id: uuid.UUID,
        user_id: Optional[uuid.UUID],
        prompt_data: PromptUpdate
    ) -> Prompt:
        """Update an existing prompt."""
        prompt = self._get_owned_prompt(prompt_id, user_id)

        if prompt_data.text is not None:
            text = prompt_data.text.strip()
            if text != prompt.text:
                duplicate_stmt = select(Prompt).where(
                    func.lower(Prompt.text) == text.lower(),
                    Prompt.id != prompt_id,
                )
                if user_id is None:
                    duplicate_stmt = duplicate_stmt.where(Prompt.user_id.is_(None))
                else:
                    duplicate_stmt = duplicate_stmt.where(Prompt.user_id == user_id)

                if prompt_data.category is not None:
                    normalized_category = self._normalize_category(prompt_data.category)
                else:
                    normalized_category = prompt.category

                if normalized_category:
                    duplicate_stmt = duplicate_stmt.where(Prompt.category == normalized_category)

                existing = self.session.exec(duplicate_stmt).first()
                if existing:
                    raise ValueError("A prompt with the same text and category already exists.")

                prompt.text = text

        if prompt_data.category is not None:
            prompt.category = self._normalize_category(prompt_data.category)

        if prompt_data.difficulty_level is not None:
            prompt.difficulty_level = prompt_data.difficulty_level

        if prompt_data.estimated_time_minutes is not None:
            prompt.estimated_time_minutes = prompt_data.estimated_time_minutes

        if prompt_data.is_active is not None:
            prompt.is_active = prompt_data.is_active

        prompt.updated_at = utc_now()
        self.session.add(prompt)
        self._commit()
        self.session.refresh(prompt)
        self.invalidate_cache()
        return prompt

    def delete_prompt(self, prompt_id: uuid.UUID, user_id: Optional[uuid.UUID]) -> bool:
        """Soft delete a prompt. Raises if prompt is in use."""
        prompt = self._get_owned_prompt(prompt_id, user_id)

        in_use = self.session.exec(
            select(func.count(Entry.id)).where(
                Entry.prompt_id == prompt_id,
            )
        ).first() or 0

        if in_use:
            raise ValueError("Prompt is currently in use and cannot be deleted.")

        prompt.is_active = False
        prompt.updated_at = utc_now()
        self.session.add(prompt)
        self._commit()
        self.invalidate_cache()
        return True

    def get_prompt_by_id(self, prompt_id: uuid.UUID, include_deleted: bool = False) -> Optional[Prompt]:
        """Get a prompt by ID."""
        statement = select(Prompt).where(Prompt.id == prompt_id)
        return self.session.exec(statement).first()

    def get_all_prompts(
        self,
        user_id: Optional[uuid.UUID] = None,
        category: Optional[str] = None,
        difficulty_level: Optional[int] = None,
        is_active: bool = True,
        limit: int = 50,
        offset: int = 0
    ) -> List[Prompt]:
        """Get prompts with optional filters."""
        limit = self._normalize_limit(limit)
        normalized_category = self._normalize_category(category) if category else None

        statement = select(Prompt).where(
            Prompt.is_active == is_active,
        )

        if user_id is not None:
            statement = statement.where(Prompt.user_id == user_id)
        else:
            # If no user_id specified, get system prompts (user_id is NULL)
            statement = statement.where(Prompt.user_id.is_(None))

        if normalized_category:
            statement = statement.where(Prompt.category == normalized_category)

        if difficulty_level is not None:
            statement = statement.where(Prompt.difficulty_level == difficulty_level)

        use_cache = user_id is None and is_active and offset == 0
        cache_key = None
        if use_cache:
            cache_key = self._cache_key(
                category=normalized_category,
                difficulty_level=difficulty_level,
                limit=limit
            )
            cached = self._get_cached_prompts(cache_key)
            if cached is not None:
                return cached

        statement = statement.order_by(Prompt.created_at.desc()).offset(offset).limit(limit)
        prompts = list(self.session.exec(statement))

        if use_cache and cache_key is not None:
            self._store_cache(cache_key, prompts)

        return prompts

    def get_system_prompts(
        self,
        category: Optional[str] = None,
        difficulty_level: Optional[int] = None,
        limit: int = 50
    ) -> List[Prompt]:
        """Get system prompts (user_id is NULL)."""
        return self.get_all_prompts(
            user_id=None,
            category=category,
            difficulty_level=difficulty_level,
            limit=limit
        )


    def get_daily_prompt(self, user_id: uuid.UUID) -> Optional[Prompt]:
        """Get a deterministic daily prompt for a user based on user ID and current date."""
        from app.services.user_service import UserService
        from app.core.time_utils import local_date_for_user

        # Get today's date in the user's timezone
        user_service = UserService(self.session)
        user_tz = user_service.get_user_timezone(user_id)
        today = local_date_for_user(utc_now(), user_tz)

        # Get total count of active system prompts
        count_statement = select(func.count(Prompt.id)).where(
            Prompt.is_active == True,
            Prompt.user_id.is_(None),
        )
        total_prompts = self.session.exec(count_statement).first()

        if total_prompts == 0:
            return None

        # Create a deterministic seed based on user ID and current date
        user_date_string = f"{user_id}_{today.isoformat()}"
        hash_value = hash(user_date_string)
        prompt_index = abs(hash_value) % total_prompts

        # Get the specific prompt at the calculated index using OFFSET
        statement = select(Prompt).where(
            Prompt.is_active == True,
            Prompt.user_id.is_(None),
        ).offset(prompt_index).limit(1)

        daily_prompt = self.session.exec(statement).first()
        if not daily_prompt:
            return None

        # Check if user has already answered today's prompt
        existing_entry_statement = select(Entry).where(
            Entry.user_id == user_id,
            Entry.prompt_id == daily_prompt.id,
            Entry.entry_date == today,
        )

        existing_entry = self.session.exec(existing_entry_statement).first()
        if existing_entry:
            # User has already answered today's prompt
            return None

        return daily_prompt

    def get_random_prompt(
        self,
        user_id: Optional[uuid.UUID] = None,
        category: Optional[str] = None,
        difficulty_level: Optional[int] = None
    ) -> Optional[Prompt]:
        """Get a random prompt with optional filters."""
        statement = select(Prompt).where(
            Prompt.is_active == True,
        )

        if user_id is not None:
            statement = statement.where(Prompt.user_id == user_id)
        else:
            statement = statement.where(Prompt.user_id.is_(None))

        normalized_category = self._normalize_category(category) if category else None
        if normalized_category:
            statement = statement.where(Prompt.category == normalized_category)

        if difficulty_level is not None:
            statement = statement.where(Prompt.difficulty_level == difficulty_level)

        available_prompts = list(self.session.exec(statement))
        if available_prompts:
            return random.choice(available_prompts)
        return None



    def increment_usage_count(self, prompt_id: uuid.UUID) -> Prompt:
        """Increment the usage count for a prompt."""
        prompt = self.get_prompt_by_id(prompt_id)
        if not prompt:
            raise PromptNotFoundError("Prompt not found")

        prompt.usage_count += 1
        prompt.updated_at = utc_now()
        self.session.add(prompt)
        self._commit()
        self.session.refresh(prompt)
        self.invalidate_cache()
        return prompt

    def get_prompt_statistics(self, user_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        """Get prompt usage statistics."""
        # Base query
        statement = select(Prompt)

        if user_id is not None:
            statement = statement.where(Prompt.user_id == user_id)
        else:
            statement = statement.where(Prompt.user_id.is_(None))

        prompts = list(self.session.exec(statement))

        if not prompts:
            return {
                'total_prompts': 0,
                'active_prompts': 0,
                'total_usage': 0,
                'average_usage': 0,
                'most_used_prompt': None,
                'category_distribution': {},
                'difficulty_distribution': {}
            }

        # Calculate statistics
        total_prompts = len(prompts)
        active_prompts = len([p for p in prompts if p.is_active])
        total_usage = sum(p.usage_count for p in prompts)
        average_usage = total_usage / total_prompts if total_prompts > 0 else 0

        # Most used prompt
        most_used = max(prompts, key=lambda p: p.usage_count) if prompts else None

        # Category distribution
        category_distribution: Dict[str, int] = {}
        for prompt in prompts:
            category = prompt.category or 'uncategorized'
            category_distribution[category] = category_distribution.get(category, 0) + 1

        # Difficulty distribution
        difficulty_distribution: Dict[str, int] = {}
        for prompt in prompts:
            difficulty_key = str(prompt.difficulty_level) if prompt.difficulty_level is not None else "unknown"
            difficulty_distribution[difficulty_key] = difficulty_distribution.get(difficulty_key, 0) + 1

        return {
            'total_prompts': total_prompts,
            'active_prompts': active_prompts,
            'total_usage': total_usage,
            'average_usage': round(average_usage, 2),
            'most_used_prompt': {
                'id': str(most_used.id),
                'text': most_used.text[:100] + '...' if len(most_used.text) > 100 else most_used.text,
                'usage_count': most_used.usage_count
            } if most_used else None,
            'category_distribution': category_distribution,
            'difficulty_distribution': difficulty_distribution
        }

    def get_prompts_by_category(self, category: str, user_id: Optional[uuid.UUID] = None) -> List[Prompt]:
        """Get prompts by category."""
        return self.get_all_prompts(
            user_id=user_id,
            category=category,
            limit=100
        )

    def get_prompts_by_difficulty(self, difficulty_level: int, user_id: Optional[uuid.UUID] = None) -> List[Prompt]:
        """Get prompts by difficulty level."""
        return self.get_all_prompts(
            user_id=user_id,
            difficulty_level=difficulty_level,
            limit=100
        )

    def search_prompts(self, query: str, user_id: Optional[uuid.UUID] = None) -> List[Prompt]:
        """Search prompts by text content (excludes soft-deleted)."""
        statement = select(Prompt).where(
            Prompt.is_active == True,
            Prompt.text.ilike(f"%{query}%")
        )

        if user_id is not None:
            statement = statement.where(Prompt.user_id == user_id)
        else:
            statement = statement.where(Prompt.user_id.is_(None))

        statement = statement.order_by(Prompt.created_at.desc())
        return list(self.session.exec(statement))

    def bulk_update_prompts(self, user_id: uuid.UUID, updates: List[Dict[str, Any]]) -> List[Prompt]:
        """
        Bulk update prompts for a user.

        Args:
            user_id: The ID of the user who owns the prompts
            updates: List of dicts with 'id' and update fields

        Returns:
            List of updated Prompt objects
        """
        updated_prompts = []

        for update_data in updates:
            prompt_id = update_data.get('id')
            if not prompt_id:
                continue

            # Get the prompt
            statement = select(Prompt).where(
                Prompt.id == prompt_id,
                Prompt.user_id == user_id,
                Prompt.is_active == True
            )
            prompt = self.session.exec(statement).first()

            if not prompt:
                continue

            # Update fields
            if 'text' in update_data:
                prompt.text = update_data['text']
            if 'category' in update_data:
                prompt.category = update_data['category']
            if 'difficulty_level' in update_data:
                prompt.difficulty_level = update_data['difficulty_level']
            if 'estimated_time_minutes' in update_data:
                prompt.estimated_time_minutes = update_data['estimated_time_minutes']

            prompt.updated_at = utc_now()
            self.session.add(prompt)
            updated_prompts.append(prompt)

        self.session.commit()
        return updated_prompts

    def bulk_delete_prompts(self, user_id: uuid.UUID, prompt_ids: List[uuid.UUID]) -> int:
        """
        Bulk soft delete prompts for a user.

        Args:
            user_id: The ID of the user who owns the prompts
            prompt_ids: List of prompt IDs to delete

        Returns:
            Number of prompts deleted
        """
        deleted_count = 0

        for prompt_id in prompt_ids:
            # Get the prompt
            statement = select(Prompt).where(
                Prompt.id == prompt_id,
                Prompt.user_id == user_id,
                Prompt.is_active == True
            )
            prompt = self.session.exec(statement).first()

            if not prompt:
                continue

            # Soft delete
            prompt.is_active = False
            prompt.updated_at = utc_now()
            self.session.add(prompt)
            deleted_count += 1

        self.session.commit()
        return deleted_count
