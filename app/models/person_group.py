"""
Person Group model for grouping people.
"""
import uuid
from typing import TYPE_CHECKING, List, Optional

from pydantic import field_validator
from sqlalchemy import BigInteger, Column, ForeignKey
from sqlalchemy.orm import validates
from sqlmodel import CheckConstraint, Field, Index, Relationship, UniqueConstraint

from .base import BaseModel
from .person_group_link import PersonGroupLink

if TYPE_CHECKING:
    from .person import Person
    from .user import User


class PersonGroup(BaseModel, table=True):
    """
    User-defined groups for people (e.g., "Family", "Friends", "Work").
    """
    __tablename__ = "person_group"

    name: str = Field(..., min_length=1, max_length=100)
    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    color_value: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    icon: Optional[str] = Field(None, max_length=50)
    position: int = Field(default=0)
    stable_key: Optional[str] = Field(default=None, max_length=100, index=True)

    # Relations
    user: "User" = Relationship(back_populates="person_groups")
    people: List["Person"] = Relationship(
        back_populates="groups",
        link_model=PersonGroupLink,
    )

    # Table constraints and indexes
    __table_args__ = (
        Index("idx_person_group_user_name", "user_id", "name", unique=True),
        UniqueConstraint("user_id", "stable_key", name="uq_person_group_user_stable_key"),
        CheckConstraint("length(trim(name)) > 0", name="ck_person_group_name_non_empty"),
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return cls._clean_name(v)

    @validates("name")
    def validate_name_assignment(self, _key: str, value: str) -> str:
        return self._clean_name(value)

    @staticmethod
    def _clean_name(v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            raise ValueError("Group name cannot be empty")
        return cleaned
