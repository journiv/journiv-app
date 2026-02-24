"""
Mood group service for managing mood collections.
"""
import uuid
from typing import Iterable, List, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, col, func, select

from app.core.db_utils import normalize_uuid_list
from app.core.logging_config import log_error, log_info
from app.models.mood import Mood
from app.models.mood_group import MoodGroup, MoodGroupLink
from app.schemas.mood_group import MoodGroupCreate, MoodGroupUpdate


class MoodGroupNotFoundError(Exception):
    """Raised when a mood group is not found."""


class MoodGroupService:
    """Service class for mood group operations."""

    def __init__(self, session: Session):
        self.session = session

    def _commit(self) -> None:
        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

    @staticmethod
    def _ensure_unique_ids(ids: list[uuid.UUID], *, label: str) -> None:
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate {label} IDs are not allowed")

    def _validate_mood_ids(self, user_id: uuid.UUID, mood_ids: Iterable[uuid.UUID]) -> None:
        ids = list(dict.fromkeys(mood_ids))
        if not ids:
            return
        rows = self.session.exec(
            select(Mood.id).where(
                col(Mood.id).in_(normalize_uuid_list(ids)),
                col(Mood.is_active).is_(True),
                col(Mood.user_id) == user_id,
            )
        ).all()
        if len(rows) != len(set(ids)):
            raise ValueError("One or more moods are invalid or not accessible")

    def _next_group_position(self, user_id: uuid.UUID) -> int:
        max_position = self.session.exec(
            select(func.coalesce(func.max(MoodGroup.position), 0)).where(
                MoodGroup.user_id == user_id
            )
        ).one()
        return int(max_position) + 10

    def _ensure_unique_name(self, user_id: uuid.UUID, name: str, exclude_id: Optional[uuid.UUID] = None) -> None:
        normalized = name.strip().lower()
        statement = select(MoodGroup.id).where(
            MoodGroup.user_id == user_id,
            func.lower(MoodGroup.name) == normalized,
        )
        if exclude_id is not None:
            statement = statement.where(MoodGroup.id != exclude_id)
        exists = self.session.exec(statement).first()
        if exists:
            raise ValueError(f"Mood group with name '{name}' already exists")

    def create_group(self, user_id: uuid.UUID, data: MoodGroupCreate) -> MoodGroup:
        self._ensure_unique_name(user_id, data.name)
        position = data.position if data.position is not None else self._next_group_position(user_id)
        group = MoodGroup(
            user_id=user_id,
            name=data.name,
            icon=data.icon,
            color_value=data.color_value,
            position=position,
        )
        try:
            self.session.add(group)
            if data.mood_ids:
                self._validate_mood_ids(user_id, data.mood_ids)
                self._replace_group_links(group.id, data.mood_ids)
            self._commit()
            self.session.refresh(group)
        except ValueError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        except IntegrityError as exc:
            self.session.rollback()
            log_error(exc)
            raise ValueError(f"Mood group with name '{data.name}' already exists") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Mood group created: {group.id} for user {user_id}")
        return group

    def get_group_by_id(self, group_id: uuid.UUID) -> Optional[MoodGroup]:
        return self.session.exec(
            select(MoodGroup).where(MoodGroup.id == group_id)
        ).first()

    def get_group_with_moods(
        self,
        user_id: uuid.UUID,
        group_id: uuid.UUID,
    ) -> dict:
        group = self.get_group_by_id(group_id)
        if not group or group.user_id != user_id:
            raise MoodGroupNotFoundError(f"Mood group {group_id} not found")

        moods_map = self._get_moods_for_groups(
            user_id,
            [group_id],
        )
        return {
            **group.model_dump(),
            "position": group.position,
            "moods": moods_map.get(group_id, []),
        }

    def get_groups_for_user(
        self,
        user_id: uuid.UUID,
    ) -> List[dict]:
        groups = self.session.exec(
            select(MoodGroup)
            .where(
                col(MoodGroup.user_id) == user_id
            )
            .order_by(col(MoodGroup.position), func.lower(MoodGroup.name))
        ).all()

        moods_map = self._get_moods_for_groups(
            user_id,
            [group.id for group in groups],
        )

        result: List[dict] = []
        for group in groups:
            moods = moods_map.get(group.id, [])
            result.append(
                {
                    **group.model_dump(),
                    "position": group.position,
                    "moods": moods,
                }
            )

        return result

    def update_group(
        self,
        group_id: uuid.UUID,
        user_id: uuid.UUID,
        data: MoodGroupUpdate,
    ) -> MoodGroup:
        group = self.get_group_by_id(group_id)
        if not group or group.user_id != user_id:
            raise MoodGroupNotFoundError(f"Mood group {group_id} not found")

        update_data = data.model_dump(exclude_unset=True, exclude={"mood_ids"})
        if "name" in update_data and update_data["name"]:
            self._ensure_unique_name(user_id, update_data["name"], exclude_id=group_id)
        for key, value in update_data.items():
            setattr(group, key, value)

        try:
            self.session.add(group)
            if data.mood_ids is not None:
                self._validate_mood_ids(user_id, data.mood_ids)
                self._replace_group_links(group.id, data.mood_ids)
            self._commit()
            self.session.refresh(group)
        except ValueError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Mood group updated: {group_id}")
        return group

    def delete_group(self, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
        group = self.get_group_by_id(group_id)
        if not group or group.user_id != user_id:
            raise MoodGroupNotFoundError(f"Mood group {group_id} not found")
        try:
            self.session.delete(group)
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Mood group deleted: {group_id}")

    def reorder_groups(self, user_id: uuid.UUID, updates: list[tuple[uuid.UUID, int]]) -> None:
        if not updates:
            return
        group_ids = [group_id for group_id, _ in updates]
        self._ensure_unique_ids(group_ids, label="group")
        groups = self.session.exec(
            select(MoodGroup).where(
                col(MoodGroup.user_id) == user_id,
                col(MoodGroup.id).in_(normalize_uuid_list(group_ids)),
            )
        ).all()
        if len(groups) != len(group_ids):
            raise MoodGroupNotFoundError("One or more mood groups not found")
        groups_by_id = {group.id: group for group in groups}
        try:
            for group_id, position in updates:
                group = groups_by_id[group_id]
                group.position = position
                self.session.add(group)
            self._commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Mood groups reordered for user {user_id}")

    def reorder_group_moods(self, user_id: uuid.UUID, group_id: uuid.UUID, mood_ids: list[uuid.UUID]) -> None:
        group = self.get_group_by_id(group_id)
        if not group:
            raise MoodGroupNotFoundError(f"Mood group {group_id} not found")
        if group.user_id != user_id:
            raise MoodGroupNotFoundError(f"Mood group {group_id} not found")
        self._ensure_unique_ids(mood_ids, label="mood")
        self._validate_mood_ids(user_id, mood_ids)
        links = self.session.exec(
            select(MoodGroupLink).where(
                col(MoodGroupLink.mood_group_id) == group_id,
                col(MoodGroupLink.mood_id).in_(normalize_uuid_list(mood_ids)),
            )
        ).all()
        if len(links) != len(mood_ids):
            raise ValueError("One or more moods do not belong to this mood group")
        link_map = {link.mood_id: link for link in links}
        for index, mood_id in enumerate(mood_ids):
            link = link_map.get(mood_id)
            if link:
                link.position = index
        try:
            for link in link_map.values():
                self.session.add(link)
            self._commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Mood group moods reordered for user {user_id}, group {group_id}")

    def _replace_group_links(self, group_id: uuid.UUID, mood_ids: Iterable[uuid.UUID]) -> None:
        mood_ids = list(dict.fromkeys(mood_ids))
        existing_links = self.session.exec(
            select(MoodGroupLink).where(MoodGroupLink.mood_group_id == group_id)
        ).all()
        existing_map = {link.mood_id: link for link in existing_links}
        keep_ids = set(mood_ids)

        for link in existing_links:
            if link.mood_id not in keep_ids:
                self.session.delete(link)

        for index, mood_id in enumerate(mood_ids):
            link = existing_map.get(mood_id)
            if link:
                link.position = index
            else:
                self.session.add(
                    MoodGroupLink(
                        mood_group_id=group_id,
                        mood_id=mood_id,
                        position=index,
                    )
                )
        # Caller is responsible for committing.

    def _get_moods_for_groups(
        self,
        user_id: uuid.UUID,
        group_ids: List[uuid.UUID],
    ) -> dict[uuid.UUID, List[dict]]:
        if not group_ids:
            return {}

        statement = (
            select(MoodGroupLink, Mood)
            .join(
                Mood,
                col(Mood.id) == col(MoodGroupLink.mood_id),
            )
            .where(
                col(MoodGroupLink.mood_group_id).in_(normalize_uuid_list(group_ids)),
                col(Mood.is_active).is_(True),
                col(Mood.user_id) == user_id,
            )
            .order_by(
                col(MoodGroupLink.mood_group_id),
                col(MoodGroupLink.position),
                col(Mood.name),
            )
        )

        rows = self.session.exec(statement).all()
        moods_map: dict[uuid.UUID, List[dict]] = {group_id: [] for group_id in group_ids}
        for link, mood in rows:
            moods_map.setdefault(link.mood_group_id, []).append(
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
                }
            )
        return moods_map
