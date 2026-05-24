"""
External provider identities linked to Journiv people.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlmodel import Column as SQLModelColumn
from sqlmodel import Field, Index

from .base import BaseModel
from .types import JSONType


class PersonExternalIdentity(BaseModel, table=True):
    """
    Provider identity mapped to a Journiv person.

    The Journiv person remains the canonical user-facing identity. Provider
    records are stored here only for sync/matching.
    """
    __tablename__ = "person_external_identity"

    user_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    person_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("person.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    integration_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("integration.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    provider: str = Field(sa_column=Column(String(50), nullable=False, index=True))
    external_person_id: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    external_name: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
    external_thumbnail_asset_id: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
    external_face_id: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
    feature_face_asset_id: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
    is_hidden: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=sa.false(), default=False),
    )
    is_favorite: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=sa.false(), default=False),
    )
    sync_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=sa.true(), default=True),
    )
    last_synced_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    raw_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=SQLModelColumn(JSONType(), nullable=True),
    )

    __table_args__ = (
        UniqueConstraint("integration_id", "external_person_id", name="uq_person_external_identity_provider_person"),
        UniqueConstraint("person_id", "integration_id", "provider", name="uq_person_external_identity_person_provider"),
        Index("idx_person_external_identity_user_provider_sync", "user_id", "provider", "sync_enabled"),
    )
