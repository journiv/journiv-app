"""
Database models for integrations and cached provider data.

This module defines the core Integration model.
All tokens are encrypted using Fernet before storage and decrypted on retrieval.

Models:
- Integration: Stores user connections to external providers (currently Immich)

Extension Points:
- Add new provider models following the same pattern
- Always include user_id foreign key with CASCADE delete
- Add external_id for mapping to provider's ID system
- Include timestamps for sync management
"""
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import Column, ForeignKey, String, Text, UniqueConstraint
from sqlmodel import Field, Index, Relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class IntegrationProvider(str, Enum):
    """
    Supported integration providers.

    Add new providers here as they are implemented.
    Each provider must have a corresponding client module in app/integrations/{provider}.py
    """
    IMMICH = "immich"
    # TODO: Add other providers
    # JELLYFIN = "jellyfin"
    # AUDIOBOOKSHELF = "audiobookshelf"


class AssetType(str, Enum):
    """
    Media asset types across all providers.

    Used for consistent categorization of cached items.
    """
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    OTHER = "OTHER"


class ImportMode(str, Enum):
    """
    Import mode for external assets.

    Determines how assets are handled when imported from external providers.
    """
    LINK_ONLY = "link_only"  # Store references only, fetch on-demand
    COPY = "copy"  # Download and store files locally


class Integration(BaseModel, table=True):
    """
    User's connection to an external integration provider.

    Currently supports Immich. Additional providers can be added in the future.
    Credentials are encrypted at rest and decrypted when making API calls.

    Fields:
        user_id: The Journiv user who owns this integration
        provider: Which service this connects to (currently: immich)
        base_url: The provider's base URL (can override .env defaults)
        access_token_encrypted: Encrypted API key or OAuth access token
        refresh_token_encrypted: Encrypted OAuth refresh token (optional, for future)
        token_expires_at: Token expiration timestamp (optional, for future OAuth)
        external_user_id: The user's ID in the external system
        last_synced_at: When we last successfully synced data from this provider
        last_error: Last error message from sync/API call (for debugging)
        last_error_at: When the last error occurred
        is_active: Whether this integration is enabled (false = paused)
        connected_at: When the user first connected this integration

    Security:
        - Tokens are encrypted using Fernet (core/encryption.py)
        - Changing SECRET_KEY invalidates all encrypted tokens
        - Never expose encrypted tokens in API responses
    """
    __tablename__ = "integration"

    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )

    provider: IntegrationProvider = Field(
        sa_column=Column(String(50), nullable=False, index=True),
        description="Integration provider type"
    )

    base_url: str = Field(
        sa_column=Column(String(512), nullable=False),
        description="Provider's base URL (e.g., https://immich.example.com)"
    )

    # Encrypted tokens (stored as text to accommodate variable-length encrypted data)
    access_token_encrypted: str = Field(
        sa_column=Column(Text, nullable=False),
        description="Encrypted API key or OAuth access token"
    )

    refresh_token_encrypted: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Encrypted OAuth refresh token (future use)"
    )

    token_expires_at: Optional[datetime] = Field(
        default=None,
        description="Token expiration time (future use for OAuth)"
    )

    # Provider-specific metadata
    external_user_id: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="User's ID in the external provider's system"
    )

    # Sync tracking
    last_synced_at: Optional[datetime] = Field(
        default=None,
        description="Last successful sync timestamp"
    )

    last_error: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Last error message from sync/API call"
    )

    last_error_at: Optional[datetime] = Field(
        default=None,
        description="When the last error occurred"
    )

    # Status
    is_active: bool = Field(
        default=True,
        description="Whether this integration is currently enabled"
    )

    connected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the user first connected this integration"
    )

    # Import mode configuration
    import_mode: ImportMode = Field(
        default=ImportMode.LINK_ONLY,
        sa_column=Column(String(20), nullable=False, default=ImportMode.LINK_ONLY.value),
        description="How to handle asset imports (link-only or copy)"
    )

    # Provider-specific metadata (JSON column for flexible provider data storage)
    provider_metadata: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="JSON metadata specific to the provider (e.g., album_id for Immich)"
    )

    # Relationships
    user: "User" = Relationship(back_populates="integrations")

    # Table constraints and indexes
    __table_args__ = (
        # Unique constraint: one connection per user per provider
        UniqueConstraint("user_id", "provider", name="uq_user_provider"),
        # Index for finding active integrations by provider (for scheduled sync)
        Index("idx_integration_active_provider", "is_active", "provider"),
        # Index for finding integrations that need syncing
        Index("idx_integration_last_synced", "last_synced_at"),
    )

    def get_metadata(self) -> Dict[str, Any]:
        """Get provider metadata as dict, handling JSON deserialization."""
        if self.provider_metadata is None:
            return {}
        if isinstance(self.provider_metadata, dict):
            return self.provider_metadata
        if isinstance(self.provider_metadata, str):
            try:
                return json.loads(self.provider_metadata)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def set_metadata(self, metadata: Dict[str, Any]) -> None:
        """Set provider metadata, handling JSON serialization."""
        if metadata is None or metadata == {}:
            self.provider_metadata = None
        else:
            # Store as JSON string for both SQLite and PostgreSQL
            self.provider_metadata = json.dumps(metadata)

    def update_metadata(self, **kwargs) -> None:
        """Update specific keys in provider metadata."""
        current = self.get_metadata()
        current.update(kwargs)
        self.set_metadata(current)

