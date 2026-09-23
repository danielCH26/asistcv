"""
SQLModel database models for AsistCV.

Embedding columns (vector(1024) + embedding_model) were added in
migration 002 (Sprint 1, issue #14). They are NULLable so legacy rows
remain valid until on-demand re-embedding fills them.
"""
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class Profile(SQLModel, table=True):
    """User profile model - stores candidate information."""

    __tablename__ = "profiles"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=255, description="Full name of the candidate")
    headline: str | None = Field(
        default=None, max_length=500, description="Professional headline"
    )
    experience: dict | None = Field(
        default=None, sa_column=Column(JSON), description="Work experience data"
    )
    skills: dict | None = Field(
        default=None, sa_column=Column(JSON), description="Skills and competencies"
    )
    preferences: dict | None = Field(
        default=None, sa_column=Column(JSON), description="Job preferences"
    )
    embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(1024), nullable=True),
        description="Profile embedding vector (1024 dims)",
    )
    embedding_model: str | None = Field(
        default=None,
        sa_column=Column(String(100), nullable=True),
        description="Model that generated the embedding (re-embedding marker)",
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

    id: int | None = Field(default=None, primary_key=True)
    raw_text: str = Field(sa_column=Column(Text, nullable=False), description="Full job description text")
    title: str | None = Field(
        default=None, max_length=500, description="Job title"
    )
    company: str | None = Field(
        default=None, max_length=255, description="Company name"
    )
    source: str | None = Field(
        default=None, max_length=100, description="Source of the job posting"
    )
    url: str | None = Field(
        default=None, max_length=2048, description="URL to original posting"
    )
    embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(1024), nullable=True),
        description="JD embedding snapshot at analysis time (never re-generated)",
    )
    embedding_model: str | None = Field(
        default=None,
        sa_column=Column(String(100), nullable=True),
        description="Model that generated the embedding",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


class Analysis(SQLModel, table=True):
    """Analysis model - stores matching analysis results."""

    __tablename__ = "analyses"

    id: int | None = Field(default=None, primary_key=True)
    job_description_id: int = Field(
        sa_column=Column(Integer, ForeignKey("job_descriptions.id"), nullable=False),
        description="Reference to the job description"
    )
    profile_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("profiles.id"), nullable=True),
        description="Reference to the analyzed profile (NULL for legacy rows)",
    )
    profile_snapshot: dict | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Snapshot of profile data at time of analysis",
    )
    score: int | None = Field(
        default=None, ge=0, le=100, description="Match score 0-100"
    )
    strengths: dict | None = Field(
        default=None, sa_column=Column(JSON), description="Identified strengths"
    )
    gaps: dict | None = Field(
        default=None, sa_column=Column(JSON), description="Identified gaps"
    )
    energy_level: str | None = Field(
        default=None,
        max_length=50,
        description="Energy level assessment: high, medium, low",
    )
    reasoning: str | None = Field(
        default=None, sa_column=Column(Text), description="AI reasoning for the analysis"
    )
    embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(1024), nullable=True),
        description="JD embedding snapshot that produced the score (reproducibility)",
    )
    embedding_model: str | None = Field(
        default=None,
        sa_column=Column(String(100), nullable=True),
        description="Model that generated the embedding",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )
