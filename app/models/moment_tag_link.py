"""
Moment-Tag link model.
"""
import uuid

from sqlalchemy import Column, ForeignKey, Index
from sqlmodel import Field, SQLModel

from .base import TimestampMixin


class MomentTagLink(TimestampMixin, SQLModel, table=True):
    """
    Link table for many-to-many relationship between moments and tags.
    """
    __tablename__ = "moment_tag_link"

    moment_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("moment.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False
        )
    )
    tag_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("tag.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False
        )
    )

    # Table constraints and indexes
    __table_args__ = (
        Index('idx_moment_tag_link_tag_id', 'tag_id'),
    )
