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


class Embedding(BaseModel):
    """Text embedding vector."""

    vector: list[float] = Field(..., description="Embedding vector (1024 dimensions)")
    model: str = Field(..., description="Model used to generate the embedding")
    provider: str = Field(default="unknown", description="Provider that generated the embedding")
