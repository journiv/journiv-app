"""
Mood service for handling mood-related operations.
"""
import re
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, func, select

from app.core.db_utils import normalize_uuid_list
from app.core.exceptions import (
    MoodAlreadyExistsError,
    MoodNotFoundError,
    ValidationError,
)
from app.core.logging_config import log_error
from app.core.time_utils import utc_now
from app.models.enums import MoodCategory
from app.models.moment import Moment, MomentMoodActivity
from app.models.mood import Mood
from app.models.mood_group import MoodGroup, MoodGroupLink
from app.models.user_mood_preference import UserMoodPreference

DEFAULT_MOOD_PAGE_LIMIT = 50
MAX_MOOD_PAGE_LIMIT = 100


class MoodService:
    """Service class for mood operations."""

    def __init__(self, session: Session):
        self.session = session

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
    def _category_from_score(score: int) -> str:
        if score >= 4:
            return MoodCategory.POSITIVE.value
        if score <= 2:
            return MoodCategory.NEGATIVE.value
        return MoodCategory.NEUTRAL.value

    @staticmethod
    def _tier_group_name(score: int) -> str:
        if score >= 5:
            return "Very Positive"
        if score == 4:
            return "Positive"
        if score == 3:
            return "Neutral"
        if score == 2:
            return "Negative"
        return "Very Negative"

    @staticmethod
    def _slugify_key(name: str) -> str:
        normalized = name.strip().lower()
        normalized = re.sub(r"\s+", "-", normalized)
        normalized = re.sub(r"[^a-z0-9-]", "", normalized)
        normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
        return normalized

    def _generate_unique_key(self, user_id: uuid.UUID, name: str) -> str:
        base_key = self._slugify_key(name) or "mood"
        base_key = base_key[:50]
        candidate = base_key
        suffix = 2
        while self.session.exec(
            select(Mood.id).where(
                (col(Mood.user_id) == user_id) | (col(Mood.user_id).is_(None)),
                col(Mood.key) == candidate,
            )
        ).first():
            suffix_value = f"-{suffix}"
            max_base_len = max(1, 50 - len(suffix_value))
            candidate = f"{base_key[:max_base_len]}{suffix_value}"
            suffix += 1
        return candidate

    def _get_tier_group_id(self, score: int) -> Optional[uuid.UUID]:
        group_name = self._tier_group_name(score)
        statement = select(MoodGroup.id).where(
            col(MoodGroup.user_id).is_(None),
            col(MoodGroup.name) == group_name,
        )
        return self.session.exec(statement).first()

    def _ensure_tier_group_link(self, mood: Mood) -> None:
        group_id = self._get_tier_group_id(mood.score)
        if not group_id:
            return
        existing_link = self.session.exec(
            select(MoodGroupLink)
            .join(
                MoodGroup,
                col(MoodGroupLink.mood_group_id) == col(MoodGroup.id),
            )
            .where(
                col(MoodGroupLink.mood_id) == mood.id,
                col(MoodGroup.user_id).is_(None),
            )
        ).first()
        if existing_link and existing_link.mood_group_id == group_id:
            if existing_link.position != mood.position:
                existing_link.position = mood.position
            return
        if existing_link:
            self.session.delete(existing_link)
        link = MoodGroupLink(
            mood_group_id=group_id,
            mood_id=mood.id,
            position=mood.position,
        )
        self.session.add(link)

    def _commit(self) -> None:
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    def get_moods_for_user(
        self,
        user_id: uuid.UUID,
        category: Optional[str] = None,
        include_hidden: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get moods visible to a user (system + user-defined), optionally filtered."""
        normalized_category = self._normalize_category(category) if category else None
        statement = (
            select(Mood, UserMoodPreference.is_hidden, UserMoodPreference.sort_order)
            .outerjoin(
                UserMoodPreference,
                (col(UserMoodPreference.mood_id) == col(Mood.id))
                & (col(UserMoodPreference.user_id) == user_id),
            )
            .where(
                col(Mood.is_active).is_(True),
                (col(Mood.user_id).is_(None) | (col(Mood.user_id) == user_id)),
            )
        )
        if normalized_category:
            statement = statement.where(col(Mood.category) == normalized_category)
        if not include_hidden:
            statement = statement.where(
                (col(UserMoodPreference.is_hidden).is_(None))
                | (col(UserMoodPreference.is_hidden).is_(False))
            )

        statement = statement.order_by(
            func.coalesce(
                col(UserMoodPreference.sort_order),
                col(Mood.position),
            ).asc(),
            col(Mood.name).asc(),
        )
        rows = list(self.session.exec(statement))
        moods: List[Dict[str, Any]] = []
        for mood, is_hidden, sort_order in rows:
            moods.append(
                {
                    "id": mood.id,
                    "name": mood.name,
                    "key": mood.key,
                    "icon": mood.icon,
                    "color_value": mood.color_value,
                    "category": mood.category,
                    "score": mood.score,
                    "position": mood.position,
                    "is_active": mood.is_active,
                    "user_id": mood.user_id,
                    "created_at": mood.created_at,
                    "updated_at": mood.updated_at,
                    "is_hidden": bool(is_hidden) if is_hidden is not None else False,
                    "sort_order": sort_order,
                }
            )
        return moods

    def get_mood_by_id(self, mood_id: uuid.UUID) -> Optional[Mood]:
        """Get a mood by ID."""
        statement = select(Mood).where(Mood.id == mood_id)
        return self.session.exec(statement).first()

    def find_mood_by_name(self, mood_name: str) -> Optional[Mood]:
        """Find a mood by name (case-insensitive)."""
        if not mood_name:
            raise ValidationError("Mood name cannot be empty")
        normalized = mood_name.strip().lower()
        statement = select(Mood).where(func.lower(Mood.name) == normalized)
        return self.session.exec(statement).first()

    def create_user_mood(self, user_id: uuid.UUID, data: Dict[str, Any]) -> Mood:
        """Create a user-defined mood."""
        name = data.get("name", "").strip()
        if not name:
            raise ValidationError("Mood name cannot be empty")

        existing = self.session.exec(
            select(Mood).where(
                Mood.user_id == user_id,
                func.lower(Mood.name) == name.lower(),
            )
        ).first()
        if existing:
            raise MoodAlreadyExistsError("Mood name already exists")

        score_raw = data.get("score", 3)
        try:
            score = int(score_raw) if score_raw is not None else 3
        except (TypeError, ValueError) as exc:
            raise ValidationError("Mood score must be between 1 and 5") from exc
        if score < 1 or score > 5:
            raise ValidationError("Mood score must be between 1 and 5")
        category = self._category_from_score(score)
        position = data.get("position")
        if position is None:
            max_position = self.session.exec(
                select(func.coalesce(func.max(Mood.position), 0)).where(
                    (col(Mood.user_id) == user_id) | (col(Mood.user_id).is_(None))
                )
            ).one()
            position = int(max_position) + 10

        key = self._generate_unique_key(user_id, name)
        mood = Mood(
            name=name,
            key=key,
            icon=data.get("icon"),
            color_value=data.get("color_value"),
            score=score,
            category=category,
            position=position,
            user_id=user_id,
            is_active=True,
        )
        self.session.add(mood)
        self.session.flush()
        self._ensure_tier_group_link(mood)
        self._commit()
        self.session.refresh(mood)
        return mood

    def update_user_mood(self, user_id: uuid.UUID, mood: Mood, data: Dict[str, Any]) -> Mood:
        """Update a user-defined mood."""
        if mood.user_id != user_id:
            raise MoodNotFoundError("Mood not found")

        if "name" in data and data["name"] is not None:
            name = data["name"].strip()
            if not name:
                raise ValidationError("Mood name cannot be empty")
            duplicate = self.session.exec(
                select(Mood).where(
                    Mood.user_id == user_id,
                    func.lower(Mood.name) == name.lower(),
                    Mood.id != mood.id,
                )
            ).first()
            if duplicate:
                raise MoodAlreadyExistsError("Mood name already exists")
            mood.name = name

        if "icon" in data and data["icon"] is not None:
            mood.icon = data["icon"]
        if "color_value" in data and data["color_value"] is not None:
            try:
                mood.color_value = int(data["color_value"])
            except (TypeError, ValueError) as exc:
                raise ValidationError("color_value must be an integer") from exc
        if "score" in data and data["score"] is not None:
            try:
                score = int(data["score"])
            except (TypeError, ValueError) as exc:
                raise ValidationError("Mood score must be between 1 and 5") from exc
            if score < 1 or score > 5:
                raise ValidationError("Mood score must be between 1 and 5")
            mood.score = score
            mood.category = self._category_from_score(score)
        if "position" in data and data["position"] is not None:
            try:
                mood.position = int(data["position"])
            except (TypeError, ValueError) as exc:
                raise ValidationError("position must be an integer") from exc
        if "is_active" in data and data["is_active"] is not None:
            mood.is_active = bool(data["is_active"])

        mood.updated_at = utc_now()
        self.session.flush()
        self._ensure_tier_group_link(mood)
        self._commit()
        self.session.refresh(mood)
        return mood

    def delete_user_mood(self, user_id: uuid.UUID, mood: Mood) -> None:
        """Soft delete a user-defined mood."""
        if mood.user_id != user_id:
            raise MoodNotFoundError("Mood not found")
        mood.is_active = False
        mood.updated_at = utc_now()
        self._commit()

    def set_mood_hidden(self, user_id: uuid.UUID, mood_id: uuid.UUID, is_hidden: bool) -> None:
        """Set per-user mood visibility."""
        mood = self.get_mood_by_id(mood_id)
        if not mood:
            raise MoodNotFoundError("Mood not found")
        if not mood.is_active or (mood.user_id is not None and mood.user_id != user_id):
            raise MoodNotFoundError("Mood not found")
        preference = self.session.exec(
            select(UserMoodPreference).where(
                UserMoodPreference.user_id == user_id,
                UserMoodPreference.mood_id == mood_id,
            )
        ).first()
        if preference:
            preference.is_hidden = is_hidden
            preference.updated_at = utc_now()
        else:
            preference = UserMoodPreference(
                user_id=user_id,
                mood_id=mood_id,
                sort_order=mood.position,
                is_hidden=is_hidden,
            )
            self.session.add(preference)
        self._commit()

    def reorder_moods(self, user_id: uuid.UUID, mood_ids: List[uuid.UUID]) -> None:
        """Persist per-user mood ordering for the unified list."""
        if not mood_ids:
            return

        allowed = set(
            self.session.exec(
                select(Mood.id).where(
                    col(Mood.is_active).is_(True),
                    (col(Mood.user_id).is_(None)) | (col(Mood.user_id) == user_id),
                )
            ).all()
        )
        missing = [mood_id for mood_id in mood_ids if mood_id not in allowed]
        if missing:
            raise MoodNotFoundError("One or more moods not found")

        existing = {
            pref.mood_id: pref
            for pref in self.session.exec(
                select(UserMoodPreference).where(
                    UserMoodPreference.user_id == user_id,
                    col(UserMoodPreference.mood_id).in_(normalize_uuid_list(mood_ids)),
                )
            ).all()
        }

        for index, mood_id in enumerate(mood_ids):
            pref = existing.get(mood_id)
            if pref:
                pref.sort_order = index
                pref.updated_at = utc_now()
            else:
                self.session.add(
                    UserMoodPreference(
                        user_id=user_id,
                        mood_id=mood_id,
                        sort_order=index,
                        is_hidden=False,
                    )
                )

        self._commit()

    def get_mood_statistics(
        self,
        user_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get mood statistics for a user based on moments."""
        if not end_date:
            end_date = utc_now().date()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        mood_counts = list(
            self.session.exec(
                select(
                    Mood.name,
                    Mood.category,
                    func.count(MomentMoodActivity.id).label("count"),
                )
                .join(MomentMoodActivity, Mood.id == MomentMoodActivity.mood_id)
                .join(Moment, Moment.id == MomentMoodActivity.moment_id)
                .where(
                    col(Moment.user_id) == user_id,
                    col(Mood.is_active).is_(True),
                    col(Moment.logged_date) >= start_date,
                    col(Moment.logged_date) <= end_date,
                )
                .group_by(Mood.name, Mood.category)
                .order_by(func.count(MomentMoodActivity.id).desc())
            )
        )

        daily_moods = list(
            self.session.exec(
                select(
                    col(Moment.logged_date).label("date"),
                    Mood.category,
                    func.count(MomentMoodActivity.id).label("count"),
                )
                .join(MomentMoodActivity, Moment.id == MomentMoodActivity.moment_id)
                .join(Mood, Mood.id == MomentMoodActivity.mood_id)
                .where(
                    col(Moment.user_id) == user_id,
                    col(Moment.logged_date) >= start_date,
                    col(Moment.logged_date) <= end_date,
                )
                .group_by(col(Moment.logged_date), Mood.category)
                .order_by(col(Moment.logged_date))
            )
        )

        most_frequent = mood_counts[0] if mood_counts else None
        total_logs = sum(count.count for count in mood_counts) if mood_counts else 0
        mood_distribution: Dict[str, int] = {}
        for mood_count in mood_counts:
            mood_distribution[mood_count.category] = (
                mood_distribution.get(mood_count.category, 0) + mood_count.count
            )
        if total_logs > 0:
            for category in mood_distribution:
                mood_distribution[category] = round(
                    (mood_distribution[category] / total_logs) * 100, 2
                )

        return {
            "total_logs": total_logs,
            "date_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "mood_distribution": mood_distribution,
            "most_frequent_mood": {
                "name": most_frequent.name,
                "category": most_frequent.category,
                "count": most_frequent.count,
            }
            if most_frequent
            else None,
            "mood_counts": [
                {
                    "mood": count.name,
                    "category": count.category,
                    "count": count.count,
                }
                for count in mood_counts
            ],
            "daily_trends": [
                {
                    "date": str(trend.date),
                    "category": trend.category,
                    "count": trend.count,
                }
                for trend in daily_moods
            ],
        }

    def get_mood_streak(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """Get current mood logging streak for a user based on moments."""
        mood_dates = list(
            self.session.exec(
                select(col(Moment.logged_date))
                .where(
                    Moment.user_id == user_id,
                    col(Moment.primary_mood_id).is_not(None),
                )
                .group_by(col(Moment.logged_date))
                .order_by(col(Moment.logged_date).desc())
            )
        )

        if not mood_dates:
            return {
                "current_streak": 0,
                "total_days_logged": 0,
                "last_logged_date": None,
            }

        latest_date = mood_dates[0]
        today = date.today()
        if latest_date < (today - timedelta(days=1)):
            return {
                "current_streak": 0,
                "total_days_logged": len(mood_dates),
                "last_logged_date": latest_date,
            }

        current_streak = 1
        expected_date = latest_date
        for i in range(1, len(mood_dates)):
            expected_date = expected_date - timedelta(days=1)
            if mood_dates[i] == expected_date:
                current_streak += 1
            else:
                break

        return {
            "current_streak": current_streak,
            "total_days_logged": len(mood_dates),
            "last_logged_date": latest_date,
        }
