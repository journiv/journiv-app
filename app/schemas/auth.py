"""
Authentication schemas.
"""
from typing import Optional

from pydantic import BaseModel, validator


class Token(BaseModel):
    """
    Token response schema.

    refresh_token is optional - only included during login, not during token refresh.
    This ensures refresh tokens eventually expire and require re-login.
    """
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Login response schema with tokens and user info."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class TokenData(BaseModel):
    """Token data schema."""
    user_id: Optional[str] = None


class UserCreate(BaseModel):
    """User creation schema."""
    email: str
    password: str
    name: str

    @validator('email')
    def validate_email(cls, v):
        if v and '@' not in v:
            raise ValueError('Invalid email address')
        return v.lower().strip() if v else v

    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Name cannot be empty')
        return v.strip()


class UserLogin(BaseModel):
    """User login schema."""
    email: str
    password: str

    @validator('email')
    def validate_email(cls, v):
        if v and '@' not in v:
            raise ValueError('Invalid email address')
        return v.lower().strip() if v else v


class TokenRefresh(BaseModel):
    """Token refresh schema."""
    refresh_token: str
