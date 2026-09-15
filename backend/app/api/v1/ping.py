"""
Ping endpoint.
"""
from datetime import UTC, datetime

from fastapi import APIRouter

router = APIRouter(tags=["ping"])


@router.get("/ping")
async def ping() -> dict[str, bool | str]:
    """Ping endpoint with timestamp."""
    return {
        "pong": True,
        "timestamp": datetime.now(UTC).isoformat(),
    }
