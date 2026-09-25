"""
Candidate ranking service for hybrid ranking.

This service provides the ranking logic for candidates:
- match_score × recency_decay
- recency_decay = exp(-días / 30)
- floor: effective_score >= 0.5 × match_score when match_score >= 0.7
"""
import math
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RecruiterAnalysis, RecruiterCandidate


def calculate_recency_decay(last_analysed_at: datetime | None) -> float:
    """
    Calculate recency decay factor.

    Returns exp(-days_since_analysis / 30)
    If last_analysed_at is None, returns 1.0 (no decay for never-analysed)
    """
    if last_analysed_at is None:
        return 1.0

    now = datetime.now(UTC)
    if last_analysed_at.tzinfo is None:
        last_analysed_at = last_analysed_at.replace(tzinfo=UTC)

    days_since = (now - last_analysed_at).total_seconds() / (24 * 3600)
    return math.exp(-days_since / 30)


def calculate_effective_score(
    match_score: float,
    last_analysed_at: datetime | None,
    apply_floor: bool = True,
) -> float:
    """
    Calculate effective score with recency decay and floor.

    Formula: effective_score = match_score × recency_decay

    Floor rule: if match_score >= 0.7 and apply_floor is True,
    effective_score >= 0.5 × match_score
    """
    recency_decay = calculate_recency_decay(last_analysed_at)
    effective = match_score * recency_decay

    # Apply floor rule for high match scores
    if apply_floor and match_score >= 0.7:
        floor = 0.5 * match_score
        effective = max(effective, floor)

    return effective


async def rank_candidates(
    recruiter_id: int,
    jd_text: str,
    db: AsyncSession,
    top_k: int = 10,
) -> list[tuple[RecruiterCandidate, float]]:
    """
    Rank candidates by hybrid scoring (match × recency).

    This function:
    1. Gets all candidates for the recruiter
    2. For each candidate, calculates effective score
    3. Returns top-k sorted by effective score descending

    Note: The actual LLM matching would be done by the caller
    (the endpoint), this function handles ranking logic.
    """
    # Get all candidates for this recruiter
    result = await db.execute(
        select(RecruiterCandidate).where(
            RecruiterCandidate.recruiter_id == recruiter_id
        )
    )
    candidates = result.scalars().all()

    if not candidates:
        return []

    # For each candidate, find their latest analysis
    scored_candidates = []

    for candidate in candidates:
        # Get latest analysis for this candidate
        analysis_result = await db.execute(
            select(RecruiterAnalysis).where(
                RecruiterAnalysis.candidate_id == candidate.id
            ).order_by(RecruiterAnalysis.created_at.desc())
        )
        analysis = analysis_result.scalar_one_or_none()

        if analysis and analysis.score is not None:
            # Convert 0-100 score to 0-1 float
            match_score = analysis.score / 100.0
            effective = calculate_effective_score(
                match_score,
                candidate.last_analysed_at,
                apply_floor=True,
            )
            scored_candidates.append((candidate, effective))
        else:
            # No analysis yet - include at end with 0 score
            scored_candidates.append((candidate, 0.0))

    # Sort by effective score descending
    scored_candidates.sort(key=lambda x: x[1], reverse=True)

    # Return top-k
    return scored_candidates[:top_k]


async def get_or_compute_match_score(
    candidate_id: int,
    jd_text: str,
    db: AsyncSession,
) -> tuple[int | None, bool]:
    """
    Get cached match score or indicate need to compute.

    Returns:
        (score, needs_computation) - score is None if not cached
    """
    # Look for existing analysis with same JD hash
    # For simplicity, we'll just check if there's any recent analysis
    # In production, you'd hash the JD and cache it

    result = await db.execute(
        select(RecruiterAnalysis).where(
            RecruiterAnalysis.candidate_id == candidate_id,
            RecruiterAnalysis.jd_text == jd_text,
        ).order_by(RecruiterAnalysis.created_at.desc())
    )
    analysis = result.scalar_one_or_none()

    if analysis:
        return analysis.score, False

    return None, True
