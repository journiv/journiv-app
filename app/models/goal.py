"""
Goal-related models for activity-based and manual goal tracking.
"""
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlmodel import CheckConstraint, Field, Index, Relationship

from app.core.time_utils import utc_now

from .base import BaseModel
from .enums import GoalFrequency, GoalLogSource, GoalLogStatus, GoalType

GOAL_TYPE_ENUM = SQLAlchemyEnum(
    GoalType,
    name="goal_type_enum",
    native_enum=True,
    values_callable=lambda x: [e.value for e in x],
)
GOAL_FREQUENCY_ENUM = SQLAlchemyEnum(
    GoalFrequency,
    name="goal_frequency_enum",
    native_enum=True,
    values_callable=lambda x: [e.value for e in x],
)
GOAL_LOG_STATUS_ENUM = SQLAlchemyEnum(
    GoalLogStatus,
    name="goal_log_status_enum",
    native_enum=True,
    values_callable=lambda x: [e.value for e in x],
)
GOAL_LOG_SOURCE_ENUM = SQLAlchemyEnum(
    GoalLogSource,
    name="goal_log_source_enum",
    native_enum=True,
    values_callable=lambda x: [e.value for e in x],
)

if TYPE_CHECKING:
    from .activity import Activity
    from .goal_category import GoalCategory
    from .moment import Moment
    from .user import User


class Goal(BaseModel, table=True):
    """
    User goal definition (optionally linked to an activity for auto-completion).
    """
    __tablename__ = "goal"

    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )
    activity_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("activity.id", ondelete="SET NULL"),
            nullable=True,
            index=True
        )
    )
    category_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("goal_category.id", ondelete="SET NULL"),
            nullable=True,
            index=True
        )
    )
    title: str = Field(sa_column=Column(String(200), nullable=False))
    goal_type: GoalType = Field(
        default=GoalType.ACHIEVE,
        sa_column=Column(
            GOAL_TYPE_ENUM,
            nullable=False,
            server_default="achieve",
        ),
    )
    frequency_type: GoalFrequency = Field(
        default=GoalFrequency.DAILY,
        sa_column=Column(
            GOAL_FREQUENCY_ENUM,
            nullable=False,
            server_default="daily",
        ),
    )
    target_count: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default="1"),
    )
    reminder_time: Optional[str] = Field(
        default=None,
        sa_column=Column(String(5), nullable=True),
    )
    is_paused: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    icon: Optional[str] = Field(default=None, max_length=64)
    color_value: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    position: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    archived_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    # Relations
    user: "User" = Relationship(back_populates="goals")
    activity: Optional["Activity"] = Relationship(back_populates="goals")
    category: Optional["GoalCategory"] = Relationship(back_populates="goals")
    logs: List["GoalLog"] = Relationship(
        back_populates="goal",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    __table_args__ = (
        CheckConstraint(
            "target_count >= 1",
            name="check_goal_target_count"
        ),
        Index("idx_goal_user_active", "user_id", "archived_at"),
        Index("idx_goal_user_position", "user_id", "position"),
        Index("idx_goal_user_category_position", "user_id", "category_id", "position"),
    )


class GoalLog(BaseModel, table=True):
    """
    A completion record for a goal on a specific day.
    """
    __tablename__ = "goal_log"

    goal_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("goal.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )
    logged_date: date = Field(
        sa_column=Column(Date, nullable=False, index=True)
    )
    period_start: date = Field(
        sa_column=Column(Date, nullable=False, index=True)
    )
    period_end: date = Field(
        sa_column=Column(Date, nullable=False, index=True)
    )
    status: GoalLogStatus = Field(
        default=GoalLogStatus.SUCCESS,
        sa_column=Column(
            GOAL_LOG_STATUS_ENUM,
            nullable=False,
            server_default="success",
        ),
    )
    count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    source: GoalLogSource = Field(
        default=GoalLogSource.AUTO,
        sa_column=Column(
            GOAL_LOG_SOURCE_ENUM,
            nullable=False,
            server_default="auto",
        ),
    )
    last_updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    moment_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("moment.id", ondelete="SET NULL"),
            nullable=True,
            index=True
        )
    )

    # Relations
    goal: "Goal" = Relationship(back_populates="logs")
    user: "User" = Relationship(back_populates="goal_logs")
    moment: Optional["Moment"] = Relationship(back_populates="goal_logs")

    __table_args__ = (
        Index("idx_goal_log_user_date", "user_id", "logged_date"),
        Index("idx_goal_log_goal_date", "goal_id", "logged_date"),
        UniqueConstraint("goal_id", "period_start", name="uq_goal_log_goal_period"),
    )


class GoalManualLog(BaseModel, table=True):
    """
    Manual override log for a goal on a specific date.
    """
    __tablename__ = "goal_manual_log"

    goal_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("goal.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    logged_date: date = Field(
        sa_column=Column(Date, nullable=False, index=True)
    )
    status: GoalLogStatus = Field(
        default=GoalLogStatus.SUCCESS,
        sa_column=Column(
            GOAL_LOG_STATUS_ENUM,
            nullable=False,
            server_default="success",
        ),
    )

    goal: "Goal" = Relationship()
    user: "User" = Relationship()

    __table_args__ = (
        Index("idx_goal_manual_log_goal_date", "goal_id", "logged_date"),
        Index("idx_goal_manual_log_user_date", "user_id", "logged_date"),
        UniqueConstraint("goal_id", "logged_date", name="uq_goal_manual_log_goal_date"),
    )
