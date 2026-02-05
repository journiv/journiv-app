"""
Pydantic schemas for integration API requests and responses.

These schemas define the shape of data sent to and from the integration endpoints.
They provide validation, documentation, and type safety for the API.

Request Schemas:
- IntegrationConnectRequest: Connect to a provider with credentials
- IntegrationDisconnectRequest: Disconnect from a provider

Response Schemas:
- IntegrationStatusResponse: Current status of an integration
- IntegrationConnectResponse: Result of a successful connection
- IntegrationAssetResponse: Normalized asset data from any provider

Design Principles:
- Never expose encrypted tokens in responses
- Normalize provider-specific data to common formats
- Include helpful metadata for the frontend (URLs, status, errors)
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl, TypeAdapter, field_validator

from app.models.integration import AssetType, ImportMode, IntegrationProvider

# ================================================================================
# REQUEST SCHEMAS
# ================================================================================

class IntegrationConnectRequest(BaseModel):
    """
    Request to connect a new integration or update an existing one.

    Fields:
        provider: Which service to connect (immich, jellyfin, audiobookshelf)
        credentials: Provider-specific authentication data (dict to support different auth methods)
        base_url: Optional override for provider's base URL (defaults to .env value)

    Examples:
        Immich:
            {
                "provider": "immich",
                "credentials": {"api_key": "abc123..."},
                "base_url": "https://photos.example.com"  # optional
            }
    """
    provider: IntegrationProvider = Field(
        ...,
        description="Integration provider to connect"
    )

    credentials: dict = Field(
        ...,
        description="Provider-specific authentication credentials (e.g., {'api_key': '...'})"
    )

    base_url: Optional[str] = Field(
        default=None,
        description="Override provider base URL (optional, defaults to .env value)"
    )

    import_mode: Optional[ImportMode] = Field(
        default=ImportMode.LINK_ONLY,
        description="How to handle asset imports (link-only or copy). Defaults to link_only."
    )

    @field_validator('base_url', mode='before')
    @classmethod
    def normalize_base_url(cls, v):
        """Remove trailing slash from base URL for consistency."""
        if v is None:
            return None
        url_str = str(v)
        validated = TypeAdapter(HttpUrl).validate_python(url_str)
        return str(validated).rstrip('/')


class IntegrationDisconnectRequest(BaseModel):
    """
    Request to disconnect an integration.

    Fields:
        provider: Which integration to disconnect
    """
    provider: IntegrationProvider = Field(
        ...,
        description="Integration provider to disconnect"
    )


class IntegrationSettingsUpdateRequest(BaseModel):
    """
    Request to update integration settings without reconnecting.

    Fields:
        import_mode: Update import mode (optional)
        album_id: Update album ID for link mode (optional, Immich only)
    """
    import_mode: Optional[ImportMode] = Field(
        None,
        description="Update import mode (optional)"
    )
    album_id: Optional[str] = Field(
        None,
        description="Update album ID for link mode (optional, Immich provider only)"
    )


# ================================================================================
# RESPONSE SCHEMAS
# ================================================================================

class IntegrationStatusResponse(BaseModel):
    """
    Current status of an integration connection.

    Fields:
        provider: Which service this is
        status: "connected" | "disconnected" | "error"
        external_user_id: User's ID in the external system (if connected)
        connected_at: When the integration was first connected (if connected)
        last_synced_at: When we last successfully synced data (if any)
        last_error: Last error message (if any)
        is_active: Whether the integration is currently enabled

    Example Response:
        {
            "provider": "immich",
            "status": "connected",
            "external_user_id": "abc-123-def",
            "connected_at": "2025-01-01T12:00:00Z",
            "last_synced_at": "2025-01-06T10:00:00Z",
            "last_error": null,
            "is_active": true
        }
    """
    provider: IntegrationProvider
    status: str = Field(
        ...,
        description="Connection status: 'connected', 'disconnected', or 'error'"
    )
    external_user_id: Optional[str] = Field(
        default=None,
        description="User's ID in the external provider system"
    )
    connected_at: Optional[datetime] = Field(
        default=None,
        description="When the integration was first connected"
    )
    last_synced_at: Optional[datetime] = Field(
        default=None,
        description="Last successful sync timestamp"
    )
    last_error: Optional[str] = Field(
        default=None,
        description="Last error message (if any)"
    )
    is_active: bool = Field(
        default=True,
        description="Whether the integration is currently enabled"
    )
    import_mode: ImportMode = Field(
        default=ImportMode.LINK_ONLY,
        description="Current import mode setting"
    )
    album_id: Optional[str] = Field(
        default=None,
        description="Album ID for link mode (Immich provider)"
    )
    album_error: Optional[str] = Field(
        default=None,
        description="Error message if album creation/validation failed"
    )

    class Config:
        from_attributes = True


class IntegrationConnectResponse(BaseModel):
    """
    Response after successfully connecting an integration.

    Fields:
        status: "connected" (always)
        provider: Which service was connected
        external_user_id: Verified user ID from the provider
        connected_at: Connection timestamp

    Example Response:
        {
            "status": "connected",
            "provider": "immich",
            "external_user_id": "abc-123",
            "connected_at": "2025-01-06T12:00:00Z"
        }

    Security Note:
        - Never include encrypted tokens or raw credentials in this response
        - Only return non-sensitive metadata
    """
    status: str = Field(
        default="connected",
        description="Connection status (always 'connected' on success)"
    )
    provider: IntegrationProvider = Field(
        ...,
        description="Integration provider that was connected"
    )
    external_user_id: str = Field(
        ...,
        description="Verified user ID from the provider"
    )
    connected_at: datetime = Field(
        ...,
        description="When the integration was connected"
    )

    class Config:
        from_attributes = True


class IntegrationAssetResponse(BaseModel):
    """
    Normalized asset data from any integration provider.

    This schema provides a consistent format for assets across all providers
    (Immich, Jellyfin, Audiobookshelf, etc.), making it easy for the frontend
    to display them in a unified interface.

    Fields:
        id: External asset ID (from the provider)
        type: Asset type (IMAGE, VIDEO, AUDIO, OTHER)
        title: Human-readable title (filename for Immich, show title for Jellyfin, etc.)
        taken_at: When the asset was created/taken/watched
        thumb_url: Relative URL to thumbnail proxy endpoint

    Example Response (Immich photo):
        {
            "id": "abc-123",
            "type": "IMAGE",
            "title": "IMG_1234.jpg",
            "taken_at": "2025-01-01T12:00:00Z",
            "thumb_url": "/api/v1/integrations/immich/proxy/abc-123/thumbnail"
        }

    Frontend Usage:
        - Use thumb_url to display thumbnails (backend proxies from provider)
        - type determines which icon/player to show
        - taken_at enables chronological sorting and "On This Day" features
    """
    id: str = Field(
        ...,
        description="External asset ID from the provider"
    )
    type: AssetType = Field(
        ...,
        description="Asset type (IMAGE, VIDEO, AUDIO, OTHER)"
    )
    title: Optional[str] = Field(
        default=None,
        description="Human-readable title or filename"
    )
    taken_at: Optional[datetime] = Field(
        default=None,
        description="When the asset was created, taken, or watched"
    )
    thumb_url: str = Field(
        ...,
        description="Relative URL to thumbnail proxy endpoint"
    )
    original_url: Optional[str] = Field(
        default=None,
        description="Signed URL to original asset proxy endpoint"
    )

    class Config:
        from_attributes = True


class IntegrationAssetsListResponse(BaseModel):
    """
    Paginated list of assets from a provider.

    Fields:
        assets: List of normalized assets
        page: Current page number
        limit: Items per page
        total: Total number of assets available
        has_more: Whether there are more pages

    Example Response:
        {
            "assets": [...],
            "page": 1,
            "limit": 50,
            "total": 1234,
            "has_more": true
        }
    """
    assets: list[IntegrationAssetResponse] = Field(
        ...,
        description="List of assets on this page"
    )
    page: int = Field(
        ...,
        description="Current page number (1-indexed)"
    )
    limit: int = Field(
        ...,
        description="Number of items per page"
    )
    total: int = Field(
        ...,
        description="Total number of assets available"
    )
    has_more: bool = Field(
        ...,
        description="Whether there are more pages to fetch"
    )
