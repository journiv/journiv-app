"""
Instance details for a single Journiv installation.
"""

import re
from datetime import datetime
from typing import Optional

from pydantic import field_validator
from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field

from app.core.install_id import generate_install_id

from .base import BaseModel


class InstanceDetail(BaseModel, table=True):
    """
    Source of truth for instance identity and license management.

    CRITICAL INFORMATION:
    ========================
    This model inherits an 'id' field (UUID) from BaseModel which serves as the
    database primary key. This 'id' field is INTERNAL ONLY and must NEVER be
    exposed in APIs, services, or to external systems.

    ALWAYS use 'install_id' for:
    - All API responses (system, license, version endpoints)
    - All external service communication (journiv-plus server)
    - All logging and other information
    - Frontend display (settings etc.)

    The 'id' field exists ONLY for:
    - Database primary key and ORM operations
    - Internal foreign key relationships (if any)
    """

    __tablename__ = "instance_details"
    __table_args__ = (
        UniqueConstraint('singleton_marker', name='uq_instance_details_singleton'),
    )

    # Hardware-bound installation identifier (PRIMARY EXTERNAL ID)
    # This is the ONLY ID that should be exposed outside the database layer
    install_id: str = Field(
        default_factory=generate_install_id,
        max_length=36,
        unique=True,
        nullable=False,
        index=True,
        description="Hardware-bound deterministic UUID for this installation. "
                    "ALWAYS USE THIS for APIs, license validation, and external communication. "
                    "This ID is used for license binding."
    )
    signed_license: Optional[str] = Field(
        default=None,
        max_length=2048,
        description="Ed25519 signed license from journiv-plus license server"
    )
    license_validated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Last successful license validation timestamp for informational purposes only."
    )

    version_check_enabled: bool = Field(
        default=True,
        description="Whether version checking is enabled (user-controlled via admin UI)"
    )

    # Per-instance authentication secret from journiv-plus
    plus_instance_secret: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Unique HMAC secret from journiv-plus server (64 hex chars). "
                    "Used for signing all requests to journiv-plus. "
                    "Obtained during instance registration handshake."
    )

    # Singleton marker to enforce single row constraint
    singleton_marker: int = Field(
        default=1,
        nullable=False,
        description="Constant marker field (always 1) used with UNIQUE constraint to enforce singleton pattern."
    )

    @field_validator('plus_instance_secret')
    @classmethod
    def validate_secret_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not re.match(r'^[0-9a-fA-F]{64}$', v):
            raise ValueError('plus_instance_secret must be 64 hexadecimal characters')
        return v
