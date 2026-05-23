"""
Person-related models.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from pydantic import field_validator
from sqlalchemy import Column, DateTime, ForeignKey
from sqlmodel import CheckConstraint, Field, Index, Relationship, UniqueConstraint

from .base import BaseModel

if TYPE_CHECKING:
    from .moment import Moment
    from .person_group import PersonGroup
    from .user import User

from .moment_person_link import MomentPersonLink
from .person_group_link import PersonGroupLink


class Person(BaseModel, table=True):
    """
    Person model for tracking people associated with moments.
    """
    __tablename__ = "person"

    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    name: str = Field(..., min_length=1, max_length=120, index=True)
    normalized_name: str = Field(..., min_length=1, max_length=120, index=True)
    nickname: Optional[str] = Field(default=None, max_length=120)
    note: Optional[str] = Field(default=None, max_length=1000)
    profile_image_path: Optional[str] = Field(default=None, max_length=512)
    archived_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )

    # Relations
    user: "User" = Relationship(back_populates="people")
    moments: List["Moment"] = Relationship(
        back_populates="people",
        link_model=MomentPersonLink,
    )
    groups: List["PersonGroup"] = Relationship(
        back_populates="people",
        link_model=PersonGroupLink,
    )

    __table_args__ = (
        Index("idx_person_user_archived_name", "user_id", "archived_at", "name"),
        UniqueConstraint("user_id", "normalized_name", name="uq_person_user_normalized_name"),
        CheckConstraint("length(name) > 0", name="check_person_name_not_empty"),
        CheckConstraint("length(normalized_name) > 0", name="check_person_normalized_name_not_empty"),
        CheckConstraint("normalized_name = lower(normalized_name)", name="check_person_normalized_name_lowercase"),
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            raise ValueError("Person name cannot be empty")
        return cleaned

    @field_validator("normalized_name")
    @classmethod
    def validate_normalized_name(cls, v: str) -> str:
        cleaned = (v or "").strip().lower()
        if not cleaned:
            raise ValueError("Normalized name cannot be empty")
        return cleaned

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None
