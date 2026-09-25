"""
Audit runner service - orchestrates CV vs JD match for anonymous audits.

This service reuses the existing match logic but:
- Does NOT persist to analyses table
- Does NOT persist to users_cvs table
- Returns the result directly to the caller
- Stores minimal data in audit_uploads for potential email capture
"""
from dataclasses import dataclass
from typing import Any

import groq
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.factory import get_llm_provider
from app.services.retrieval import retrieve_profile_context

logger = get_logger("app.services.audit_runner")

# Minimum JD length (same as match endpoint)
MIN_JD_LENGTH = 50


@dataclass
class AuditResult:
    """Result of an anonymous audit."""

    score: int
    strengths: list[str]
    gaps: list[str]
    energy_level: str
    reasoning: str
    result_json: dict[str, Any]


async def run_audit(
    session: AsyncSession,
    jd_text: str,
    cv_text: str | None = None,
    pdf_bytes: bytes | None = None,
) -> AuditResult:
    """
    Run an audit analysis on JD vs CV.

    Args:
        session: Database session
        jd_text: Job description text (must be >= 50 chars)
        cv_text: Extracted CV text (optional, for text-based matching)
        pdf_bytes: Raw PDF bytes (optional, for future PDF-based matching)

    Returns:
        AuditResult with score, strengths, gaps, energy_level, reasoning

    Raises:
        ValueError: If JD is too short (< 50 chars)
    """
    if len(jd_text.strip()) < MIN_JD_LENGTH:
        raise ValueError(f"JD_TOO_SHORT: JD must be at least {MIN_JD_LENGTH} characters")

    settings = get_settings()
    provider = get_llm_provider()

    # Step 1: Generate JD embedding
    try:
        jd_embedding = await provider.generate_embedding(jd_text)
    except Exception as exc:
        logger.error("audit_jd_embedding_failed", error=str(exc)[:200])
        raise RuntimeError(f"Embedding provider failed: {exc}") from exc

    # Step 2: Build profile context from CV text (or mock profile)
    # For anonymous audit, we use the CV text directly as a "profile"
    # The retrieval service expects a Profile object, so we create a minimal mock

    # Create a mock profile object for retrieval
    from app.db.models import Profile

    mock_profile = Profile(
        id=0,
        name="Anonymous",
        headline="Anonymous CV",
        experience={},
        skills={},
        preferences={},
        embedding=list(jd_embedding.vector) if jd_embedding.vector else None,
    )

    # Step 3: Run retrieval (even for anonymous, to get best context)
    try:
        profile_context = await retrieve_profile_context(
            profile=mock_profile,
            jd_embedding=list(jd_embedding.vector),
            settings=settings,
            provider=provider,
            regenerate_profile_embedding=False,
        )
    except Exception as exc:
        logger.warning("audit_retrieval_failed", error=str(exc)[:200])
        # Fall back to using CV text directly as context
        profile_context_text = cv_text or "No CV text provided"
    else:
        profile_context_text = profile_context.text

    # Step 4: Generate match analysis via LLM
    try:
        analysis = await provider.generate_match(
            jd_text=jd_text,
            profile_context={
                "id": 0,
                "name": "Anonymous",
                "headline": "Anonymous CV",
                "experience": {},
                "skills": {},
                "preferences": {},
                "retrieval_mode": "complete",
                "retrieval_context": profile_context_text,
            },
        )
    except groq.RateLimitError as exc:
        logger.error("audit_llm_rate_limit", error=str(exc)[:200])
        raise RuntimeError("LLM rate limit exceeded") from exc
    except Exception as exc:
        logger.error("audit_llm_failed", error=str(exc)[:200])
        raise RuntimeError(f"Analysis generation failed: {exc}") from exc

    # Build result JSON for storage
    result_json = {
        "score": analysis.score,
        "strengths": analysis.strengths,
        "gaps": analysis.gaps,
        "energy_level": analysis.energy_level,
        "reasoning": analysis.reasoning,
    }

    return AuditResult(
        score=analysis.score,
        strengths=analysis.strengths,
        gaps=analysis.gaps,
        energy_level=analysis.energy_level,
        reasoning=analysis.reasoning,
        result_json=result_json,
    )
