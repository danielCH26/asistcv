"""
Pydantic schemas for authentication endpoints.
"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignUpRequest(BaseModel):
    """Request body for user registration."""
    email: EmailStr
    password: str = Field(..., min_length=10)
    role: str = Field(..., pattern="^(job_seeker|recruiter)$")
    full_name: str = Field(..., min_length=1, max_length=255)
    locale: str = Field(default="es", pattern="^(es|en)$")
    accept_tos: bool = Field(default=False)
    good_faith_declaration: bool = Field(default=False)
    tos_version: str | None = None

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        """Validate password has uppercase, lowercase, and digit."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    """Request body for login."""
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Request body for token refresh."""
    refresh_token: str


class TokenResponse(BaseModel):
    """Response with access and refresh tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


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


class ChangePasswordRequest(BaseModel):
    """Request body for changing password."""
    current_password: str
    new_password: str = Field(..., min_length=10)

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        """Validate password has uppercase, lowercase, and digit."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class VerifyEmailRequest(BaseModel):
    """Request body for requesting email verification."""
    pass


class VerifyEmailConfirm(BaseModel):
    """Request body for confirming email verification."""
    token: str
