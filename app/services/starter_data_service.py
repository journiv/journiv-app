"""
Starter data seeding service.
"""
import uuid
from typing import Any, cast

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, select

from app.core.logging_config import log_error
from app.core.starter_data import (
    STARTER_ACTIVITY_GROUPS,
    STARTER_GOAL,
    STARTER_GOAL_CATEGORY,
    STARTER_MOOD_GROUP,
    STARTER_MOODS,
)
from app.models.activity import Activity
from app.models.activity_group import ActivityGroup
from app.models.enums import GoalFrequency, GoalType
from app.models.goal import Goal
from app.models.goal_category import GoalCategory
from app.models.mood import Mood
from app.models.mood_group import MoodGroup, MoodGroupLink


class StarterDataService:
    """Idempotent starter metadata seeding."""

    def __init__(self, session: Session):
        self.session = session

    def ensure_user_seeded(self, user_id: uuid.UUID, *, commit: bool = True) -> None:
        """Ensure the user has all starter metadata records exactly once."""
        try:
            mood_group_id = self._ensure_mood_group(user_id)
            self._ensure_moods(user_id, mood_group_id)
            self._ensure_activity_groups(user_id)
            goal_category_id = self._ensure_goal_category(user_id)
            self._ensure_goal(user_id, goal_category_id)
            if commit:
                self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    def _ensure_mood_group(self, user_id: uuid.UUID) -> uuid.UUID:
        stable_key = STARTER_MOOD_GROUP["stable_key"]
        existing = self.session.exec(
            select(MoodGroup).where(
                col(MoodGroup.user_id) == user_id,
                col(MoodGroup.stable_key) == stable_key,
            )
        ).first()
        if existing:
            return existing.id

        group = MoodGroup(
            user_id=user_id,
            stable_key=stable_key,
            name=STARTER_MOOD_GROUP["name"],
            icon=STARTER_MOOD_GROUP["icon"],
            color_value=STARTER_MOOD_GROUP["color_value"],
            position=STARTER_MOOD_GROUP["position"],
        )
        self.session.add(group)
        self.session.flush()
        return group.id

    def _ensure_moods(self, user_id: uuid.UUID, mood_group_id: uuid.UUID) -> None:
        stable_keys = [m["stable_key"] for m in STARTER_MOODS]
        existing_moods = self.session.exec(
            select(Mood).where(
                col(Mood.user_id) == user_id,
                col(Mood.stable_key).in_(stable_keys),
            )
        ).all()
        moods_by_stable_key = {mood.stable_key: mood for mood in existing_moods}

        created_moods: list[Mood] = []
        for mood_data in STARTER_MOODS:
            mood = moods_by_stable_key.get(mood_data["stable_key"])
            if mood is not None:
                continue
            mood = Mood(
                user_id=user_id,
                stable_key=mood_data["stable_key"],
                key=mood_data["key"],
                name=mood_data["name"],
                icon=mood_data["icon"],
                color_value=mood_data["color_value"],
                category=mood_data["category"],
                score=mood_data["score"],
                position=mood_data["position"],
                is_active=True,
            )
            self.session.add(mood)
            created_moods.append(mood)
            moods_by_stable_key[mood_data["stable_key"]] = mood

        if created_moods:
            self.session.flush()

        mood_ids = [mood.id for mood in moods_by_stable_key.values()]
        existing_links = self.session.exec(
            select(MoodGroupLink).where(
                col(MoodGroupLink.mood_group_id) == mood_group_id,
                col(MoodGroupLink.mood_id).in_(mood_ids),
            )
        ).all()
        linked_mood_ids = {link.mood_id for link in existing_links}

        for mood_data in STARTER_MOODS:
            mood = moods_by_stable_key[mood_data["stable_key"]]
            if mood.id in linked_mood_ids:
                continue
            self.session.add(
                MoodGroupLink(
                    mood_group_id=mood_group_id,
                    mood_id=mood.id,
                    position=mood_data["position"],
                )
            )

    def _ensure_activity_groups(self, user_id: uuid.UUID) -> None:
        group_data_list = cast(list[dict[str, Any]], STARTER_ACTIVITY_GROUPS)
        group_stable_keys = [group_data["stable_key"] for group_data in group_data_list]
        existing_groups = self.session.exec(
            select(ActivityGroup).where(
                col(ActivityGroup.user_id) == user_id,
                col(ActivityGroup.stable_key).in_(group_stable_keys),
            )
        ).all()
        groups_by_stable_key = {group.stable_key: group for group in existing_groups}

        for group_data in group_data_list:
            if group_data["stable_key"] in groups_by_stable_key:
                continue
            group = ActivityGroup(
                user_id=user_id,
                stable_key=group_data["stable_key"],
                name=group_data["name"],
                icon=group_data["icon"],
                color_value=group_data["color_value"],
                position=group_data["position"],
            )
            self.session.add(group)
            self.session.flush()
            groups_by_stable_key[group_data["stable_key"]] = group

        all_activity_data = [
            activity_data
            for group_data in group_data_list
            for activity_data in cast(list[dict[str, Any]], group_data["activities"])
        ]
        activity_stable_keys = [activity_data["stable_key"] for activity_data in all_activity_data]
        existing_activities = self.session.exec(
            select(Activity).where(
                col(Activity.user_id) == user_id,
                col(Activity.stable_key).in_(activity_stable_keys),
            )
        ).all()
        existing_activity_keys = {activity.stable_key for activity in existing_activities}

        for group_data in group_data_list:
            group = groups_by_stable_key[group_data["stable_key"]]
            for activity_data in cast(list[dict[str, Any]], group_data["activities"]):
                if activity_data["stable_key"] in existing_activity_keys:
                    continue
                self.session.add(
                    Activity(
                        user_id=user_id,
                        group_id=group.id,
                        stable_key=activity_data["stable_key"],
                        name=activity_data["name"],
                        icon=activity_data["icon"],
                        color=activity_data["color"],
                        position=activity_data["position"],
                    )
                )

    def _ensure_goal_category(self, user_id: uuid.UUID) -> uuid.UUID:
        stable_key = STARTER_GOAL_CATEGORY["stable_key"]
        category = self.session.exec(
            select(GoalCategory).where(
                col(GoalCategory.user_id) == user_id,
                col(GoalCategory.stable_key) == stable_key,
            )
        ).first()
        if category:
            return category.id

        category = GoalCategory(
            user_id=user_id,
            stable_key=stable_key,
            name=STARTER_GOAL_CATEGORY["name"],
            icon=STARTER_GOAL_CATEGORY["icon"],
            color_value=STARTER_GOAL_CATEGORY["color_value"],
            position=STARTER_GOAL_CATEGORY["position"],
        )
        self.session.add(category)
        self.session.flush()
        return category.id

    def _ensure_goal(self, user_id: uuid.UUID, category_id: uuid.UUID) -> None:
        stable_key = STARTER_GOAL["stable_key"]
        existing = self.session.exec(
            select(Goal).where(
                col(Goal.user_id) == user_id,
                col(Goal.stable_key) == stable_key,
            )
        ).first()
        if existing:
            return

        goal = Goal(
            user_id=user_id,
            category_id=category_id,
            stable_key=stable_key,
            title=STARTER_GOAL["title"],
            icon=STARTER_GOAL.get("icon"),
            goal_type=GoalType(STARTER_GOAL["goal_type"]),
            frequency_type=GoalFrequency(STARTER_GOAL["frequency_type"]),
            target_count=STARTER_GOAL["target_count"],
            position=STARTER_GOAL["position"],
            is_paused=False,
            archived_at=None,
        )
        self.session.add(goal)
