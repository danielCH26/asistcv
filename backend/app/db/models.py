"""
SQLModel database models for AsistCV.

NOTE: Vector embeddings (vector(1024)) are NOT included in Sprint 0.
They will be added in Slice 1 (issue #16).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, JSON, ForeignKey, Integer, DateTime, String, Text
from sqlmodel import Field, SQLModel


class Profile(SQLModel, table=True):
    """User profile model - stores candidate information."""

    __tablename__ = "profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=255, description="Full name of the candidate")
    headline: Optional[str] = Field(
        default=None, max_length=500, description="Professional headline"
    )
    experience: Optional[dict] = Field(
        default=None, sa_column=Column(JSON), description="Work experience data"
    )
    skills: Optional[dict] = Field(
        default=None, sa_column=Column(JSON), description="Skills and competencies"
    )
    preferences: Optional[dict] = Field(
        default=None, sa_column=Column(JSON), description="Job preferences"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()", onupdate=datetime.utcnow),
    )


class JobDescription(SQLModel, table=True):
    """Job description model - stores job postings."""

    __tablename__ = "job_descriptions"

    id: Optional[int] = Field(default=None, primary_key=True)
    raw_text: str = Field(sa_column=Column(Text, nullable=False), description="Full job description text")
    title: Optional[str] = Field(
        default=None, max_length=500, description="Job title"
    )
    company: Optional[str] = Field(
        default=None, max_length=255, description="Company name"
    )
    source: Optional[str] = Field(
        default=None, max_length=100, description="Source of the job posting"
    )
    url: Optional[str] = Field(
        default=None, max_length=2048, description="URL to original posting"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


class Analysis(SQLModel, table=True):
    """Analysis model - stores matching analysis results."""

    __tablename__ = "analyses"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_description_id: int = Field(
        sa_column=Column(Integer, ForeignKey("job_descriptions.id"), nullable=False),
        description="Reference to the job description"
    )
    profile_snapshot: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Snapshot of profile data at time of analysis",
    )
    score: Optional[int] = Field(
        default=None, ge=0, le=100, description="Match score 0-100"
    )
    strengths: Optional[dict] = Field(
        default=None, sa_column=Column(JSON), description="Identified strengths"
    )
    gaps: Optional[dict] = Field(
        default=None, sa_column=Column(JSON), description="Identified gaps"
    )
    energy_level: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Energy level assessment: high, medium, low",
    )
    reasoning: Optional[str] = Field(
        default=None, sa_column=Column(Text), description="AI reasoning for the analysis"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )
