"""
Unit tests for the ``AdaptationRunner``.

The runner is the asynchronous orchestrator that flips a
``CVAdaptation`` row from ``pending`` → ``completed``/``failed``. We
exercise:

- Happy path: LLM produces a validator-clean adapted CV → ``completed``,
  ``adapted_cv_json`` populated.
- Validator fail then retry success: first LLM call produces an
  adapted CV with a forbidden skill; second call (strict suffix)
  produces a clean one → ``completed``.
- All retries exhausted → ``failed``, ``error_code=INVALID_HONESTY``.
- LLM raises → ``failed``, ``error_code=LLM_ERROR``.
- JSON parse fail (LLM returns an invalid payload that fails
  pydantic validation) → ``failed``, ``error_code=LLM_ERROR``.

The runner accepts any session factory and LLM provider, so tests
inject a session factory pointed at the test DB and a ``MagicMock`` /
hand-rolled fake LLM provider. No external services are involved.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.db.models import CVAdaptation, Subscription, User, UserCV
from app.llm.schemas import AdaptedCV, AdaptedExperienceItem
from app.services.adaptation_runner import AdaptationRunner
from app.services.rls_context import set_rls_user
from app.services.tier_limits import check_limit, get_plan_limits


class _FakeLLM:
    """Minimal stand-in for the LLM provider.

    The runner uses ``generate_adaptation`` only; everything else falls
    through to ``AttributeError`` which the tests don't trigger. The
    factory-style ``set_side_effect`` lets a single test inject a list
    of canned responses / exceptions to walk the runner through the
    happy / retry / failure paths.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses: list[AdaptedCV | Exception] = []

    def set_responses(self, responses: list[AdaptedCV | Exception]) -> None:
        self._responses = list(responses)

    async def generate_adaptation(
        self,
        cv_structured: dict[str, Any],
        jd_text: str,
        *,
        max_tokens: int = 4000,
    ) -> AdaptedCV:
        self.calls.append(
            {"cv_structured": cv_structured, "jd_text": jd_text, "max_tokens": max_tokens}
        )
        if not self._responses:
            raise AssertionError("no canned response queued for LLM call")
        next_resp = self._responses.pop(0)
        if isinstance(next_resp, Exception):
            raise next_resp
        return next_resp


async def _seed_owner_and_cv(clean_db) -> tuple[User, UserCV]:
    """Create one user + one CV; return the (user, cv) pair."""
    async with clean_db.session_factory() as session:
        user = User(
            email="owner@example.com",
            password_hash="x",
            role="job_seeker",
            full_name="Owner",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        cv = UserCV(
            owner_user_id=user.id,
            original_filename="cv.pdf",
            structured={
                "full_name": "Owner",
                "experience": [
                    {
                        "title": "Senior Backend Engineer",
                        "company": "Acme",
                        "dates": "2020-2024",
                        "description": "Built Python services on AWS Lambda. Led team of 5.",
                    }
                ],
                "skills": ["Python", "AWS", "PostgreSQL"],
                "education": [],
                "languages": ["English"],
            },
            content_version=1,
        )
        session.add(cv)
        await session.commit()
        await session.refresh(cv)
        return user, cv


async def _insert_pending_row(
    clean_db,
    *,
    owner_user_id: int,
    cv_id: int,
    jd_text: str = "Looking for a Senior Backend Engineer with Python and AWS experience.",
    status: str = "pending",
    created_at: datetime | None = None,
) -> CVAdaptation:
    """Insert a CVAdaptation row with the JD stored as bytes.

    ``created_at`` is overridable so a test can backdate a row to
    simulate the passing of the 24 h cache TTL.
    """
    from app.services.adaptation_cache import compute_jd_text_hash

    jd_hash = compute_jd_text_hash(jd_text)
    async with clean_db.session_factory() as session:
        await set_rls_user(session, owner_user_id, "job_seeker")
        row = CVAdaptation(
            parent_cv_id=cv_id,
            owner_user_id=owner_user_id,
            jd_text_hash=jd_hash,
            jd_text=jd_text.encode("utf-8"),
            adapted_cv_json={},
            status=status,
        )
        if created_at is not None:
            row.created_at = created_at
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def _seed_subscription(clean_db, user_id: int, plan: str) -> Subscription:
    """Give the user an active paid plan so adaptations are not capped at 0."""
    async with clean_db.session_factory() as session:
        sub = Subscription(
            user_id=user_id,
            plan=plan,
            status="active",
            stripe_subscription_id=f"sub_{user_id}",
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return sub


def _valid_adapted(source: dict[str, Any]) -> AdaptedCV:
    """Build an AdaptedCV that passes the validator against the source.

    The validator's description check tokenizes the adapted description
    and verifies each token (length >= 3) appears in the source
    description blob. So we can ONLY append words that are already
    present in the source — echoing the source verbatim is the safest
    validator-clean rewrite.
    """
    return AdaptedCV(
        full_name=source["full_name"],
        experience=[
            AdaptedExperienceItem(
                title=exp["title"],
                company=exp["company"],
                dates=exp["dates"],
                description=exp["description"],
            )
            for exp in source.get("experience", [])
        ],
        skills=list(source.get("skills", [])),
        education=list(source.get("education", [])),
        languages=list(source.get("languages", [])),
    )


def _invalid_adapted(source: dict[str, Any]) -> AdaptedCV:
    """AdaptedCV that introduces a forbidden skill (``Kubernetes``).

    The validator rejects skills that don't trace back to the source
    after normalization, so this triggers an ``INVALID_HONESTY``
    failure on the first attempt.
    """
    return AdaptedCV(
        full_name=source["full_name"],
        experience=[
            AdaptedExperienceItem(
                title=exp["title"],
                company=exp["company"],
                dates=exp["dates"],
                description=exp["description"],
            )
            for exp in source.get("experience", [])
        ],
        skills=list(source.get("skills", [])) + ["Kubernetes"],
        education=list(source.get("education", [])),
        languages=list(source.get("languages", [])),
    )


# === Happy path ===


class TestAdaptationRunnerHappyPath:
    """A clean LLM call populates the row and marks it completed."""

    @pytest.mark.asyncio
    async def test_completed_on_valid_output(
        self, clean_db, monkeypatch
    ) -> None:
        """First-call success: status=completed, json persisted, counter incremented."""
        user, cv = await _seed_owner_and_cv(clean_db)
        row = await _insert_pending_row(
            clean_db, owner_user_id=user.id, cv_id=cv.id
        )

        llm = _FakeLLM()
        source = cv.structured
        llm.set_responses([_valid_adapted(source)])

        # Block the real increment_usage side-effect so the test doesn't
        # depend on subscription fixtures; the call is best-effort anyway.
        async def _noop_increment(session, user_id, resource):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            "app.services.adaptation_runner.increment_usage", _noop_increment
        )

        runner = AdaptationRunner(
            session_factory=clean_db.session_factory,
            llm_provider=llm,
        )
        await runner.run(row.id)

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            updated = await session.get(CVAdaptation, row.id)
            assert updated is not None
            assert updated.status == "completed"
            assert updated.error_code is None
            assert updated.error_message is None
            assert updated.completed_at is not None
            assert updated.adapted_cv_json["full_name"] == "Owner"
            assert "Python" in updated.adapted_cv_json["skills"]
            # LLM was called exactly once (no retries).
            assert len(llm.calls) == 1

    @pytest.mark.asyncio
    async def test_jd_text_passed_to_llm(self, clean_db, monkeypatch) -> None:
        """The LLM receives the JD bytes decoded back from the row."""
        user, cv = await _seed_owner_and_cv(clean_db)
        jd_text = "Need a Python expert with cloud experience."
        row = await _insert_pending_row(
            clean_db,
            owner_user_id=user.id,
            cv_id=cv.id,
            jd_text=jd_text,
        )

        llm = _FakeLLM()
        llm.set_responses([_valid_adapted(cv.structured)])

        async def _noop_increment(session, user_id, resource):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            "app.services.adaptation_runner.increment_usage", _noop_increment
        )

        runner = AdaptationRunner(
            session_factory=clean_db.session_factory,
            llm_provider=llm,
        )
        await runner.run(row.id)

        # First call sees the JD verbatim; no retry, no strict suffix.
        assert len(llm.calls) == 1
        assert llm.calls[0]["jd_text"] == jd_text


