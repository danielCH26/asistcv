"""
Job-offer endpoints: list, archive, run search, and preferences.

- GET /v1/job-offers: paginated list, RLS-filtered, status filter.
- POST /v1/job-offers/{id}/archive: mark own offer as archived.
- POST /v1/job-offers/run: trigger offer search for the current user.
- PUT /v1/me/offer-preferences: persist notification preferences in JSONB.

``search_query`` is stored for auditability but is intentionally excluded
from the list response — it is an internal pipeline detail, not user-facing.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.api.deps import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.models import JobOffer, User
from app.db.session import get_session_context
from app.llm.factory import get_llm_provider
from app.services.offer_prefs import OfferPrefs
from app.services.offer_search_client import (
    OfferSearchAuthError,
    OfferSearchConnectionError,
    OfferSearchRateLimitError,
    OfferSearchTimeoutError,
)
from app.services.offer_search_worker import OfferRunResult, run_offer_search
from app.services.rls_context import bind_rls_context

router = APIRouter(tags=["job-offers"])
logger = get_logger("app.api.job_offers")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class JobOfferResponse(BaseModel):
    """Response body for a single job offer (search_query excluded — internal)."""

    id: int
    title: str
    company: str | None
    url: str
    snippet: str | None
    published_date: str | None
    score: int | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JobOfferListResponse(BaseModel):
    """Paginated list response."""

    items: list[JobOfferResponse]
    total: int
    limit: int
    offset: int


class OfferRunResponse(BaseModel):
    """Response from POST /v1/job-offers/run."""

    found: int
    new_offers: int
    skipped_stale: bool


class OfferPreferencesRequest(BaseModel):
    """Request body for PUT /v1/me/offer-preferences."""

    frequency_hours: int | None = Field(
        default=None,
        ge=1,
        le=168,
        description="How often to run the search (1-168 hours)",
    )
    top_n: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Maximum number of offers to surface per run (1-20)",
    )
    email_frequency: str | None = Field(
        default=None,
        description="When to email: none | daily | weekly",
        pattern=r"^(none|daily|weekly)$",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Arbitrary offer filters (e.g. {'remote_only': True})",
    )


class OfferPreferencesResponse(BaseModel):
    """Response body for offer preferences (resolved with defaults)."""

    frequency_hours: int
    top_n: int
    email_frequency: str
    filters: dict[str, Any] | None


# ---------------------------------------------------------------------------
# GET /v1/job-offers
# ---------------------------------------------------------------------------


@router.get("/job-offers", response_model=JobOfferListResponse)
async def list_job_offers(
    current_user: CurrentUser = Depends(get_current_user),
    status: str | None = Query(default=None, description="Filter by status: new | archived"),
    limit: int = Query(default=20, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
) -> JobOfferListResponse:
    """
    List job offers for the current user (RLS-filtered).

    Returns a paginated list ordered by ``created_at`` DESC.
    ``search_query`` is excluded from the response — it is an internal
    audit field, not user-facing data.
    """
    async with get_session_context() as session:
        await bind_rls_context(session, current_user.id, current_user.role)

        # Count query — use func.count() for a single-row SQL result
        count_query = select(func.count(JobOffer.id)).where(
            JobOffer.owner_user_id == current_user.id
        )
        if status is not None:
            count_query = count_query.where(JobOffer.status == status)
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        # Data query
        query = (
            select(JobOffer)
            .where(JobOffer.owner_user_id == current_user.id)
            .order_by(JobOffer.created_at.desc())
        )
        if status is not None:
            query = query.where(JobOffer.status == status)
        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        rows = result.scalars().all()

    # Serialize, dropping search_query before response.
    items = [
        JobOfferResponse(
            id=row.id,
            title=row.title,
            company=row.company,
            url=row.url,
            snippet=row.snippet,
            published_date=row.published_date,
            score=row.score,
            status=row.status,
            created_at=row.created_at,
        )
        for row in rows
    ]

    return JobOfferListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# POST /v1/job-offers/{id}/archive
# ---------------------------------------------------------------------------


@router.post("/job-offers/{offer_id}/archive", response_model=JobOfferResponse)
async def archive_job_offer(
    offer_id: int,
    current_user: CurrentUser = Depends(get_current_user),
) -> JobOfferResponse:
    """
    Archive a job offer (mark it as no longer of interest).

    Only the owning user can archive their own offers (RLS-enforced).
    Returns 404 for non-existent or cross-user offers.
    """
    async with get_session_context() as session:
        await bind_rls_context(session, current_user.id, current_user.role)

        row = await session.get(JobOffer, offer_id)

    if row is None or row.owner_user_id != current_user.id:
        # 404: don't reveal existence to non-owners (mirrors match.py pattern).
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    async with get_session_context() as session:
        await bind_rls_context(session, current_user.id, current_user.role)
        row = await session.get(JobOffer, offer_id)
        if row is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        row.status = "archived"
        await session.commit()
        await session.refresh(row)

    return JobOfferResponse.model_validate(row)


# ---------------------------------------------------------------------------
# POST /v1/job-offers/run
# ---------------------------------------------------------------------------


@router.post("/job-offers/run", response_model=OfferRunResponse)
async def run_offer_search_endpoint(
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> OfferRunResponse:
    """
    Trigger the offer-search pipeline for the current user.

    Calls ``run_offer_search`` with the Tavily client and embedding
    provider resolved from settings. Errors from the search client are
    mapped to typed HTTPException responses.
    """
    search_client = _build_search_client(settings)
    embedding_provider = get_llm_provider()

    try:
        result: OfferRunResult = await run_offer_search(
            user_id=current_user.id,
            session_factory=_session_factory(),
            settings=settings,
            search_client=search_client,
            embedding_provider=embedding_provider,
        )
    except OfferSearchAuthError as exc:
        raise HTTPException(
            status_code=401,
            detail="SEARCH_AUTH_ERROR",
        ) from exc
    except OfferSearchRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=f"SEARCH_RATE_LIMIT:{exc.retry_after}" if exc.retry_after else "SEARCH_RATE_LIMIT",
        ) from exc
    except OfferSearchTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="SEARCH_TIMEOUT",
        ) from exc
    except OfferSearchConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="SEARCH_CONNECTION_ERROR",
        ) from exc
    except SQLAlchemyError:
        logger.exception("offer_search_run_db_error", user_id=current_user.id)
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable",
        ) from None

    return OfferRunResponse(
        found=result.found,
        new_offers=result.new_offers,
        skipped_stale=result.skipped_stale,
    )


# ---------------------------------------------------------------------------
# PUT /v1/me/offer-preferences
# ---------------------------------------------------------------------------


@router.put("/me/offer-preferences", response_model=OfferPreferencesResponse)
async def update_offer_preferences(
    prefs: OfferPreferencesRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> OfferPreferencesResponse:
    """
    Persist the current user's job-offer notification preferences.

    All fields are optional; omitted fields retain their current value
    (or the application defaults if never set).
    """
    async with get_session_context() as session:
        user = await session.get(User, current_user.id)

    if user is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    # Start from existing prefs, then overlay validated input.
    raw = dict(user.offer_preferences or {})

    if prefs.frequency_hours is not None:
        raw["frequency_hours"] = prefs.frequency_hours
    if prefs.top_n is not None:
        raw["top_n"] = prefs.top_n
    if prefs.email_frequency is not None:
        raw["email_frequency"] = prefs.email_frequency
    if prefs.filters is not None:
        raw["filters"] = prefs.filters

    async with get_session_context() as session:
        user = await session.get(User, current_user.id)
        if user is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        user.offer_preferences = raw
        await session.commit()
        await session.refresh(user)

    # Resolve response with defaults for fields not in raw.
    resolved = OfferPrefs(
        frequency_hours=raw.get("frequency_hours", 24),
        top_n=raw.get("top_n", 5),
        email_frequency=raw.get("email_frequency", "none"),
        filters=raw.get("filters"),
    )

    return OfferPreferencesResponse(
        frequency_hours=resolved.frequency_hours,
        top_n=resolved.top_n,
        email_frequency=resolved.email_frequency,
        filters=resolved.filters,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_search_client(settings: Settings):
    """Build a Tavily search client from settings, or raise a helpful error."""
    api_key = settings.tavily_api_key
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="FEATURE_DISABLED",
        )
    from app.services.offer_search_client import TavilyOfferSearchClient

    return TavilyOfferSearchClient(api_key=api_key)


def _session_factory():
    """Return the async session maker for the run_offer_search call.

    Uses the public factory getter so that tests can override DATABASE_URL
    before the engine is cached.
    """
    from app.db.session import get_session_factory

    return get_session_factory()
