"""
Match endpoint for JD vs profile analysis.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
async def match(request: MatchRequest) -> MatchResponse:
    """
    Analyze match between a job description and a profile.

    Uses the configured LLM provider (mock or vertex) to generate
    the match analysis.
    """
    try:
        provider = get_llm_provider()

        # Build profile context from request
        profile_context = {"profile_id": request.profile_id}

        # Generate match analysis
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
