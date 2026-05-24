"""
Cached Immich face detections for linked assets.
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
    Integer,
    String,
    UniqueConstraint,
)
from sqlmodel import Column as SQLModelColumn
from sqlmodel import Field, Index

from .base import BaseModel
from .types import JSONType


class ImmichAssetFace(BaseModel, table=True):
    """
    Refreshable cache of face detections on Immich assets.
    """
    __tablename__ = "immich_asset_face"

    user_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    integration_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("integration.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    external_asset_id: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    external_face_id: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    external_person_id: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True, index=True))
    person_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    bounding_box_x1: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    bounding_box_y1: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    bounding_box_x2: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    bounding_box_y2: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    image_width: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    image_height: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    source_type: Optional[str] = Field(default=None, sa_column=Column(String(50), nullable=True))
    is_hidden: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=sa.false(), default=False),
    )
    raw_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=SQLModelColumn(JSONType(), nullable=True),
    )
    last_synced_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (
        UniqueConstraint("integration_id", "external_face_id", name="uq_immich_asset_face_integration_face"),
        Index("idx_immich_asset_face_integration_asset", "integration_id", "external_asset_id"),
        Index("idx_immich_asset_face_integration_person", "integration_id", "external_person_id"),
        Index("idx_immich_asset_face_user_person", "user_id", "person_id"),
    )
