"""
Internal cleanup endpoint for the ``cv_adaptations`` sweeper.

Called by the ``adaptation-sweeper.yml`` GitHub Actions cron job every
15 minutes. The endpoint deletes:

1. ``completed`` rows older than 90 days — keeps the table bounded
   while preserving the typical "I came back a week later" UX window.
2. ``pending`` rows older than 1 hour — orphans from a Render restart
   whose runner never came back. ``created_at`` is the spawn time
   recorded by the endpoint; a row that's still pending after 1 h
   means the runner died before flushing terminal status.

Auth
----
The endpoint expects ``X-Backend-API-Key: <token>``. We use the same
``backend_api_key`` setting as the rest of the protected endpoints
(``/v1/*`` in protected mode); no JWT — the cron job can't carry one.

Response
--------
``{"deleted": N}`` — number of rows removed in this sweep. N=0 is a
successful sweep, not an error.

Wiring
------
Mounted at ``/internal/adaptations/cleanup`` (no ``/v1`` prefix).
The router prefix in ``app.main`` is ``/internal``.
"""
from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import and_, delete

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import CVAdaptation
from app.db.session import get_session_context
from app.services.rls_context import set_rls_service

logger = get_logger("app.api.internal.adaptations")

router = APIRouter(tags=["adaptations-internal"])

# Retention windows. Tuned to balance DB size against UX. The
# "1 hour pending" window specifically targets Render's typical cold
# start delay plus a comfortable buffer; rows older than that are
# almost certainly dead jobs.
COMPLETED_RETENTION_DAYS = 90
PENDING_ORPHAN_HOURS = 1

API_KEY_HEADER = "X-Backend-API-Key"


def _verify_api_key(provided: str | None) -> bool:
    """Constant-time compare against the configured ``BACKEND_API_KEY``.

    Returns ``False`` when the key isn't configured (open mode): the
    sweeper only fires from the GitHub Actions cron, so an open
    environment is just unprotected. In production ``BACKEND_API_KEY``
    is always set.
    """
    settings = get_settings()
    expected = settings.backend_api_key
    if not expected:
        logger.warning("internal_cleanup_no_api_key_configured")
        return False
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


@router.post("/adaptations/cleanup")
async def cleanup_adaptations(
    x_backend_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> dict[str, int]:
    """Delete expired completed rows and orphaned pending rows.

    Returns:
        ``{"deleted": N}`` with N = sum of completed + orphaned pending
        rows removed in this sweep.
    """
    if not _verify_api_key(x_backend_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="UNAUTHORIZED",
        )

    now = datetime.now(UTC)
    completed_threshold = now - timedelta(days=COMPLETED_RETENTION_DAYS)
    pending_threshold = now - timedelta(hours=PENDING_ORPHAN_HOURS)

    async with get_session_context() as session:
        await set_rls_service(session)

        # Two DELETEs in a single transaction. RLS bypass is granted to
        # the service context (migration 016), so cross-owner rows are
        # reachable in one statement.
        # ``completed_at`` is typed ``datetime | None`` in the model; the
        # ``IS NOT NULL`` predicate narrows it at the SQL level but mypy
        # can't see through SQLAlchemy column expressions, so we cast.
        completed_result = await session.execute(
            delete(CVAdaptation).where(
                and_(
                    CVAdaptation.status == "completed",
                    CVAdaptation.completed_at.is_not(None),
                    CVAdaptation.completed_at < completed_threshold,  # type: ignore[operator]
                )
            )
        )
        pending_result = await session.execute(
            delete(CVAdaptation).where(
                and_(
                    CVAdaptation.status == "pending",
                    CVAdaptation.created_at < pending_threshold,
                )
            )
        )
        await session.commit()

        deleted_completed = completed_result.rowcount or 0
        deleted_pending = pending_result.rowcount or 0
        deleted_total = deleted_completed + deleted_pending

    logger.info(
        "adaptation_cleanup_swept",
        deleted_completed=deleted_completed,
        deleted_pending=deleted_pending,
        deleted_total=deleted_total,
    )
    return {"deleted": deleted_total}
