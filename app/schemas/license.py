"""
Pydantic schemas for Journiv Plus license management.

These schemas are used by the backend to communicate with the journiv-plus
license server and to provide license management endpoints to the frontend.
"""
import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class LicenseRegisterRequest(BaseModel):
    """Request to register a Plus license."""

    license: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Plain text license key in format 'lic_' followed by 32 alphanumeric characters (e.g., 'lic_abc123def456ghi789jkl012mno345pq')"
    )
    email: EmailStr = Field(
        ...,
        description="Admin's email address"
    )
    discord_id: Optional[str] = Field(
        None,
        description="Optional Discord ID to participate in the plus group"
    )

    @field_validator('license', mode='before')
    @classmethod
    def validate_license_format(cls, v: str) -> str:
        """Validate license key format: lic_ followed by exactly 32 alphanumeric characters."""
        v = v.strip()
        pattern = r"^lic_[a-zA-Z0-9]{32}$"
        if not re.match(pattern, v):
            raise ValueError('License key must match format: lic_ followed by exactly 32 alphanumeric characters (e.g., lic_abc123def456ghi789jkl012mno345pq)')
        return v


class LicenseRegisterResponse(BaseModel):
    """Response from license registration."""

    successful: bool = Field(..., description="Whether registration succeeded")
    signed_license: Optional[str] = Field(
        None,
        max_length=2000,
        description="Signed license claim envelope (base64)"
    )
    error_message: Optional[str] = Field(
        None,
        description="Error message if registration failed"
    )
    rate_limited: Optional[bool] = Field(False, description="Whether the request was rate limited")
    retry_after: Optional[int] = Field(None, description="Seconds to wait before retrying")


class LicenseInfoResponse(BaseModel):
    """
    Detailed license information response.
    """

    is_active: bool = Field(..., description="Whether license is currently active")
    tier: Optional[str] = Field(None, description="License tier (none, supporter, believer)")
    license_type: str = Field(..., description="License type: 'subscription' or 'lifetime'")
    subscription_expires_at: Optional[str] = Field(None, description="Subscription expiration timestamp (ISO format). NULL for lifetime licenses.")
    install_id: str = Field(..., description="Hardware-bound installation identifier for license binding")

    # Server info (optional, from online fetch)
    is_cancelled: Optional[bool] = Field(None, description="Whether license has been cancelled (server)")
    registered_email: Optional[str] = Field(None, description="Email address on license (server)")
    discord_id: Optional[str] = Field(None, description="Discord ID on license (server)")


class LicenseResetRequest(BaseModel):
    """Request to unbind a license from current installation."""

    install_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Current installation ID to unbind"
    )
    email: EmailStr = Field(
        ...,
        description="User's email for verification (must match license owner)"
    )

    @field_validator('install_id')
    @classmethod
    def validate_install_id_format(cls, v: str) -> str:
        """Validate install_id is a valid UUID v5 (deterministic)."""
        from uuid import UUID
        v = str(v).strip().lower()
        try:
            uuid_obj = UUID(v)
            # Enforce UUID v5 (deterministic/name-based) for consistency
            # journiv-backend uses UUID v5 for deterministic install_id generation
            if uuid_obj.version != 5:
                raise ValueError(f'install_id must be UUID v5 (deterministic), got version {uuid_obj.version}')
        except ValueError as e:
            if 'version' in str(e):
                raise
            raise ValueError('install_id must be a valid UUID v5 (deterministic)') from None
        return v


class LicenseResetResponse(BaseModel):
    """Response from license reset/unbind operation."""

    status: str = Field(..., description="Operation status: 'ok'")

