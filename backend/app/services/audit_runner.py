"""
Audit runner service - orchestrates CV vs JD match for anonymous audits.

This service reuses the existing match provider call but:
- Does NOT run the profile retrieval pipeline (no persisted Profile to
  retrieve from; the extracted CV text is passed straight to the prompt)
- Does NOT persist to analyses table
- Does NOT persist to users_cvs table
- Returns the result directly to the caller
- Stores minimal data in audit_uploads for potential email capture
"""
from dataclasses import dataclass
from dataclasses import field as dataclasses_field
from typing import Any

import groq
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm.factory import get_llm_provider

logger = get_logger("app.services.audit_runner")

# Minimum JD length (same as match endpoint)
MIN_JD_LENGTH = 50

# Minimum CV length for the CV-only audit (same as endpoint validation)
MIN_CV_LENGTH = 50


@dataclass
class AuditResult:
    """Result of an anonymous audit."""

    score: int
    strengths: list[str]
    gaps: list[str]
    energy_level: str
    reasoning: str
    result_json: dict[str, Any]
    mode: str = "jd_directed"
    problematicas: list[dict[str, Any]] = dataclasses_field(default_factory=list)
    recomendaciones: list[str] = dataclasses_field(default_factory=list)


async def run_audit(
    session: AsyncSession,
    jd_text: str,
    cv_text: str | None = None,
    pdf_bytes: bytes | None = None,
) -> AuditResult:
    """
    Run a JD-directed audit: score a job description against the uploaded CV.

    The anonymous funnel has no persisted ``Profile``, so the CV text the
    endpoint already extracted is the only real candidate context. It goes
    into the match prompt directly, mirroring the recruiter-candidate path
    (``api/v1/recruiter_candidates.py``), which matches a JD against an
    uploaded CV the same way.

    The retrieval pipeline is deliberately NOT used here.
    ``retrieve_profile_context`` derives its output exclusively from
    ``Profile.experience`` / ``skills`` / ``preferences``. A synthetic
    ``Profile`` carrying the CV nowhere serializes to a handful of chars, so
    retrieval always short-circuits to ``mode="complete"`` and returns the
    empty profile's own JSON -- which used to overwrite the ``cv_text``
    fallback and make the audit a match between the JD and nothing at all.
    Retrieval still runs for the authenticated path (``/v1/match``), which
    has a real stored Profile to select fragments from.

    Args:
        session: Unused. This path performs no database work; kept in the
            signature for parity with the other service entry points.
        jd_text: Job description text (must be >= 50 chars)
        cv_text: Extracted CV text (text or parsed from the uploaded PDF)
        pdf_bytes: Unused. The endpoint already persists the raw bytes on the
            ``audit_uploads`` row; scoring only needs the extracted text.

    Returns:
        AuditResult with score, strengths, gaps, energy_level, reasoning

    Raises:
        ValueError: If JD is too short (< 50 chars)
    """
    if len(jd_text.strip()) < MIN_JD_LENGTH:
        raise ValueError(f"JD_TOO_SHORT: JD must be at least {MIN_JD_LENGTH} characters")

    provider = get_llm_provider()

    # The endpoint guarantees a non-empty CV (>= 50 chars) on this path; the
    # placeholder only guards direct service callers.
    profile_context_text = cv_text or "No CV text provided"

    # Generate match analysis via LLM
    try:
        analysis = await provider.generate_match(
            jd_text=jd_text,
            profile_context={
                "id": 0,
                "name": "Anonymous",
                "headline": "Anonymous CV",
                "experience": "",
                "skills": "",
                "preferences": "",
                "retrieval_mode": "full",
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
        "mode": "jd_directed",
        "score": analysis.score,
        "strengths": analysis.strengths,
        "gaps": analysis.gaps,
        "energy_level": analysis.energy_level,
        "reasoning": analysis.reasoning,
    }

    return AuditResult(
        mode="jd_directed",
        score=analysis.score,
        strengths=analysis.strengths,
        gaps=analysis.gaps,
        energy_level=analysis.energy_level,
        reasoning=analysis.reasoning,
        result_json=result_json,
    )


async def run_cv_audit(cv_text: str) -> AuditResult:
    """
    Run a CV quality audit WITHOUT a job description.

    The free audit hook: finds problems in the CV itself (missing sections,
    unquantified achievements, weak verbs, inconsistent dates, etc.).

    Args:
        cv_text: Extracted CV text (must be >= 50 chars)

    Returns:
        AuditResult with mode="cv_only" and the CV quality analysis

    Raises:
        ValueError: If CV text is too short (< 50 chars)
    """
    if not cv_text or len(cv_text.strip()) < MIN_CV_LENGTH:
        raise ValueError(f"CV_TOO_SHORT: CV must be at least {MIN_CV_LENGTH} characters")

    provider = get_llm_provider()

    try:
        audit = await provider.generate_cv_audit(cv_text)
    except groq.RateLimitError as exc:
        logger.error("audit_cv_llm_rate_limit", error=str(exc)[:200])
        raise RuntimeError("LLM rate limit exceeded") from exc
    except Exception as exc:
        logger.error("audit_cv_llm_failed", error=str(exc)[:200])
        raise RuntimeError(f"CV audit generation failed: {exc}") from exc

    problematicas: list[dict[str, Any]] = [issue.model_dump() for issue in audit.problematicas]
    high_severity = sum(1 for issue in audit.problematicas if issue.severidad == "high")
    reasoning = (
        f"Auditoría de calidad del CV: {len(problematicas)} problemáticas detectadas "
        f"({high_severity} de severidad alta) y {len(audit.recomendaciones)} recomendaciones."
    )
    energy_level = "high" if audit.score >= 75 else ("medium" if audit.score >= 50 else "low")

    result_json = {
        "mode": "cv_only",
        "score": audit.score,
        "problematicas": problematicas,
        "recomendaciones": audit.recomendaciones,
        "fortalezas": audit.fortalezas,
        "strengths": audit.fortalezas,
        "gaps": [issue["problema"] for issue in problematicas],
        "energy_level": energy_level,
        "reasoning": reasoning,
    }

    return AuditResult(
        mode="cv_only",
        score=audit.score,
        strengths=audit.fortalezas,
        gaps=[issue["problema"] for issue in problematicas],
        energy_level=energy_level,
        reasoning=reasoning,
        problematicas=problematicas,
        recomendaciones=audit.recomendaciones,
        result_json=result_json,
    )
