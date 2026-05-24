"""
Moment-Person link model.
"""
import uuid

from sqlalchemy import Column, ForeignKey, Index
from sqlmodel import Field, SQLModel

from .base import TimestampMixin


class MomentPersonLink(TimestampMixin, SQLModel, table=True):
    """
    Link table for many-to-many relationship between moments and people.
    """
    __tablename__ = "moment_person_link"

    moment_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("moment.id", ondelete="CASCADE"),
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
        Index("idx_moment_person_link_person_moment", "person_id", "moment_id"),
    )