# === Validator retry path ===


class TestAdaptationRunnerRetries:
    """Validator failures trigger a strict-prompt retry."""

    @pytest.mark.asyncio
    async def test_retry_after_validator_failure_succeeds(
        self, clean_db, monkeypatch
    ) -> None:
        """First call invalid → retry with strict suffix → success → completed."""
        user, cv = await _seed_owner_and_cv(clean_db)
        row = await _insert_pending_row(
            clean_db, owner_user_id=user.id, cv_id=cv.id
        )

        llm = _FakeLLM()
        source = cv.structured
        llm.set_responses(
            [_invalid_adapted(source), _valid_adapted(source)]
        )

        async def _noop_increment(session, user_id, resource):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            "app.services.adaptation_runner.increment_usage", _noop_increment
        )

        runner = AdaptationRunner(
            session_factory=clean_db.session_factory,
            llm_provider=llm,
        )
        await runner.run(row.id)

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            updated = await session.get(CVAdaptation, row.id)
            assert updated is not None
            assert updated.status == "completed"
            assert updated.adapted_cv_json["full_name"] == "Owner"

        # Two LLM calls: first invalid, second with strict suffix.
        assert len(llm.calls) == 2
        # The strict suffix only appears on retry attempts.
        assert "STRICT MODE" in llm.calls[1]["jd_text"]
        assert "STRICT MODE" not in llm.calls[0]["jd_text"]

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_marks_invalid_honesty(
        self, clean_db, monkeypatch
    ) -> None:
        """Validator keeps failing → 3 calls total → status=failed, INVALID_HONESTY."""
        user, cv = await _seed_owner_and_cv(clean_db)
        row = await _insert_pending_row(
            clean_db, owner_user_id=user.id, cv_id=cv.id
        )

        llm = _FakeLLM()
        source = cv.structured
        # Every response is invalid (Kubernetes is not in the source).
        llm.set_responses(
            [_invalid_adapted(source) for _ in range(3)]
        )

        async def _noop_increment(session, user_id, resource):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            "app.services.adaptation_runner.increment_usage", _noop_increment
        )

        runner = AdaptationRunner(
            session_factory=clean_db.session_factory,
            llm_provider=llm,
        )
        await runner.run(row.id)

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            updated = await session.get(CVAdaptation, row.id)
            assert updated is not None
            assert updated.status == "failed"
            assert updated.error_code == "INVALID_HONESTY"
            assert updated.error_message is not None
            assert "Kubernetes" in updated.error_message
            assert updated.completed_at is not None

        # 1 initial + 2 retries = 3 total LLM calls.
        assert len(llm.calls) == 3

    @pytest.mark.asyncio
    async def test_llm_raises_marks_llm_error(
        self, clean_db, monkeypatch
    ) -> None:
        """LLM raising on every attempt → status=failed, LLM_ERROR."""
        user, cv = await _seed_owner_and_cv(clean_db)
        row = await _insert_pending_row(
            clean_db, owner_user_id=user.id, cv_id=cv.id
        )

        llm = _FakeLLM()
        llm.set_responses(
            [RuntimeError("groq rate limit") for _ in range(3)]
        )

        async def _noop_increment(session, user_id, resource):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            "app.services.adaptation_runner.increment_usage", _noop_increment
        )

        runner = AdaptationRunner(
            session_factory=clean_db.session_factory,
            llm_provider=llm,
        )
        await runner.run(row.id)

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            updated = await session.get(CVAdaptation, row.id)
            assert updated is not None
            assert updated.status == "failed"
            assert updated.error_code == "LLM_ERROR"
            assert "groq rate limit" in (updated.error_message or "")

        assert len(llm.calls) == 3

    @pytest.mark.asyncio
    async def test_validation_error_treated_as_llm_error(
        self, clean_db, monkeypatch
    ) -> None:
        """A pydantic ValidationError raised by the LLM client → LLM_ERROR.

        Some LLM clients raise ``pydantic.ValidationError`` when the
        raw response fails schema parsing. The runner wraps that into
        the same ``LLM_ERROR`` bucket so the client doesn't need to
        distinguish JSON parse failures from provider failures.
        """
        user, cv = await _seed_owner_and_cv(clean_db)
        row = await _insert_pending_row(
            clean_db, owner_user_id=user.id, cv_id=cv.id
        )

        llm = _FakeLLM()
        try:
            llm.set_responses(
                [
                    ValidationError.from_exception_data(
                        "AdaptedCV",
                        [
                            {
                                "type": "missing",
                                "loc": ("full_name",),
                                "input": {},
                            }
                        ],
                    )
                    for _ in range(3)
                ]
            )
        except Exception:
            # Some pydantic builds reject empty input; raise a
            # RuntimeError instead to keep the test robust.
            llm.set_responses([RuntimeError("JSON parse fail") for _ in range(3)])

        async def _noop_increment(session, user_id, resource):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            "app.services.adaptation_runner.increment_usage", _noop_increment
        )

        runner = AdaptationRunner(
            session_factory=clean_db.session_factory,
            llm_provider=llm,
        )
        await runner.run(row.id)

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            updated = await session.get(CVAdaptation, row.id)
            assert updated is not None
            assert updated.status == "failed"
            assert updated.error_code == "LLM_ERROR"


