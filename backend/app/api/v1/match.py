"""
Match endpoint placeholder.
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["match"])


class MatchRequest(BaseModel):
    """Request body for match endpoint."""
    jd_text: str
    profile_id: int


class MatchResponse(BaseModel):
    """Response body for match endpoint."""
    score: float | None = None
    status: str
    message: str


@router.post("/match", response_model=MatchResponse)
async def match(request: MatchRequest) -> MatchResponse:
    """
    Placeholder for match endpoint.

    This will be implemented in Sprint 1 with actual LLM integration.
    """
    return MatchResponse(
        score=None,
        status="not_implemented_yet",
        message="match endpoint will be implemented in Sprint 1",
    )
