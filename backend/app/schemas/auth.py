"""
Pydantic schemas for authentication and user profile endpoints.
"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserResponse(BaseModel):
    """User profile response."""
    id: int
    email: str
    role: str
    full_name: str
    locale: str
    avatar_url: str | None = None
    email_verified_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateUserRequest(BaseModel):
    """Request body for updating user profile."""
    full_name: str | None = Field(None, min_length=1, max_length=255)
    locale: str | None = Field(None, pattern="^(es|en)$")
    avatar_url: str | None = None


class EmailCodeRequest(BaseModel):
    """Request body for asking a login code (passwordless)."""
    email: EmailStr


class EmailCodeVerifyRequest(BaseModel):
    """Request body for verifying a login code."""
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=12)


class RefreshRequest(BaseModel):
    """Request body for token refresh / logout."""
    refresh_token: str


class TokenResponse(BaseModel):
    """Response with access and refresh tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
