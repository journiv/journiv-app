"""
External identity model for OIDC/OAuth authentication.
"""
import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, Relationship, String

from .base import TimestampMixin

if TYPE_CHECKING:
    from .user import User


class ExternalIdentity(TimestampMixin, table=True):
    """
    External identity linking OIDC/OAuth accounts to internal users.

    Links external authentication providers (issuer + subject) to internal user accounts.
    Supports multiple external identities per user and OIDC auto-provisioning.
    """

    __tablename__ = "external_identities"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )
    issuer: str = Field(
        ...,
        sa_column=Column(String(512), nullable=False, index=True),
        description="OIDC issuer URL (e.g., https://accounts.myhomelab.com)"
    )
    subject: str = Field(
        ...,
        sa_column=Column(String(255), nullable=False),
        description="OIDC subject identifier (unique per issuer)"
    )
    email: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
        description="Email from OIDC provider"
    )
    name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Display name from OIDC provider"
    )
    picture: Optional[str] = Field(
        default=None,
        sa_column=Column(String(512), nullable=True),
        description="Profile picture URL from OIDC provider"
    )
    last_login_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last successful login via this external identity"
    )

    # Relationships
    user: "User" = Relationship(back_populates="external_identities")

    # Table constraints
    __table_args__ = (
        UniqueConstraint(
            "issuer",
            "subject",
            name="uq_issuer_subject"
        ),
    )
