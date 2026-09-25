"""
Pydantic schemas for CV management endpoints.
"""
from datetime import datetime

from pydantic import BaseModel, Field


class CVStructuredData(BaseModel):
    """Structured CV data from PDF extraction or editor."""
    full_name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    experience: list[dict] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    languages: list[dict] = Field(default_factory=list)


class CVCreateRequest(BaseModel):
    """Request body for creating a CV from structured editor."""
    structured: CVStructuredData
    original_filename: str = Field(default="structured_cv.pdf")


class CVResponse(BaseModel):
    """CV response for list/detail endpoints."""
    id: int
    original_filename: str
    detected_locale: str | None = None
    created_at: datetime
    last_edited_at: datetime

    model_config = {"from_attributes": True}


class CVDetailResponse(CVResponse):
    """Detailed CV response with structured data."""
    structured: dict
    raw_text: str | None = None


class CVUpdateRequest(BaseModel):
    """Request body for updating CV structured data."""
    structured: CVStructuredData


class CVUploadResponse(BaseModel):
    """Response after successful CV upload."""
    cv_id: int
    original_filename: str
    detected_locale: str
    structured: dict
    parsed_at: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    code: str | None = None
