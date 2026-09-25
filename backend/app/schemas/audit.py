"""
Pydantic schemas for audit endpoints.
"""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AuditAnonymousRequest(BaseModel):
    """Request body for anonymous audit endpoint."""

    jd_text: str = Field(..., min_length=50, description="Job description text (min 50 chars)")


class AuditAnonymousResponse(BaseModel):
    """Response body for anonymous audit."""

    audit_token: str = Field(..., description="Token to retrieve or claim this audit later")
    score: int = Field(..., ge=0, le=100, description="Match score 0-100")
    strengths: list[str] = Field(..., description="Identified strengths")
    gaps: list[str] = Field(..., description="Identified gaps")
    energy_level: str = Field(..., description="Energy level: high, medium, low")
    reasoning: str = Field(..., description="AI reasoning for the analysis")


class CaptureEmailRequest(BaseModel):
    """Request body for capturing email after audit."""

    email: str = Field(..., description="User email address")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format (basic RFC 5322 check)."""
        import re

        # Basic email regex (RFC 5322 simplified)
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, v):
            raise ValueError("EMAIL_INVALID")
        return v


class CaptureEmailResponse(BaseModel):
    """Response body for email capture."""

    message: str = Field(..., description="Status message")


class ClaimAuditRequest(BaseModel):
    """Request body for claiming an audit after user signup."""

    audit_token: str = Field(..., description="Token from the anonymous audit")
    user_id: int = Field(..., description="ID of the user claiming this audit")


class ClaimAuditResponse(BaseModel):
    """Response body for audit claim."""

    success: bool = Field(..., description="Whether the claim was successful")
    message: str = Field(..., description="Status message")


class AuditRetrieveResponse(BaseModel):
    """Response body for retrieving a cached audit result."""

    score: int = Field(..., ge=0, le=100)
    strengths: list[str]
    gaps: list[str]
    energy_level: str
    reasoning: str
    created_at: datetime
    email_captured: bool
