"""
Prompt service for handling prompt-related operations.
"""

import random
import threading
import uuid
from collections import Counter
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, func, select

from app.core.exceptions import PromptNotFoundError
from app.core.logging_config import log_error
from app.core.time_utils import utc_now
from app.models.enums import PromptCategory
from app.models.moment import Moment
from app.models.prompt import Prompt
from app.schemas.prompt import PromptCreate, PromptResponse, PromptUpdate

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
    def _cache_key(
        cls,
        *,
        category: Optional[str],
        difficulty_level: Optional[int],
        q: Optional[str],
        min_minutes: Optional[int],
        max_minutes: Optional[int],
        limit: int,
    ) -> str:
        return repr(
            (
                category,
                difficulty_level,
                q,
                min_minutes,
                max_minutes,
                limit,
            )
        )

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
                    updated_at=prompt.updated_at,
                )
                for prompt in prompts
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
                    updated_at=prompt.updated_at,
                )
                for prompt in cached
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
        include_deleted: bool = False,
    ) -> Prompt:
        statement = select(Prompt).where(Prompt.id == prompt_id)

        if user_id is None:
            statement = statement.where(col(Prompt.user_id).is_(None))
        else:
            statement = statement.where(Prompt.user_id == user_id)

        prompt = self.session.exec(statement).first()
        if not prompt:
            raise PromptNotFoundError("Prompt not found")
        return prompt

    def create_prompt(
        self, user_id: Optional[uuid.UUID], prompt_data: PromptCreate
    ) -> Prompt:
        """Create a new prompt for a user or system."""
        normalized_category = (
            self._normalize_category(prompt_data.category)
            if prompt_data.category
            else None
        )
        text = prompt_data.text.strip()

        duplicate_stmt = select(Prompt).where(
            func.lower(Prompt.text) == text.lower(),
        )

        if user_id is None:
            duplicate_stmt = duplicate_stmt.where(col(Prompt.user_id).is_(None))
        else:
            duplicate_stmt = duplicate_stmt.where(Prompt.user_id == user_id)

        if normalized_category:
            duplicate_stmt = duplicate_stmt.where(
                Prompt.category == normalized_category
            )

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
        prompt_data: PromptUpdate,
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
                    duplicate_stmt = duplicate_stmt.where(col(Prompt.user_id).is_(None))
                else:
                    duplicate_stmt = duplicate_stmt.where(Prompt.user_id == user_id)

                if prompt_data.category is not None:
                    normalized_category = self._normalize_category(prompt_data.category)
                else:
                    normalized_category = prompt.category

                if normalized_category:
                    duplicate_stmt = duplicate_stmt.where(
                        Prompt.category == normalized_category
                    )

                existing = self.session.exec(duplicate_stmt).first()
                if existing:
                    raise ValueError(
                        "A prompt with the same text and category already exists."
                    )

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

        from app.models.moment import Moment

        in_use = (
            self.session.exec(
                select(func.count(Moment.id)).where(
                    col(Moment.prompt_id) == prompt_id,
                )
            ).one()
            or 0
        )

        if in_use:
            raise ValueError("Prompt is currently in use and cannot be deleted.")

        prompt.is_active = False
        prompt.updated_at = utc_now()
        self.session.add(prompt)
        self._commit()
        self.invalidate_cache()
        return True

    def get_prompt_by_id(
        self, prompt_id: uuid.UUID, include_deleted: bool = False
    ) -> Optional[Prompt]:
        """Get a prompt by ID."""
        statement = select(Prompt).where(Prompt.id == prompt_id)
        return self.session.exec(statement).first()

    def prompt_responses(
        self, prompts: List[Prompt], user_id: uuid.UUID
    ) -> List[PromptResponse]:
        """Attach current writer answer counts to a set of prompt responses.

        Prompt usage is the number of the current user's Moments linked to a
        prompt. Fetch the counts as one grouped query so a prompt page does not
        turn into one query per card.
        """
        prompt_ids = [prompt.id for prompt in prompts]
        if not prompt_ids:
            return []

        statement = (
            select(Moment.prompt_id, func.count(Moment.id))
            .where(
                Moment.user_id == user_id,
                col(Moment.prompt_id).in_(prompt_ids),
            )
            .group_by(Moment.prompt_id)
        )
        answered_counts = {
            prompt_id: count
            for prompt_id, count in self.session.exec(statement)
            if prompt_id is not None
        }
        return [
            PromptResponse.model_validate(
                {
                    **prompt.model_dump(),
                    "answered_count": answered_counts.get(prompt.id, 0),
                }
            )
            for prompt in prompts
        ]

    def prompt_response(self, prompt: Prompt, user_id: uuid.UUID) -> PromptResponse:
        """Attach the current writer's answer count to one prompt."""
        return self.prompt_responses([prompt], user_id)[0]

    @staticmethod
    def _normalized_search_query(q: Optional[str]) -> Optional[str]:
        """Treat blank browse searches as absent filters."""
        if q is None:
            return None
        return q.strip() or None

    def _filtered_prompt_statement(
        self,
        *,
        statement: Any = None,
        user_id: Optional[uuid.UUID],
        category: Optional[str],
        difficulty_level: Optional[int],
        is_active: bool,
        q: Optional[str],
        min_minutes: Optional[int],
        max_minutes: Optional[int],
    ):
        """Build the shared browse/count query so pagination cannot drift."""
        normalized_category = self._normalize_category(category) if category else None
        normalized_q = self._normalized_search_query(q)
        statement = statement if statement is not None else select(Prompt)
        statement = statement.where(Prompt.is_active == is_active)

        if user_id is not None:
            statement = statement.where(Prompt.user_id == user_id)
        else:
            statement = statement.where(col(Prompt.user_id).is_(None))

        if normalized_category:
            statement = statement.where(Prompt.category == normalized_category)
        if difficulty_level is not None:
            statement = statement.where(Prompt.difficulty_level == difficulty_level)
        if normalized_q:
            pattern = f"%{normalized_q}%"
            # Search the prompt body plus the raw and human-readable category.
            # The latter preserves a browser search such as "self discovery" for
            # the API's `self_discovery` category value.
            statement = statement.where(
                or_(
                    col(Prompt.text).ilike(pattern),
                    col(Prompt.category).ilike(pattern),
                    func.replace(col(Prompt.category), "_", " ").ilike(pattern),
                    func.replace(col(Prompt.category), "_", "-").ilike(pattern),
                )
            )
        if min_minutes is not None:
            statement = statement.where(
                col(Prompt.estimated_time_minutes) >= min_minutes
            )
        if max_minutes is not None:
            statement = statement.where(
                col(Prompt.estimated_time_minutes) <= max_minutes
            )
        return statement

    def get_all_prompts(
        self,
        user_id: Optional[uuid.UUID] = None,
        category: Optional[str] = None,
        difficulty_level: Optional[int] = None,
        q: Optional[str] = None,
        min_minutes: Optional[int] = None,
        max_minutes: Optional[int] = None,
        is_active: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Prompt]:
        """Get prompts with optional filters."""
        limit = self._normalize_limit(limit)
        normalized_category = self._normalize_category(category) if category else None
        normalized_q = self._normalized_search_query(q)
        statement = self._filtered_prompt_statement(
            user_id=user_id,
            category=normalized_category,
            difficulty_level=difficulty_level,
            is_active=is_active,
            q=normalized_q,
            min_minutes=min_minutes,
            max_minutes=max_minutes,
        )

        use_cache = user_id is None and is_active and offset == 0
        cache_key = None
        if use_cache:
            cache_key = self._cache_key(
                category=normalized_category,
                difficulty_level=difficulty_level,
                q=normalized_q,
                min_minutes=min_minutes,
                max_minutes=max_minutes,
                limit=limit,
            )
            cached = self._get_cached_prompts(cache_key)
            if cached is not None:
                return cached

        statement = (
            statement.order_by(
                col(Prompt.created_at).desc(),
                col(Prompt.id).desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        prompts = list(self.session.exec(statement))

        if use_cache and cache_key is not None:
            self._store_cache(cache_key, prompts)

        return prompts

    def get_system_prompts(
        self,
        category: Optional[str] = None,
        difficulty_level: Optional[int] = None,
        q: Optional[str] = None,
        min_minutes: Optional[int] = None,
        max_minutes: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Prompt]:
        """Get system prompts (user_id is NULL)."""
        return self.get_all_prompts(
            user_id=None,
            category=category,
            difficulty_level=difficulty_level,
            q=q,
            min_minutes=min_minutes,
            max_minutes=max_minutes,
            limit=limit,
            offset=offset,
        )

    def count_system_prompts(
        self,
        category: Optional[str] = None,
        difficulty_level: Optional[int] = None,
        q: Optional[str] = None,
        min_minutes: Optional[int] = None,
        max_minutes: Optional[int] = None,
    ) -> int:
        """Count active system prompts for the same filters as the list API."""
        statement = self._filtered_prompt_statement(
            statement=select(func.count(Prompt.id)),
            user_id=None,
            category=category,
            difficulty_level=difficulty_level,
            is_active=True,
            q=q,
            min_minutes=min_minutes,
            max_minutes=max_minutes,
        )
        return self.session.exec(statement).one() or 0

    def count_system_prompts_by_category(
        self,
        difficulty_level: Optional[int] = None,
        q: Optional[str] = None,
        min_minutes: Optional[int] = None,
        max_minutes: Optional[int] = None,
    ) -> Dict[str, int]:
        """Count active system prompts by category for browser filter badges."""
        statement = self._filtered_prompt_statement(
            statement=select(Prompt.category, func.count(Prompt.id)),
            user_id=None,
            category=None,
            difficulty_level=difficulty_level,
            is_active=True,
            q=q,
            min_minutes=min_minutes,
            max_minutes=max_minutes,
        )
        statement = statement.group_by(Prompt.category)
        return {
            category or "": count for category, count in self.session.exec(statement)
        }

    def get_daily_prompt(self, user_id: uuid.UUID) -> Optional[Prompt]:
        """Get a deterministic daily prompt for a user based on user ID and current date."""
        from app.core.time_utils import local_date_for_user
        from app.services.user_service import UserService

        # Get today's date in the user's timezone
        user_service = UserService(self.session)
        user_tz = user_service.get_user_timezone(user_id)
        today = local_date_for_user(utc_now(), user_tz)

        # Get total count of active system prompts
        count_statement = select(func.count(Prompt.id)).where(
            Prompt.is_active,
            col(Prompt.user_id).is_(None),
        )
        total_prompts = self.session.exec(count_statement).one() or 0

        if total_prompts == 0:
            return None

        # Create a deterministic seed based on user ID and current date
        user_date_string = f"{user_id}_{today.isoformat()}"
        hash_value = hash(user_date_string)
        prompt_index = abs(hash_value) % total_prompts

        # Get the specific prompt at the calculated index using OFFSET
        statement = (
            select(Prompt)
            .where(
                Prompt.is_active,
                col(Prompt.user_id).is_(None),
            )
            .offset(prompt_index)
            .limit(1)
        )

        daily_prompt = self.session.exec(statement).first()
        if not daily_prompt:
            return None

        # Check if user has already answered today's prompt (moment-first ownership).
        from app.models.moment import Moment

        existing_moment_statement = select(Moment).where(
            Moment.user_id == user_id,
            col(Moment.prompt_id) == daily_prompt.id,
            col(Moment.logged_date_tz) == today,
        )

        existing_moment = self.session.exec(existing_moment_statement).first()
        if existing_moment:
            # User has already answered today's prompt (with or without Entry).
            return None

        return daily_prompt

    def get_random_prompt(
        self,
        user_id: Optional[uuid.UUID] = None,
        category: Optional[str] = None,
        difficulty_level: Optional[int] = None,
    ) -> Optional[Prompt]:
        """Get a random prompt with optional filters."""
        statement = select(Prompt).where(
            Prompt.is_active,
        )

        if user_id is not None:
            statement = statement.where(Prompt.user_id == user_id)
        else:
            statement = statement.where(col(Prompt.user_id).is_(None))

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

    def get_prompt_statistics(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """Return prompt-answer analytics for one writer.

        A prompt answer is a Moment with a linked prompt. The aggregation is
        deliberately based on those Moments (rather than ``Prompt.usage_count``),
        which is a legacy global counter and cannot describe one writer.
        """
        rows = list(
            self.session.exec(
                select(
                    col(Moment.prompt_id),
                    col(Moment.logged_date_tz),
                    col(Prompt.category),
                    col(Prompt.text),
                )
                .join(Prompt, col(Moment.prompt_id) == col(Prompt.id))
                .where(Moment.user_id == user_id)
            )
        )

        if not rows:
            return {
                "prompts_answered": 0,
                "total_answers": 0,
                "current_streak": 0,
                "favorite_categories": [],
                "completion_trend": [],
            }

        prompt_counts: Counter[uuid.UUID] = Counter()
        category_counts: Counter[str] = Counter()
        week_counts: Counter = Counter()
        prompt_texts: dict[uuid.UUID, str] = {}
        answered_dates = set()

        for prompt_id, logged_date, category, text in rows:
            if prompt_id is None:
                continue
            prompt_counts[prompt_id] += 1
            prompt_texts[prompt_id] = text
            category_counts[category or "uncategorized"] += 1
            answered_dates.add(logged_date)
            week_counts[logged_date - timedelta(days=logged_date.weekday())] += 1

        # A historical run is useful in the trend, but it is not a *current*
        # streak. Resolve "today" in the writer's timezone, just as the daily
        # prompt does, so a date rollover is never judged by the server clock.
        from app.core.time_utils import local_date_for_user
        from app.services.user_service import UserService

        user_tz = UserService(self.session).get_user_timezone(user_id)
        today = local_date_for_user(utc_now(), user_tz)
        ordered_dates = sorted(answered_dates, reverse=True)
        current_streak = 0
        if ordered_dates and ordered_dates[0] in {
            today,
            today - timedelta(days=1),
        }:
            current_streak = 1
            previous = ordered_dates[0]
            for answered_date in ordered_dates[1:]:
                if previous - answered_date != timedelta(days=1):
                    break
                current_streak += 1
                previous = answered_date

        most_used_id, most_used_count = max(
            prompt_counts.items(), key=lambda item: (item[1], str(item[0]))
        )
        return {
            "prompts_answered": len(prompt_counts),
            "total_answers": sum(prompt_counts.values()),
            "current_streak": current_streak,
            "favorite_categories": [
                {"category": category, "answered_count": count}
                for category, count in sorted(
                    category_counts.items(), key=lambda item: (-item[1], item[0])
                )
            ],
            "completion_trend": [
                {"week_start": week_start, "answered_count": count}
                for week_start, count in sorted(week_counts.items())
            ],
            "most_used_prompt": {
                "id": most_used_id,
                "text": prompt_texts[most_used_id],
                "answered_count": most_used_count,
            },
        }

    def get_prompts_by_category(
        self, category: str, user_id: Optional[uuid.UUID] = None
    ) -> List[Prompt]:
        """Get prompts by category."""
        return self.get_all_prompts(user_id=user_id, category=category, limit=100)

    def get_prompts_by_difficulty(
        self, difficulty_level: int, user_id: Optional[uuid.UUID] = None
    ) -> List[Prompt]:
        """Get prompts by difficulty level."""
        return self.get_all_prompts(
            user_id=user_id, difficulty_level=difficulty_level, limit=100
        )

    def search_prompts(
        self, query: str, user_id: Optional[uuid.UUID] = None
    ) -> List[Prompt]:
        """Search prompts by text content (excludes soft-deleted)."""
        statement = select(Prompt).where(
            Prompt.is_active, col(Prompt.text).ilike(f"%{query}%")
        )

        if user_id is not None:
            statement = statement.where(Prompt.user_id == user_id)
        else:
            statement = statement.where(col(Prompt.user_id).is_(None))

        statement = statement.order_by(col(Prompt.created_at).desc())
        return list(self.session.exec(statement))

    def bulk_update_prompts(
        self, user_id: uuid.UUID, updates: List[Dict[str, Any]]
    ) -> List[Prompt]:
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
            prompt_id = update_data.get("id")
            if not prompt_id:
                continue

            # Get the prompt
            statement = select(Prompt).where(
                Prompt.id == prompt_id, Prompt.user_id == user_id, Prompt.is_active
            )
            prompt = self.session.exec(statement).first()

            if not prompt:
                continue

            # Update fields
            if "text" in update_data:
                prompt.text = update_data["text"]
            if "category" in update_data:
                prompt.category = update_data["category"]
            if "difficulty_level" in update_data:
                prompt.difficulty_level = update_data["difficulty_level"]
            if "estimated_time_minutes" in update_data:
                prompt.estimated_time_minutes = update_data["estimated_time_minutes"]

            prompt.updated_at = utc_now()
            self.session.add(prompt)
            updated_prompts.append(prompt)

        self.session.commit()
        return updated_prompts

    def bulk_delete_prompts(
        self, user_id: uuid.UUID, prompt_ids: List[uuid.UUID]
    ) -> int:
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
                Prompt.id == prompt_id, Prompt.user_id == user_id, Prompt.is_active
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
