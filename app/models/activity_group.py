"""
Activity Group model for grouping activities.
"""
import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, Column, ForeignKey
from sqlmodel import Field, Index, Relationship

from .base import BaseModel

if TYPE_CHECKING:
    from .activity import Activity
    from .user import User


class ActivityGroup(BaseModel, table=True):
    """
    User-defined groups for activities (e.g., "Health", "Work", "Hobbies").
    """
    __tablename__ = "activity_group"

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
    user: "User" = Relationship(back_populates="activity_groups")
    activities: List["Activity"] = Relationship(
        back_populates="group",
        sa_relationship_kwargs={"order_by": "Activity.position"}
    )

    # Table constraints and indexes
    __table_args__ = (
        Index('idx_activity_group_user_name', 'user_id', 'name', unique=True),
    )
