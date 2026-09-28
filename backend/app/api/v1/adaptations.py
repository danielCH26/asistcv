"""
Adaptation endpoints (Slice A, sprint-adapt-cv-outreach, PR2b).

Public API
----------
- ``POST /v1/adaptations`` — submit a CV+JD for adaptation. Returns 202
  with the new adaptation_id, or 200 with a cached result on hit.
- ``GET /v1/adaptations/{id}`` — poll the status / fetch the result.
- ``GET /v1/adaptations/by-cv/{cv_id}`` — list user's adaptations for
  a CV (newest first, limit 20).

All endpoints require JWT auth (job_seeker or recruiter). Service
context (API key) is rejected for the user-facing endpoints; the
internal sweeper endpoint has its own auth.

Status machine
--------------
pending → completed  (success)
pending → failed     (LLM_ERROR | INVALID_HONESTY)

The 202 response carries ``adaptation_id`` only; clients poll
``GET /v1/adaptations/{id}`` until ``status`` is terminal. Render
restarts don't lose pending rows — the runner picks them up next time
the endpoint is invoked.

Cache semantics
---------------
The endpoint checks ``get_cached`` BEFORE creating a new row. A hit
short-circuits to 200 with the cached payload (status=completed); no
LLM call is issued, no new row is created. The cache key is
``(parent_cv_id, content_version, jd_text_hash)`` and a hit requires
all three to match.

Error shape
-----------
Errors follow the project convention ``{"code": "..."}`` for machine
codes (``PLAN_LIMIT_REACHED``, ``NO_CV_FOUND``, etc.) and use
``HTTPException(detail="...")`` so the OpenAPI doc and client error
handlers stay aligned.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    get_current_user,
    get_db,
    get_runner,
    require_adaptation_enabled,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import CVAdaptation, UserCV
from app.services.adaptation_cache import (
    compute_jd_text_hash,
    get_cached,
)
from app.services.adaptation_runner import AdaptationRunner
from app.services.tier_limits import check_limit

logger = get_logger("app.api.adaptations")

router = APIRouter(prefix="/adaptations", tags=["adaptations"])


# === Request / response schemas ===


class AdaptationCreateRequest(BaseModel):
    """Body for ``POST /v1/adaptations``."""

    cv_id: int = Field(..., description="Source CV id (must belong to the caller).")
    jd_text: str = Field(
        ..., min_length=1, description="Free-text job description."
    )


class AdaptationSummary(BaseModel):
    """Summary view of an adaptation for the list endpoint."""

    id: int
    cv_id: int | None
    status: str
    jd_text_hash: str
    created_at: str
    completed_at: str | None
    error_code: str | None


class AdaptationDetail(BaseModel):
    """Full payload for a single adaptation.

    ``adapted_cv`` is ``None`` for pending rows (runner hasn't finished)
    and for failed rows (no payload to return).
    """

    id: int
    cv_id: int | None
    status: str
    adapted_cv: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    jd_text_hash: str
    created_at: str
    completed_at: str | None


class AdaptationAcceptedResponse(BaseModel):
    """202 response — the row was created and the runner was spawned."""

    adaptation_id: int
    status: str


def _row_to_detail(row: CVAdaptation) -> AdaptationDetail:
    """Convert a ``CVAdaptation`` ORM row to the API detail payload.

    ``adapted_cv`` is omitted (null) when the row is pending or failed;
    completed rows expose the validated payload.
    """
    adapted_cv: dict[str, Any] | None = None
    if row.status == "completed":
        adapted_cv = row.adapted_cv_json
    return AdaptationDetail(
        id=row.id,
        cv_id=row.parent_cv_id,
        status=row.status,
        adapted_cv=adapted_cv,
        error_code=row.error_code,
        error_message=row.error_message,
        jd_text_hash=row.jd_text_hash,
        created_at=row.created_at.isoformat(),
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
    )


def _row_to_summary(row: CVAdaptation) -> AdaptationSummary:
    """Convert a ``CVAdaptation`` ORM row to the list-summary payload."""
    return AdaptationSummary(
        id=row.id,
        cv_id=row.parent_cv_id,
        status=row.status,
        jd_text_hash=row.jd_text_hash,
        created_at=row.created_at.isoformat(),
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        error_code=row.error_code,
    )


# === Helpers


async def _resolve_cv_for_user(
    session: AsyncSession, cv_id: int, owner_user_id: int
) -> UserCV | None:
    """Load the source CV and confirm the caller owns it.

    Uses the user-bound RLS context (set by ``get_db`` upstream), so
    cross-user rows are filtered by the policy in addition to this
    explicit WHERE clause. Defense in depth: both layers must agree.
    """
    result = await session.execute(
        select(UserCV).where(
            UserCV.id == cv_id, UserCV.owner_user_id == owner_user_id
        )
    )
    return result.scalar_one_or_none()


# === Endpoints


@router.post(
    "",
    dependencies=[Depends(require_adaptation_enabled)],
)
async def create_adaptation(
    payload: AdaptationCreateRequest,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    runner: AdaptationRunner = Depends(get_runner),
) -> AdaptationAcceptedResponse | AdaptationDetail:
    """Submit a CV+JD for asynchronous adaptation.

    Flow:
        1. Tier enforcement — 402 ``PLAN_LIMIT_REACHED`` if exceeded.
        2. CV ownership — 404 ``NO_CV_FOUND`` if cv_id is missing or
           not owned by the caller.
        3. Cache check — 200 with cached payload on hit (no row
           created, no LLM call).
        4. Row creation — insert a pending ``CVAdaptation`` row with
           the JD text stored as UTF-8 bytes in ``jd_text_encrypted``.
        5. Spawn the runner via ``asyncio.create_task`` and return 202.

    Args:
        payload: ``{cv_id, jd_text}``.
        response: FastAPI Response (we set status_code dynamically).
        current_user: JWT-authenticated principal.
        db: RLS-bound async session (``get_db`` binds the user).
        runner: Injected ``AdaptationRunner``.

    Returns:
        On cache hit: 200 with the full ``AdaptationDetail`` payload.
        On miss: 202 with ``{adaptation_id, status: "pending"}``.
    """
    settings = get_settings()
    if not settings.adaptation_enabled:
        # Belt-and-suspenders: require_adaptation_enabled already 503'd,
        # but the boolean re-check is cheap and protects tests that
        # override the dependency.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FEATURE_DISABLED",
        )

    # Tier enforcement: free users / over-quota → 402. The RLS GUC is
    # already bound by ``get_db`` to the caller's id.
    if current_user.id != 0:
        try:
            await check_limit(db, current_user.id, "adaptation", current_user.role)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="PLAN_LIMIT_REACHED",
            ) from exc

    # Resolve + ownership check on the source CV.
    cv = await _resolve_cv_for_user(db, payload.cv_id, current_user.id)
    if cv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="NO_CV_FOUND",
        )

    jd_hash = compute_jd_text_hash(payload.jd_text)

    # Cache check (RLS-bound session; cv_adaptations + users_cvs
    # policies apply). Returns the most recent valid completed row.
    cached = await get_cached(
        session=db,
        cv_id=payload.cv_id,
        content_version=cv.content_version,
        jd_text_hash=jd_hash,
    )
    if cached is not None:
        logger.info(
            "adaptation_cache_hit",
            adaptation_id=cached.id,
            owner_user_id=current_user.id,
            cv_id=payload.cv_id,
        )
        # Cached rows are by definition completed; surface the full
        # detail payload so the client can render immediately.
        response.status_code = status.HTTP_200_OK
        return _row_to_detail(cached)

    # Create the pending row. JD text stored as UTF-8 bytes in
    # jd_text_encrypted — encryption wiring is a follow-up.
    row = CVAdaptation(
        parent_cv_id=cv.id,
        owner_user_id=current_user.id,
        jd_text_hash=jd_hash,
        jd_text_encrypted=payload.jd_text.encode("utf-8"),
        adapted_cv_json={},
        status="pending",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    logger.info(
        "adaptation_row_created",
        adaptation_id=row.id,
        owner_user_id=current_user.id,
        cv_id=cv.id,
    )

    # Spawn the runner. We don't await it — the response returns
    # immediately and the runner writes terminal status to the row.
    asyncio.create_task(_run_in_background(runner, row.id))

    response.status_code = status.HTTP_202_ACCEPTED
    return AdaptationAcceptedResponse(adaptation_id=row.id, status="pending")


async def _run_in_background(runner: AdaptationRunner, adaptation_id: int) -> None:
    """Wrap the runner in a logging boundary so unhandled errors don't crash.

    ``AdaptationRunner.run`` already catches its own exceptions, but a
    guard here protects against future refactors that might forget the
    try/except. Returns None — this coroutine is fire-and-forget.
    """
    try:
        await runner.run(adaptation_id)
    except Exception as exc:
        logger.exception(
            "adaptation_runner_unhandled",
            adaptation_id=adaptation_id,
            error=str(exc)[:200],
        )


@router.get("/by-cv/{cv_id}", response_model=list[AdaptationSummary])
async def list_adaptations_for_cv(
    cv_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AdaptationSummary]:
    """List the caller's adaptations for a single CV.

    Returns the most recent 20 rows in reverse chronological order.
    Cross-user rows are filtered by RLS + an explicit owner_id check.
    """
    # Ownership: must own the CV (defense in depth; RLS already filters).
    cv = await _resolve_cv_for_user(db, cv_id, current_user.id)
    if cv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="NO_CV_FOUND",
        )

    result = await db.execute(
        select(CVAdaptation)
        .where(
            CVAdaptation.parent_cv_id == cv_id,
            CVAdaptation.owner_user_id == current_user.id,
        )
        .order_by(CVAdaptation.created_at.desc())
        .limit(20)
    )
    rows = result.scalars().all()
    return [_row_to_summary(row) for row in rows]


@router.get("/{adaptation_id}", response_model=AdaptationDetail)
async def get_adaptation(
    adaptation_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdaptationDetail:
    """Fetch the status / result of one adaptation.

    404 ``NOT_FOUND`` when the row doesn't exist or isn't owned by the
    caller. Pending rows return ``status="pending"`` with
    ``adapted_cv=null``; completed rows expose the validated payload;
    failed rows expose ``error_code`` + ``error_message``.
    """
    result = await db.execute(
        select(CVAdaptation).where(
            CVAdaptation.id == adaptation_id,
            CVAdaptation.owner_user_id == current_user.id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="NOT_FOUND",
        )
    return _row_to_detail(row)
