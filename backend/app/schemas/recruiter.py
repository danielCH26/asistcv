"""
Pydantic schemas for recruiter endpoints.
"""
from datetime import datetime

from pydantic import BaseModel, Field


class ConsentRequest(BaseModel):
    """Request body for recruiter consent (re-consent on ToS update)."""
    accept_tos: bool = Field(default=False)
    good_faith_declaration: bool = Field(default=False)
    tos_version: str = Field(..., min_length=1, max_length=50)


class ConsentResponse(BaseModel):
    """Response after giving consent."""
    accepted_at: datetime
    tos_version: str

    model_config = {"from_attributes": True}


class CandidateCreate(BaseModel):
    """Request body for creating a candidate."""
    full_name: str = Field(..., min_length=1, max_length=255)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    notes: str | None = None


class CandidateResponse(BaseModel):
    """Response for a candidate."""
    id: int
    recruiter_id: int
    full_name: str
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    cv_id: int | None = None
    last_analysed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CandidateListResponse(BaseModel):
    """Response for listing candidates."""
    items: list[CandidateResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class CandidateUpdate(BaseModel):
    """Request body for updating a candidate."""
    full_name: str | None = Field(None, min_length=1, max_length=255)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    notes: str | None = None


class CandidateMatchRequest(BaseModel):
    """Request body for matching a candidate against a JD."""
    jd_text: str = Field(..., min_length=50)


class CandidateMatchResponse(BaseModel):
    """Response for candidate match."""
    candidate_id: int
    score: int | None = None
    strengths: dict | None = None
    gaps: dict | None = None
    reasoning: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CandidateRankedResponse(BaseModel):
    """Response for ranked candidates."""
    items: list[CandidateResponse]
    total: int
    effective_scores: dict[int, float]  # candidate_id -> score
    total_candidates: int
    is_truncated: bool = False


class AuditLogResponse(BaseModel):
    """Response for audit log entry."""
    id: int
    recruiter_id: int
    candidate_id: int | None = None
    action: str
    details: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
