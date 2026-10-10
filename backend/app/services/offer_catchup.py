"""Catch-up dispatch of offer-search jobs on app wake — issue #55.

Render free stops the process after ~15 min of inactivity; every wake
boots a NEW process whose lifespan runs this catch-up. Users with offer
preferences whose last run is older than their configured frequency get
their search job dispatched now — the "lazy catch-up" that survives the
sleep, instead of an in-process scheduler that dies with it.

Fire-and-forget by design: the lifespan dispatches via create_task and
never awaits it, so a slow Tavily/DB call never delays startup.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from app.core.config import Settings
from app.services.offer_prefs import get_offer_prefs, is_stale
from app.services.offer_search_client import TavilyOfferSearchClient
from app.services.offer_search_worker import OfferRunResult, run_offer_search

logger = structlog.get_logger("app.offer_catchup")

# Per-job timeout: a hung Tavily/DB call must not pin the catch-up forever.
_CATCHUP_TIMEOUT_S = 120.0


def build_catchup_search_client(settings: Settings) -> TavilyOfferSearchClient | None:
    """Search client for the catch-up, or None when Tavily is unconfigured.

    The absence is a no-op (logged), not an error: the catch-up is a
    background convenience and must never break the startup.
    """
    if not settings.tavily_api_key:
        return None
    return TavilyOfferSearchClient(api_key=settings.tavily_api_key)


async def run_offer_catchup(
    settings: Settings,
    *,
    session_factory=None,
    now: datetime | None = None,
) -> list[int]:
    """Dispatch stale users' offer-search jobs; return the dispatched ids.

    Read-only staleness scan first (one session), dispatch outside it.
    A failed or timed-out job is logged and skipped — the other users'
    jobs still run.
    """
    reference = now or datetime.now(UTC)

    search_client = build_catchup_search_client(settings)
    if search_client is None:
        logger.info("offer_catchup_skipped", reason="no_tavily_api_key")
        return []

    if session_factory is None:
        from app.db.session import get_session_factory

        session_factory = get_session_factory()

    from sqlmodel import select

    from app.db.models import User

    stale: list[int] = []
    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.offer_preferences.is_not(None))
        )
        for user in result.scalars().all():
            prefs = get_offer_prefs(user)
            if is_stale(user, prefs, reference):
                stale.append(user.id)

    if not stale:
        logger.info("offer_catchup_nothing_stale", checked=len(stale))
        return []

    from app.llm.factory import get_llm_provider

    embedding_provider = get_llm_provider()
    dispatched: list[int] = []
    for user_id in stale:
        try:
            outcome: OfferRunResult = await asyncio.wait_for(
                run_offer_search(
                    user_id=user_id,
                    session_factory=session_factory,
                    settings=settings,
                    search_client=search_client,
                    embedding_provider=embedding_provider,
                ),
                timeout=_CATCHUP_TIMEOUT_S,
            )
            dispatched.append(user_id)
            logger.info(
                "offer_catchup_dispatched",
                user_id=user_id,
                found=outcome.found,
                new_offers=outcome.new_offers,
            )
        except TimeoutError:
            logger.warning("offer_catchup_job_timeout", user_id=user_id)
        except Exception as exc:  # noqa: BLE001 — fire-and-forget: one failed job never blocks the others
            logger.warning(
                "offer_catchup_job_failed",
                user_id=user_id,
                error=type(exc).__name__,
            )
    return dispatched
