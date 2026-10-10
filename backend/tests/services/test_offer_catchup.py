"""Tests for the offer catch-up dispatch (issue #55).

The catch-up is the lazy cron that survives Render free's sleep: every
wake boots a fresh process whose lifespan dispatches stale users' jobs.
These tests cover the dispatch logic with mocked DB/provider/Tavily —
CI without network. The lifespan wiring is guarded by the Tavily
absence check, so test app startups stay no-op (no DB noise).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.services.offer_catchup import run_offer_catchup

NOW = datetime(2025, 1, 10, 12, 0, 0, tzinfo=UTC)


def _settings(**kwargs: object) -> Settings:
    base = {
        "tavily_api_key": "tvly-key",
        "jwt_secret": "x" * 64,
        "database_url": "postgresql+asyncpg://localhost:5433/unused",
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _make_user(user_id: int, prefs: dict | None):
    user = MagicMock()
    user.id = user_id
    user.offer_preferences = prefs
    return user


def _session_factory_with(users: list) -> MagicMock:
    session = MagicMock()

    async def _execute(_stmt):
        result = MagicMock()
        result.scalars.return_value.all.return_value = users
        return result

    session.execute = AsyncMock(side_effect=_execute)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock()
    factory.return_value = session
    return factory


@pytest.mark.asyncio
async def test_no_tavily_key_is_a_noop() -> None:
    """Without TAVILY_API_KEY the catch-up is a logged no-op — the guard
    that keeps test app startups (and unconfigured deploys) silent."""
    calls: list[int] = []

    async def _fail(*args, **kwargs):
        calls.append(1)
        raise AssertionError("run_offer_search must not be called")

    with patch("app.services.offer_catchup.run_offer_search", _fail):
        dispatched = await run_offer_catchup(_settings(tavily_api_key=None))

    assert dispatched == []
    assert calls == []


@pytest.mark.asyncio
async def test_dispatches_only_stale_users() -> None:
    """Users with stale last_offer_run_at get dispatched; fresh ones don't."""
    stale_user = _make_user(1, {"frequency_hours": 24, "last_offer_run_at": (NOW - timedelta(hours=25)).isoformat()})
    fresh_user = _make_user(2, {"frequency_hours": 24, "last_offer_run_at": (NOW - timedelta(hours=1)).isoformat()})
    factory = _session_factory_with([stale_user, fresh_user])

    with patch("app.services.offer_catchup.run_offer_search", AsyncMock(return_value=MagicMock(found=2, new_offers=1))):
        dispatched = await run_offer_catchup(_settings(), session_factory=factory, now=NOW)

    assert dispatched == [1]


@pytest.mark.asyncio
async def test_nothing_stale_dispatches_nothing() -> None:
    """All fresh → no dispatch, no job calls."""
    fresh = _make_user(3, {"frequency_hours": 24, "last_offer_run_at": NOW.isoformat()})
    factory = _session_factory_with([fresh])

    with patch("app.services.offer_catchup.run_offer_search", AsyncMock(return_value=MagicMock(found=0, new_offers=0))):
        dispatched = await run_offer_catchup(_settings(), session_factory=factory, now=NOW)

    assert dispatched == []


@pytest.mark.asyncio
async def test_one_failed_job_does_not_block_the_rest() -> None:
    """A failing job is logged and skipped; the next user still runs."""
    failing = _make_user(1, {"frequency_hours": 24, "last_offer_run_at": (NOW - timedelta(hours=48)).isoformat()})
    healthy = _make_user(2, {"frequency_hours": 24, "last_offer_run_at": (NOW - timedelta(hours=48)).isoformat()})
    factory = _session_factory_with([failing, healthy])

    async def _fake(user_id, **kwargs):
        if user_id == 1:
            raise RuntimeError("tavily exploded")
        return MagicMock(found=1, new_offers=1)

    with patch("app.services.offer_catchup.run_offer_search", _fake):
        dispatched = await run_offer_catchup(_settings(), session_factory=factory, now=NOW)

    assert dispatched == [2]


@pytest.mark.asyncio
async def test_timeout_job_is_skipped() -> None:
    """A job exceeding the per-job timeout is logged and skipped."""
    slow = _make_user(7, {"frequency_hours": 24, "last_offer_run_at": (NOW - timedelta(hours=48)).isoformat()})
    factory = _session_factory_with([slow])

    async def _slow(user_id, **kwargs):
        import asyncio

        await asyncio.sleep(999)

    with patch("app.services.offer_catchup.run_offer_search", _slow):
        dispatched = await run_offer_catchup(_settings(), session_factory=factory, now=NOW)

    assert dispatched == []
