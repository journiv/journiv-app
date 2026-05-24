"""
Person-Group link model.
"""
import uuid

from sqlalchemy import Column, ForeignKey, Index
from sqlmodel import Field, SQLModel

from .base import TimestampMixin


class PersonGroupLink(TimestampMixin, SQLModel, table=True):
    """
    Link table for many-to-many relationship between people and person groups.
    """
    __tablename__ = "person_group_link"

    person_group_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("person_group.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    person_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("person.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )

    __table_args__ = (
        Index("idx_person_group_link_person_id", "person_id"),
    )
