"""
User schemas.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl, validator

from app.models.enums import UserRole
from app.schemas.base import TimestampMixin


class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    name: Optional[str] = None

    @validator('email')
    def validate_email(cls, v):
        if v:
            return v.lower()
        return v


class UserCreate(UserBase):
    """User creation schema."""
    name: str
    password: str

    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Name cannot be empty')
        return v.strip()


class UserUpdate(BaseModel):
    """User update schema."""
    name: Optional[str] = None
    profile_picture_url: Optional[HttpUrl] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None

    @validator('new_password')
    def validate_new_password(cls, v, values):
        """Validate new password strength and requirements."""
        if v is not None:
            # Validate password strength
            if len(v) < 8:
                raise ValueError('Password must be at least 8 characters long')

            # Check for at least one letter and one number
            has_letter = any(c.isalpha() for c in v)
            has_digit = any(c.isdigit() for c in v)
            if not (has_letter and has_digit):
                raise ValueError('Password must contain at least one letter and one number')

            # Check current_password is also provided
            if values.get('current_password') is None:
                raise ValueError('current_password is required when changing password')

        return v


class UserResponse(UserBase, TimestampMixin):
    """User response schema."""
    id: uuid.UUID
    role: UserRole
    is_active: bool
    profile_picture_url: Optional[HttpUrl] = None
    last_login_at: Optional[datetime] = None
    time_zone: Optional[str] = "UTC"  # User's timezone from settings
    is_oidc_user: bool = False  # Whether user signed up via OIDC
    created_at: datetime
    updated_at: datetime


class UserSettingsBase(BaseModel):
    """Base user settings schema."""
    daily_prompt_enabled: bool = True
    time_zone: str = "UTC"
    push_notifications: bool = True
    reminder_time: Optional[str] = None
    writing_goal_daily: Optional[int] = None
    start_of_week_day: int = Field(0, ge=0, le=6)  # 0=Monday ... 6=Sunday
    theme: str = "light"


class UserSettingsCreate(UserSettingsBase):
    """User settings creation schema."""
    pass


class UserSettingsUpdate(BaseModel):
    """User settings update schema."""
    daily_prompt_enabled: Optional[bool] = None
    time_zone: Optional[str] = None
    push_notifications: Optional[bool] = None
    reminder_time: Optional[str] = None
    writing_goal_daily: Optional[int] = None
    start_of_week_day: Optional[int] = Field(None, ge=0, le=6)
    theme: Optional[str] = None

    @validator('time_zone')
    def validate_timezone(cls, v):
        """Validate timezone is a valid IANA timezone identifier."""
        if v is not None:
            from app.core.time_utils import validate_timezone
            if not validate_timezone(v):
                raise ValueError(f'Invalid timezone: "{v}". Must be a valid IANA timezone name (e.g., "America/New_York", "Europe/London", "Asia/Tokyo")')
        return v

    @validator('start_of_week_day')
    def validate_start_of_week_day(cls, v):
        if v is not None and (v < 0 or v > 6):
            raise ValueError("start_of_week_day must be between 0 and 6")
        return v


class UserSettingsResponse(UserSettingsBase, TimestampMixin):
    """User settings response schema."""
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# Admin-specific schemas
class AdminUserCreate(UserBase):
    """Admin user creation schema (can specify role)."""
    name: str
    password: str
    role: Optional[UserRole] = UserRole.USER

    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Name cannot be empty')
        return v.strip()


class AdminUserUpdate(BaseModel):
    """Admin user update schema (can change role, active status)."""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

    @validator('email')
    def validate_email(cls, v):
        if v:
            return v.lower()
        return v

    @validator('name')
    def validate_name(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError('Name cannot be empty')
        return v.strip() if v else v

    @validator('password')
    def validate_password(cls, v):
        """Validate password strength."""
        if v is not None:
            if len(v) < 8:
                raise ValueError('Password must be at least 8 characters long')
            has_letter = any(c.isalpha() for c in v)
            has_digit = any(c.isdigit() for c in v)
            if not (has_letter and has_digit):
                raise ValueError('Password must contain at least one letter and one number')
        return v


class AdminUserListResponse(BaseModel):
    """Admin user list response with additional metadata."""
    id: uuid.UUID
    email: EmailStr
    name: str
    role: UserRole
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    login_type: str  # "local" or "oidc"
    linked_providers: Optional[list[str]] = None  # List of OIDC provider names
