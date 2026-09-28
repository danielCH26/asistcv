"""
Pydantic schemas for LLM provider inputs and outputs.
"""
from typing import Literal

from pydantic import BaseModel, Field


class MatchAnalysis(BaseModel):
    """Analysis result from matching a JD against a profile."""

    score: int = Field(..., ge=0, le=100, description="Match score from 0 to 100")
    strengths: list[str] = Field(default_factory=list, description="List of matching strengths")
    gaps: list[str] = Field(default_factory=list, description="List of skill gaps or missing requirements")
    energy_level: Literal["low", "medium", "high"] = Field(..., description="Assessed energy level of the match")
    reasoning: str = Field(..., description="Explanation of the match analysis")


class AuditIssue(BaseModel):
    """A problematic area detected in a CV quality audit."""

    seccion: str = Field(..., description="CV section the issue belongs to")
    problema: str = Field(..., description="Description of the detected problem")
    severidad: Literal["low", "medium", "high"] = Field(..., description="Issue severity")


class CVAudit(BaseModel):
    """Result of a CV quality audit (no job description involved)."""

    score: int = Field(..., ge=0, le=100, description="CV quality score from 0 to 100")
    problematicas: list[AuditIssue] = Field(
        default_factory=list, description="Problems detected in the CV"
    )
    recomendaciones: list[str] = Field(
        default_factory=list, description="Actionable recommendations to improve the CV"
    )
    fortalezas: list[str] = Field(default_factory=list, description="CV strengths")


# === Sprint 3: CV -> JD Adaptation (Slice A, PR2) ===


class AdaptedExperienceItem(BaseModel):
    """Single experience block in an adapted CV.

    Mirrors the shape of ``UserCV.structured.experience[*]``; only
    ``description`` is rewritten by the LLM (the other fields are preserved
    verbatim from the source CV).
    """

    title: str = Field(..., description="Job title as it appears in the source CV")
    company: str = Field(..., description="Company name as it appears in the source CV")
    dates: str = Field(..., description="Date range (verbatim from source CV)")
    description: str = Field(
        ...,
        description="Rewritten bullet block. Honesty validator checks substrings against the source.",
    )


class AdaptedCV(BaseModel):
    """Structured output of a CV -> JD adaptation.

    Same shape as ``UserCV.structured`` so the runner can persist the LLM
    output directly to ``CVAdaptation.adapted_cv_json`` without reshaping.
    Only ``experience[*].description`` is rewritten; everything else
    (full_name, skills, education, languages, experience metadata) is
    expected to be a subset/verbatim copy of the source.
    """

    full_name: str = Field(..., description="Candidate's full name (verbatim from source)")
    experience: list[AdaptedExperienceItem] = Field(
        default_factory=list, description="Experience blocks; only description is rewritten"
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Skills list. Honesty validator requires each to be a normalized substring of the source skills.",
    )
    education: list[dict] = Field(
        default_factory=list,
        description="Education blocks (verbatim from source)",
    )
    languages: list[str] = Field(
        default_factory=list, description="Languages (verbatim from source)"
    )


class Embedding(BaseModel):
    """Text embedding vector."""

    vector: list[float] = Field(..., description="Embedding vector (1024 dimensions)")
    model: str = Field(..., description="Model used to generate the embedding")
    provider: str = Field(default="unknown", description="Provider that generated the embedding")
