"""
Pydantic schemas for user profile endpoints.

Note: Authentication schemas (SignUpRequest, LoginRequest, RefreshRequest,
TokenResponse, ChangePasswordRequest, VerifyEmailRequest, VerifyEmailConfirm)
have been removed as part of the Clerk auth migration (S2). Authentication is
now handled by Clerk; these schemas are no longer needed.
"""
from datetime import datetime

from pydantic import BaseModel, Field


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
