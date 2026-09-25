"""
SQLModel database models for AsistCV.

Embedding columns (vector(1024) + embedding_model) were added in
migration 002 (Sprint 1, issue #14). They are NULLable so legacy rows
remain valid until on-demand re-embedding fills them.

User accounts and auth tables added in migration 003 (Sprint 2, PR1):
- User, RefreshToken, TokenRevocation, LoginAttempt, SecurityEvent
- owner_user_id added to Profile and Analysis
"""
from datetime import datetime
from typing import ClassVar

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
    owner_user_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=True),
        description="User who owns this profile (NULL for legacy/anonymous)",
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
    owner_user_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=True),
        description="User who owns this analysis (NULL for legacy/anonymous)",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


# === Sprint 2: User Accounts (PR1) ===

class User(SQLModel, table=True):
    """User model for authentication and profile."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(max_length=255, unique=True, index=True, description="User email (CITEXT)")
    password_hash: str = Field(description="Bcrypt hashed password")
    role: str = Field(max_length=20, description="User role: job_seeker or recruiter")
    full_name: str = Field(max_length=255, description="User's full name")
    locale: str = Field(default="es", max_length=10, description="Preferred locale")
    avatar_url: str | None = Field(default=None, description="URL to avatar image")
    email_verified_at: datetime | None = Field(default=None, description="Timestamp when email was verified")
    email_verification_token_hash: str | None = Field(default=None, description="Hash of email verification token")
    email_verification_expires_at: datetime | None = Field(default=None, description="Expiration of verification token")
    last_login_at: datetime | None = Field(default=None, description="Last successful login timestamp")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()", onupdate=datetime.utcnow),
    )


class RefreshToken(SQLModel, table=True):
    """Refresh token for JWT session management."""

    __tablename__ = "users_refresh_tokens"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=False),
        description="Owner of the token"
    )
    token_hash: str = Field(unique=True, description="SHA256 hash of the token")
    consumed_at: datetime | None = Field(default=None, description="When token was used (for rotation)")
    revoked_at: datetime | None = Field(default=None, description="When token was revoked")
    expires_at: datetime = Field(description="When token expires")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )
    user_agent: str | None = Field(default=None, description="Client user agent")
    ip: str | None = Field(default=None, max_length=45, description="Client IP address")


class TokenRevocation(SQLModel, table=True):
    """Blacklist for revoked access tokens (by jti)."""

    __tablename__ = "token_revocation"

    id: int | None = Field(default=None, primary_key=True)
    jti: str = Field(max_length=64, unique=True, description="JWT ID of revoked token")
    exp: datetime = Field(description="Expiration time of the token")
    revoked_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


class LoginAttempt(SQLModel, table=True):
    """Track login attempts for brute-force protection."""

    __tablename__ = "auth_login_attempts"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(max_length=255, description="Email attempted")
    ip: str | None = Field(default=None, max_length=45, description="Client IP")
    success: bool = Field(description="Whether login succeeded")
    attempted_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


class SecurityEvent(SQLModel, table=True):
    """Security events for auditing and monitoring."""

    __tablename__ = "auth_security_events"

    id: int | None = Field(default=None, primary_key=True)
    event: str = Field(max_length=50, description="Event type (e.g., token_reuse, password_changed)")
    user_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=True),
        description="Related user (if any)"
    )
    ip: str | None = Field(default=None, max_length=45, description="Client IP")
    user_agent: str | None = Field(default=None, description="Client user agent")
    details: dict | None = Field(default=None, sa_column=Column(JSON), description="Additional event details")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


# === Sprint 2: CV Management (PR2) ===

class UserCV(SQLModel, table=True):
    """User CV model - stores PDF, extracted text, and structured data."""

    __tablename__ = "users_cvs"

    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=False),
        description="User who owns this CV"
    )
    original_filename: str = Field(max_length=500, description="Original PDF filename")
    detected_locale: str | None = Field(
        default=None, max_length=10,
        description="Detected locale (es/en) from CV content"
    )
    raw_blob: bytes | None = Field(
        default=None, description="Raw PDF binary data"
    )
    raw_text: str | None = Field(
        default=None, sa_column=Column(Text), description="Extracted text from PDF"
    )
    structured: dict = Field(
        sa_column=Column(JSON), description="Structured CV data (full_name, email, experience, etc.)"
    )
    embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(1024), nullable=True),
        description="Embedding vector (1024 dims)",
    )
    embedding_model: str | None = Field(
        default=None, max_length=100,
        description="Model that generated the embedding"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )
    last_edited_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()", onupdate=datetime.utcnow),
    )


# === Sprint 2: Free Audit (PR3) ===

class AuditUpload(SQLModel, table=True):
    """Anonymous CV audit upload - stored for 30 days max."""

    __tablename__ = "audit_uploads"

    id: int | None = Field(default=None, primary_key=True)
    audit_token_hash: str = Field(
        max_length=64, unique=True, description="SHA256 hash of the audit token"
    )
    cv_text: str | None = Field(
        default=None, sa_column=Column(Text), description="Extracted CV text"
    )
    jd_text: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Job description text (None for CV-only audits)",
    )
    pdf_blob: bytes | None = Field(
        default=None, description="Raw PDF binary data (max 10MB)"
    )
    audit_result_json: dict | None = Field(
        default=None, sa_column=Column(JSON), description="Match analysis result"
    )
    email_captured: bool = Field(
        default=False, description="Whether email was captured"
    )
    linked_user_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=True),
        description="User who claimed this audit after signup"
    )
    ip_hash: str | None = Field(
        default=None, max_length=64, description="SHA256 hash of client IP"
    )
    user_agent: str | None = Field(
        default=None, max_length=500, description="Client user agent"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="When this audit expires and can be deleted"
    )


class AuditFunnelEvent(SQLModel, table=True):
    """Telemetry events for the audit funnel."""

    __tablename__ = "audit_funnel_events"

    id: int | None = Field(default=None, primary_key=True)
    ip_hash: str | None = Field(
        default=None, max_length=64, description="SHA256 hash of client IP"
    )
    step: str = Field(
        max_length=50, description="Funnel step: audit_success, capture_email, audit_to_signup, audit_purged"
    )
    audit_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("audit_uploads.id"), nullable=True),
        description="Related audit upload"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


# === Sprint 2: Recruiter Roster (PR4) ===

class RecruiterConsent(SQLModel, table=True):
    """Recruiter consent record for ToS acceptance."""

    __tablename__ = "recruiter_consents"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=False, unique=True),
        description="User who gave consent"
    )
    accepted_at: datetime = Field(
        description="When consent was given"
    )
    tos_version: str = Field(max_length=50, description="Version of ToS accepted")
    ip: str | None = Field(default=None, max_length=45, description="Client IP at consent time")
    user_agent: str | None = Field(
        default=None, max_length=500, description="Client user agent at consent time"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


class RecruiterCandidateCV(SQLModel, table=True):
    """CV documents for external candidates."""

    __tablename__ = "recruiter_candidates_cvs"

    id: int | None = Field(default=None, primary_key=True)
    candidate_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("recruiter_candidates.id"), nullable=True),
        description="Candidate this CV belongs to"
    )
    original_filename: str = Field(max_length=500, description="Original PDF filename")
    raw_blob: bytes | None = Field(default=None, description="Raw PDF binary data (max 10MB)")
    raw_text: str | None = Field(
        default=None, sa_column=Column(Text), description="Extracted text from PDF"
    )
    structured: dict | None = Field(
        default=None, sa_column=Column(JSON), description="Structured CV data"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


class RecruiterCandidate(SQLModel, table=True):
    """External candidate managed by a recruiter."""

    __tablename__ = "recruiter_candidates"

    id: int | None = Field(default=None, primary_key=True)
    recruiter_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=False),
        description="Recruiter who owns this candidate"
    )
    full_name: str = Field(max_length=255, description="Candidate full name")
    email: str | None = Field(
        default=None, max_length=255, description="Candidate email (optional)"
    )
    phone: str | None = Field(default=None, max_length=50, description="Candidate phone")
    notes: str | None = Field(
        default=None, sa_column=Column(Text), description="Notes about the candidate"
    )
    cv_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("recruiter_candidates_cvs.id"), nullable=True),
        description="CV document for this candidate"
    )
    last_analysed_at: datetime | None = Field(
        default=None, description="Last time a match analysis was run"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), onupdate=datetime.utcnow),
    )


class RecruiterAnalysis(SQLModel, table=True):
    """Match analysis for a candidate against a job description."""

    __tablename__ = "recruiter_analyses"

    id: int | None = Field(default=None, primary_key=True)
    candidate_id: int = Field(
        sa_column=Column(Integer, ForeignKey("recruiter_candidates.id"), nullable=False),
        description="Candidate analyzed"
    )
    recruiter_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=False),
        description="Recruiter who requested the analysis"
    )
    jd_text: str = Field(sa_column=Column(Text), description="Job description text used")
    score: int | None = Field(default=None, ge=0, le=100, description="Match score 0-100")
    strengths: dict | None = Field(
        default=None, sa_column=Column(JSON), description="Identified strengths"
    )
    gaps: dict | None = Field(
        default=None, sa_column=Column(JSON), description="Identified gaps"
    )
    reasoning: str | None = Field(
        default=None, sa_column=Column(Text), description="AI reasoning for the score"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


class RecruiterAuditLog(SQLModel, table=True):
    """Audit log for recruiter actions (append-only)."""

    __tablename__ = "recruiter_audit_log"

    id: int | None = Field(default=None, primary_key=True)
    recruiter_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=False),
        description="Recruiter who performed the action"
    )
    candidate_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("recruiter_candidates.id"), nullable=True),
        description="Related candidate (if any)"
    )
    action: str = Field(max_length=50, description="Action performed")
    details: dict | None = Field(
        default=None, sa_column=Column(JSON), description="Additional details"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


# === Sprint 2: Billing (PR5) ===

class Subscription(SQLModel, table=True):
    """User subscription plan."""

    __tablename__ = "subscriptions"

    PLAN_TYPES: ClassVar = ("free", "job_seeker_monthly", "recruiter_starter", "recruiter_business", "recruiter_agency")
    STATUS_TYPES: ClassVar = ("active", "past_due", "canceled", "incomplete")

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=False),
        description="User who owns this subscription"
    )
    plan: str = Field(
        max_length=50,
        default="free",
        description="Plan type: free, job_seeker_monthly, recruiter_starter, recruiter_business, recruiter_agency"
    )
    status: str = Field(
        max_length=20,
        default="active",
        description="Subscription status: active, past_due, canceled, incomplete"
    )
    stripe_customer_id: str | None = Field(default=None, max_length=100, description="Stripe customer ID")
    stripe_subscription_id: str | None = Field(
        default=None, max_length=100, unique=True, description="Stripe subscription ID"
    )
    current_period_start: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True)), description="Current billing period start"
    )
    current_period_end: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True)), description="Current billing period end"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


class Payment(SQLModel, table=True):
    """Payment history."""

    __tablename__ = "payments"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=False),
        description="User who made the payment"
    )
    stripe_payment_intent_id: str | None = Field(
        default=None, max_length=100, description="Stripe payment intent ID"
    )
    amount_cents: int = Field(description="Payment amount in cents")
    currency: str = Field(max_length=3, default="usd", description="Currency code")
    status: str = Field(max_length=20, description="Payment status")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


class StripeWebhookEvent(SQLModel, table=True):
    """Idempotency ledger for Stripe webhooks."""

    __tablename__ = "stripe_webhook_events"

    id: int | None = Field(default=None, primary_key=True)
    event_id: str = Field(max_length=100, unique=True, description="Stripe event ID")
    type: str = Field(max_length=50, description="Event type")
    payload_json: dict = Field(sa_column=Column(JSON), description="Event payload")
    processed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True)), description="When event was processed"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )


class UsageCounter(SQLModel, table=True):
    """Monthly usage tracking for plan limits."""

    __tablename__ = "usage_counters"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id"), nullable=False),
        description="User whose usage is being tracked"
    )
    period_start: datetime = Field(
        sa_column=Column(DateTime(timezone=True)), description="Start of the billing period"
    )
    matches_used: int = Field(default=0, description="Number of matches used this period")
    analyses_used: int = Field(default=0, description="Number of analyses used this period")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default="NOW()"),
    )
