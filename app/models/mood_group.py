"""
Mood group models (collections) with many-to-many links to moods.
"""
import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String
from sqlmodel import Field, Index, Relationship

from .base import BaseModel

if TYPE_CHECKING:
    from .mood import Mood
    from .user import User


class MoodGroup(BaseModel, table=True):
    """
    Mood group/collection for organizing moods in the UI.
    """
    __tablename__ = "mood_group"

    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    name: str = Field(sa_column=Column(String(100), nullable=False))
    icon: Optional[str] = Field(default=None, max_length=64)
    color_value: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    position: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    stable_key: Optional[str] = Field(default=None, max_length=100, index=True)

    user: Optional["User"] = Relationship(back_populates="mood_groups")
    links: List["MoodGroupLink"] = Relationship(
        back_populates="group",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    __table_args__ = (
        Index("idx_mood_group_user_position", "user_id", "position"),
        Index("uq_mood_group_user_stable_key", "user_id", "stable_key", unique=True),
    )


class MoodGroupLink(BaseModel, table=True):
    """
    Link table for many-to-many mood <-> mood_group, with per-group ordering.
    """
    __tablename__ = "mood_group_link"

    mood_group_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("mood_group.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    mood_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("mood.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    position: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))

    group: "MoodGroup" = Relationship(back_populates="links")
    mood: "Mood" = Relationship(back_populates="group_links")

    __table_args__ = (
        Index("uq_mood_group_link_group_mood", "mood_group_id", "mood_id", unique=True),
        Index("idx_mood_group_link_group_position", "mood_group_id", "position"),
    )
