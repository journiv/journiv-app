"""
Goal Category model for grouping goals.
"""
import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, Column, ForeignKey
from sqlmodel import Field, Index, Relationship

from .base import BaseModel

if TYPE_CHECKING:
    from .goal import Goal
    from .user import User


class GoalCategory(BaseModel, table=True):
    """
    User-defined categories for goals (e.g., "Health", "Work", "Mindfulness").
    """
    __tablename__ = "goal_category"

    name: str = Field(..., min_length=1, max_length=100)
    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )
    color_value: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True)
    )
    icon: Optional[str] = Field(None, max_length=50)
    position: int = Field(default=0, nullable=False)

    # Relations
    user: "User" = Relationship(back_populates="goal_categories")
    goals: List["Goal"] = Relationship(
        back_populates="category",
        sa_relationship_kwargs={"order_by": "Goal.position"}
    )

    __table_args__ = (
        Index('idx_goal_category_user_name', 'user_id', 'name', unique=True),
    )
