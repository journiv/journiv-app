"""
Base model classes and common functionality.

This module provides base classes for all database models in the application.
Uses timezone-aware UTC datetimes following modern Python best practices.
"""
import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from app.core.time_utils import utc_now


class BaseModel(SQLModel):
    """
    Base model with common fields for all entities.

    Provides:
    - UUID primary key for globally unique identifiers
    - created_at: Timestamp when record was created (auto-set, immutable)
    - updated_at: Timestamp when record was last modified (auto-updated in application code)

    Note: The updated_at field is managed in application code (services) rather than
    database triggers for better portability and explicit control.
    """
    __abstract__ = True
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for this record"
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        nullable=False,
        description="UTC timestamp when this record was created"
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        nullable=False,
        description="UTC timestamp when this record was last updated"
    )


class TimestampMixin(SQLModel):
    """
    Mixin for models that need timestamps but have their own primary key strategy.

    Used by models like UserSettings that don't use the standard UUID primary key
    pattern but still need creation and update timestamps.

    Note: The updated_at field is managed in application code (services) for
    consistency and explicit control. Services should call datetime.now(timezone.utc)
    and set updated_at when modifying records.
    """
    created_at: datetime = Field(
        default_factory=utc_now,
        nullable=False,
        description="UTC timestamp when this record was created"
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        nullable=False,
        description="UTC timestamp when this record was last updated"
    )
