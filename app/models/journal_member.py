"""Journal membership model for journal sharing."""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, Relationship

from .base import BaseModel
from .enums import JournalPermission

if TYPE_CHECKING:
    from .journal import Journal
    from .user import User


class JournalMember(BaseModel, table=True):
    """A non-owner user's access grant for a journal."""

    __tablename__ = "journal_member"

    journal_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("journal.id", ondelete="CASCADE"), nullable=False)
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    permission: JournalPermission = Field(
        sa_column=Column(
            SAEnum(
                JournalPermission,
                name="journal_permission_enum",
                native_enum=True,
                values_callable=lambda values: [value.value for value in values],
            ),
            nullable=False,
        )
    )

    journal: "Journal" = Relationship(back_populates="members")
    user: "User" = Relationship(back_populates="shared_journal_memberships")

    __table_args__ = (
        # A person gets one effective role per journal, not a stack of grants.
        UniqueConstraint("journal_id", "user_id", name="uq_journal_member_journal_user"),
    )