# === Idempotency / safety


class TestAdaptationRunnerIdempotency:
    """Already-terminal rows are skipped."""

    @pytest.mark.asyncio
    async def test_skip_completed_row(self, clean_db, monkeypatch) -> None:
        """Running the runner against a completed row is a no-op."""
        user, cv = await _seed_owner_and_cv(clean_db)
        # Insert a row that's already completed; the runner must skip.
        from app.services.adaptation_cache import compute_jd_text_hash

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            row = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=compute_jd_text_hash("ignored"),
                jd_text=b"ignored",
                adapted_cv_json={"full_name": "AlreadyDone"},
                status="completed",
                completed_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            row_id = row.id

        llm = _FakeLLM()  # No responses queued; if called, test fails.
        async def _noop_increment(session, user_id, resource):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            "app.services.adaptation_runner.increment_usage", _noop_increment
        )

        runner = AdaptationRunner(
            session_factory=clean_db.session_factory,
            llm_provider=llm,
        )
        await runner.run(row_id)

        # Row untouched — no LLM call, status still completed.
        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            updated = await session.get(CVAdaptation, row_id)
            assert updated is not None
            assert updated.status == "completed"
            assert updated.adapted_cv_json == {"full_name": "AlreadyDone"}
        assert llm.calls == []

    @pytest.mark.asyncio
    async def test_skip_missing_row(self, clean_db, monkeypatch) -> None:
        """Running the runner against a non-existent id is a safe no-op."""
        llm = _FakeLLM()

        async def _noop_increment(session, user_id, resource):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            "app.services.adaptation_runner.increment_usage", _noop_increment
        )

        runner = AdaptationRunner(
            session_factory=clean_db.session_factory,
            llm_provider=llm,
        )
        # Should NOT raise — silently no-op.
        await runner.run(999_999)
        assert llm.calls == []


# === Usage counter (quota) binding ===
#
# Every test above monkeypatches ``increment_usage`` to a no-op, so the
# suite as a whole is structurally blind to the counter write. That is
# deliberate isolation for the row-state tests and exactly why the
# quota bug shipped: nothing exercised the real call. The two tests
# below are the ones that deliberately do NOT stub it.


