"""
Goal Category service for managing goal categories.
"""
import uuid
from typing import List, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, col, func, select

from app.core.logging_config import log_error, log_info
from app.models.goal_category import GoalCategory
from app.schemas.goal_category import GoalCategoryCreate, GoalCategoryUpdate
from app.services.reorder_utils import apply_position_updates


class GoalCategoryNotFoundError(Exception):
    """Raised when a goal category is not found."""
    pass


class GoalCategoryService:
    """Service class for goal category operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_category(self, user_id: uuid.UUID, data: GoalCategoryCreate) -> GoalCategory:
        position = data.position
        if position is None:
            max_position = self.session.exec(
                select(func.coalesce(func.max(GoalCategory.position), 0)).where(
                    GoalCategory.user_id == user_id
                )
            ).one()
            position = int(max_position) + 10
        category = GoalCategory(
            user_id=user_id,
            name=data.name,
            color_value=data.color_value,
            icon=data.icon,
            position=position,
        )
        try:
            self.session.add(category)
            self.session.commit()
            self.session.refresh(category)
        except IntegrityError as exc:
            self.session.rollback()
            log_error(exc)
            if "idx_goal_category_user_name" in str(exc.orig):
                raise ValueError(f"Goal category with name '{category.name}' already exists") from exc
            raise ValueError("Database constraint violated") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Goal category created: {category.id} for user {user_id}")
        return category

    def get_user_categories(self, user_id: uuid.UUID) -> List[GoalCategory]:
        statement = (
            select(GoalCategory)
            .where(GoalCategory.user_id == user_id)
            .order_by(col(GoalCategory.position), col(GoalCategory.name))
        )
        categories = self.session.exec(statement).all()
        return list(categories)

    def get_category_by_id(self, category_id: uuid.UUID, user_id: uuid.UUID) -> Optional[GoalCategory]:
        statement = select(GoalCategory).where(
            GoalCategory.id == category_id,
            GoalCategory.user_id == user_id,
        )
        return self.session.exec(statement).first()

    def update_category(
        self,
        category_id: uuid.UUID,
        user_id: uuid.UUID,
        data: GoalCategoryUpdate,
    ) -> GoalCategory:
        category = self.get_category_by_id(category_id, user_id)
        if not category:
            raise GoalCategoryNotFoundError(f"Goal category {category_id} not found")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(category, key, value)

        try:
            self.session.add(category)
            self.session.commit()
            self.session.refresh(category)
        except IntegrityError as exc:
            self.session.rollback()
            log_error(exc)
            if "idx_goal_category_user_name" in str(exc.orig):
                raise ValueError(f"Goal category with name '{category.name}' already exists") from exc
            raise ValueError("Database constraint violated") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Goal category updated: {category_id}")
        return category

    def delete_category(self, category_id: uuid.UUID, user_id: uuid.UUID) -> None:
        category = self.get_category_by_id(category_id, user_id)
        if not category:
            raise GoalCategoryNotFoundError(f"Goal category {category_id} not found")
        try:
            self.session.delete(category)
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise
        else:
            log_info(f"Goal category deleted: {category_id}")

    def reorder_categories(self, user_id: uuid.UUID, updates: list[tuple[uuid.UUID, int]]) -> None:
        updated = apply_position_updates(self.session, GoalCategory, user_id, updates)
        if updated:
            log_info(f"Goal categories reordered for user {user_id}")
