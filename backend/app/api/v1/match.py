"""
Match endpoint for JD vs profile analysis.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.models import Profile
from app.db.session import get_session
from app.llm.factory import get_llm_provider

router = APIRouter(tags=["match"])


class MatchRequest(BaseModel):
    """Request body for match endpoint."""
    jd_text: str
    profile_id: int


class MatchResponse(BaseModel):
    """Response body for match endpoint."""
    score: int
    strengths: list[str]
    gaps: list[str]
    energy_level: str
    reasoning: str


@router.post("/match", response_model=MatchResponse)
async def match(
    request: MatchRequest,
    session: AsyncSession = Depends(get_session),
) -> MatchResponse:
    """
    Analyze match between a job description and a profile.

    Uses the configured LLM provider (mock or groq) to generate
    the match analysis. The full profile is loaded from the DB and
    passed as context to the LLM.

    Note: For Sprint 0.5 we load the full profile as context. In Sprint 1
    (issue #16) this will be replaced by semantic retrieval over the
    profile's embeddings.
    """
    try:
        # Load profile from DB
        result = await session.execute(
            select(Profile).where(Profile.id == request.profile_id)
        )
        profile = result.scalar_one_or_none()

        if profile is None:
            raise HTTPException(
                status_code=404,
                detail=f"Profile with id {request.profile_id} not found",
            )

        # Build profile context from DB record
        profile_context = {
            "id": profile.id,
            "name": profile.name,
            "headline": profile.headline,
            "experience": profile.experience,
            "skills": profile.skills,
            "preferences": profile.preferences,
        }

        # Generate match analysis
        provider = get_llm_provider()
        analysis = await provider.generate_match(
            jd_text=request.jd_text,
            profile_context=profile_context,
        )

        return MatchResponse(
            score=analysis.score,
            strengths=analysis.strengths,
            gaps=analysis.gaps,
            energy_level=analysis.energy_level,
            reasoning=analysis.reasoning,
        )

    except HTTPException:
        raise
    except NotImplementedError as e:
        raise HTTPException(
            status_code=501,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating match analysis: {str(e)}",
        )