@asynccontextmanager
async def _production_sessions():
    """Yield a session factory that reproduces PRODUCTION RLS conditions.

    Two test-harness conveniences hide the production bug, so both have
    to be neutralised before a missing ``set_rls_*`` call can be seen:

    1. ``tests/conftest.py`` registers a *global* ``after_begin`` listener
       that binds the service GUC ('0') on every ORM transaction, so an
       unbound session still silently runs as service.
    2. The docker/CI test user is a superuser, and superusers bypass RLS
       even with FORCE — so RLS is not enforced for it at all.

    Production has neither: ``app/db/session.py`` uses ``NullPool`` with
    no ``server_settings`` and registers no such listener, so
    ``app.current_user_id`` is simply unset. This helper removes the
    listener for the duration and runs every connection as the
    NOBYPASSRLS owner role — the same trick ``tests/test_rls.py`` uses.
    """
    import sys

    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session as _SyncSession

    from tests.conftest import RLS_TEST_ROLE

    # pytest may hold conftest under either module name; pick the one
    # whose function object is the registered listener.
    listener = None
    for mod_name in ("tests.conftest", "conftest"):
        mod = sys.modules.get(mod_name)
        candidate = getattr(mod, "_bind_service_rls", None) if mod else None
        if candidate is not None and sa_event.contains(
            _SyncSession, "after_begin", candidate
        ):
            listener = candidate
            break
    if listener is None:  # pragma: no cover - harness plumbing
        raise AssertionError("registered conftest RLS listener not found")

    sa_event.remove(_SyncSession, "after_begin", listener)
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)

    @sa_event.listens_for(engine.sync_engine, "connect")
    def _use_rls_role(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        try:
            cur.execute(f"SET ROLE {RLS_TEST_ROLE}")
        finally:
            cur.close()

    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        yield factory
    finally:
        await engine.dispose()
        sa_event.listen(_SyncSession, "after_begin", listener)


class TestUsageCounterRLSBinding:
    """The runner's counter write must survive RLS (real ``increment_usage``).

    ``usage_counters`` has FORCE ROW LEVEL SECURITY (migration 011) with
    only a service policy (``app.current_user_id = '0'``) and owner
    policies keyed on ``public.app_current_user_id()``. A session that
    never binds the GUC runs with it unset: the SELECT sees 0 rows, the
    INSERT fails ``usage_counters_owner_insert`` (NULL is not true), and
    the exception is swallowed — leaving ``adaptations_used`` at 0.

    These run under ``_production_sessions`` because the default test
    session factory runs as service and would mask the defect.
    """

    @pytest.mark.asyncio
    async def test_n_adaptations_increment_counter_by_exactly_n(
        self, clean_db
    ) -> None:
        """N successful adaptations → ``adaptations_used == N``.

        Negative control: against the unfixed runner this asserts 3 and
        measures 0 (every INSERT is rejected by RLS and swallowed).
        """
        user, cv = await _seed_owner_and_cv(clean_db)
        await _seed_subscription(clean_db, user.id, "job_seeker_monthly")

        n = 3
        # Distinct JDs → distinct jd_text_hash, so this test isolates
        # the counter write from the completed-row unique index.
        for i in range(n):
            row = await _insert_pending_row(
                clean_db,
                owner_user_id=user.id,
                cv_id=cv.id,
                jd_text=f"Backend engineer role number {i} with Python and AWS.",
            )

            llm = _FakeLLM()
            llm.set_responses([_valid_adapted(cv.structured)])
            async with _production_sessions() as factory:
                runner = AdaptationRunner(
                    session_factory=factory, llm_provider=llm
                )
                # NO monkeypatch of increment_usage - this is the point.
                await runner.run(row.id)

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            limits = await get_plan_limits(session, user.id, "job_seeker")
            assert limits.adaptations_used == 3
            assert limits.adaptations_remaining == 5 - n

    @pytest.mark.asyncio
    async def test_paid_cap_of_five_stops_at_five(self, clean_db) -> None:
        """``job_seeker_monthly`` allows 5; the 6th is refused.

        The revenue assertion, end to end through the runner: burn the
        cap with real adaptations, then confirm ``check_limit`` (what
        the POST endpoint calls) raises ``PLAN_LIMIT_REACHED``.

        Negative control: against the unfixed runner the counter stays
        at 0, so the 6th is allowed and this test fails.
        """
        user, cv = await _seed_owner_and_cv(clean_db)
        await _seed_subscription(clean_db, user.id, "job_seeker_monthly")

        for i in range(5):
            row = await _insert_pending_row(
                clean_db,
                owner_user_id=user.id,
                cv_id=cv.id,
                jd_text=f"Role {i}: Senior Backend Engineer, Python and AWS.",
            )
            llm = _FakeLLM()
            llm.set_responses([_valid_adapted(cv.structured)])
            async with _production_sessions() as factory:
                runner = AdaptationRunner(
                    session_factory=factory, llm_provider=llm
                )
                await runner.run(row.id)

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            limits = await get_plan_limits(session, user.id, "job_seeker")
            assert limits.adaptations_used == 5
            assert limits.adaptations_remaining == 0
            # The 6th request is what the POST endpoint runs first.
            with pytest.raises(ValueError, match="PLAN_LIMIT_REACHED"):
                await check_limit(session, user.id, "adaptation", "job_seeker")


# === Repeat adaptations (cache TTL vs the completed-row index)


class TestRepeatAdaptation:
    """Re-adapting the same JD after the cache expires must still finish.

    The cache serves a completed row for 24 h but the sweeper only
    deletes completed rows after 90 days. Under the old
    ``UNIQUE (... ) WHERE status='completed'`` index the repeat request
    at T+25h inserted a fresh pending row, the runner paid for the LLM
    call, and the final UPDATE to ``completed`` raised IntegrityError
    against the row from T — leaving the new row ``pending`` forever.

    Migration 021 scopes the uniqueness to ``pending`` rows, so a
    completed row stops blocking its own successor.
    """

    @pytest.mark.asyncio
    async def test_repeat_after_cache_window_completes(self, clean_db) -> None:
        """A miss on the 24 h cache re-runs and lands in ``completed``."""
        from app.services.adaptation_cache import get_cached

        user, cv = await _seed_owner_and_cv(clean_db)
        await _seed_subscription(clean_db, user.id, "job_seeker_monthly")

        jd_text = "Senior Backend Engineer with Python, AWS and PostgreSQL."
        stale = await _insert_pending_row(
            clean_db,
            owner_user_id=user.id,
            cv_id=cv.id,
            jd_text=jd_text,
            status="completed",
            created_at=datetime.now(UTC) - timedelta(hours=25),
        )
        assert stale.status == "completed"

        # Precondition: the row is past the TTL, so this is a real miss.
        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            assert (
                await get_cached(
                    session,
                    cv_id=cv.id,
                    jd_text_hash=stale.jd_text_hash,
                )
                is None
            )

        repeat = await _insert_pending_row(
            clean_db, owner_user_id=user.id, cv_id=cv.id, jd_text=jd_text
        )

        llm = _FakeLLM()
        llm.set_responses([_valid_adapted(cv.structured)])
        runner = AdaptationRunner(
            session_factory=clean_db.session_factory, llm_provider=llm
        )
        # Against the old index this raises IntegrityError from
        # _persist_success and the row is stranded in ``pending``.
        await runner.run(repeat.id)

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            updated = await session.get(CVAdaptation, repeat.id)
            assert updated is not None
            assert updated.status == "completed"
            assert updated.adapted_cv_json["full_name"] == "Owner"

            # The defining assertion: nothing is left hanging.
            result = await session.execute(
                select(CVAdaptation).where(CVAdaptation.status == "pending")
            )
            assert result.scalars().all() == []
