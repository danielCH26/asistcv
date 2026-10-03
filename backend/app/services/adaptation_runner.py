"""
Adaptation runner service (Slice A, sprint-adapt-cv-outreach, PR2b).

Owns the asynchronous flow that turns a ``CVAdaptation`` row from
``pending`` → ``completed`` (or ``failed``). Spawned by
``POST /v1/adaptations`` after the cache miss path; resilient to Render
restarts because the persistent ``cv_adaptations`` row is the source of
truth — a cold restart leaves the row pending and the runner can be
re-triggered (PR3 sweeper or an explicit retry) to resume against the
same data.

Pipeline (PR2 design D4)
------------------------
1. Load the ``CVAdaptation`` row + the source ``UserCV`` (RLS-bound
   session, service context for cross-row writes).
2. Decode the JD text from ``jd_text`` (raw UTF-8 bytes — the column is
   plaintext, consistently with the rest of the schema, and was renamed
   from ``jd_text_encrypted`` in migration 019 to stop the name claiming
   an encryption that does not exist).
3. Call ``llm_provider.generate_adaptation(cv_structured, jd_text,
   max_tokens=4000)``.
4. On LLM exception / parse failure → ``status=failed``,
   ``error_code=LLM_ERROR``. The row stays visible to the client.
5. Call ``adaptation_validator.validate_adaptation(source, adapted)``.
6. If validation fails AND the retry budget remains: increment the
   in-process retry counter, sleep 1 s, re-call the LLM with a
   stricter prompt suffix. The stricter hint is injected as a
   well-known constant so the contract is observable in logs.
7. If validation still fails after the retries → ``status=failed``,
   ``error_code=INVALID_HONESTY``, ``error_message`` carries the first
   three violations so the user can see why we rejected the output.
8. If the adapted CV passes → ``status=completed``, ``completed_at =
   now()``, ``adapted_cv_json`` populated with the validated payload.

Counter semantics
-----------------
The retry counter is in-memory (one process, one job). On Render
restart the counter resets to 0 and the runner starts fresh; that's
acceptable because the row is still in ``pending`` state so the worst
case is "one extra LLM call". A persistent counter on the row would
require a schema change that's out of scope for PR2b.

Increment usage
---------------
Successful adaptations consume one credit from the user's monthly
quota (``UsageCounter.adaptations_used``). The increment runs in a
separate transaction so a DB hiccup in the counter doesn't roll back
the adaptation; if increment fails the runner logs and continues.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.db.models import CVAdaptation, UserCV
from app.llm.base import LLMProvider
from app.services.adaptation_validator import validate_adaptation
from app.services.rls_context import set_rls_user
from app.services.tier_limits import increment_usage

logger = get_logger("app.services.adaptation_runner")

# Maximum number of validator retries (so total LLM calls ≤ 3 — one
# initial + two retries). Matches the design doc's "≤ 2 retries" cap.
MAX_RETRIES = 2

# Backoff between retries. Small (1 s) because the LLM call itself
# dominates latency; this is just enough to let any in-flight provider
# rate-limit bucket refill on the free tier.
RETRY_SLEEP_SECONDS = 1.0

# Strict-prompt suffix used to give the LLM a deterministic hint when
# the validator rejects its first attempt. The provider passes the
# full string to the model — keeping it as a constant avoids drift.
STRICT_PROMPT_SUFFIX = (
    " [STRICT MODE] Your previous output failed the honesty validator. "
    "Re-emit ONLY tokens present in the source CV (skills, companies, "
    "job titles, dates) and reuse words from the source descriptions. "
    "Do NOT invent any new skill, company, or fact."
)


class AdaptationRunner:
    """Async orchestrator for a single ``CVAdaptation`` row.

    The runner owns the lifetime of one pending row from pending to a
    terminal state (completed | failed). It does not hold the row
    between calls — every state transition is committed to the DB so
    a process crash between retries leaves the row recoverable.

    Args:
        session_factory: ``async_sessionmaker`` that produces
            ``AsyncSession`` instances bound to the test/production DB.
            Injected so tests can swap the factory.
        llm_provider: Anything that satisfies the ``LLMProvider``
            protocol (the real Groq provider in prod, a mock in tests).
        max_retries: Optional override for ``MAX_RETRIES`` (used by
            tests that want to exercise the failure path with fewer
            attempts).
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm_provider: LLMProvider,
        *,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self._session_factory = session_factory
        self._llm_provider = llm_provider
        self._max_retries = max_retries

    async def run(self, adaptation_id: int) -> None:
        """Run the adaptation pipeline for one ``adaptation_id``.

        Idempotent at the row level: if the row is already in a
        terminal state (``completed`` or ``failed``) the call is a
        no-op. This protects against the sweeper re-firing the same
        job after a partial crash.

        Args:
            adaptation_id: ``cv_adaptations.id`` to process.

        Side Effects:
            Writes to ``cv_adaptations`` (status, error_code,
            error_message, adapted_cv_json, completed_at). On
            success, increments ``usage_counters.adaptations_used``
            for the owner in a separate transaction.
        """
        try:
            row, source_cv, jd_text = await self._load(adaptation_id)
        except Exception as exc:
            logger.exception(
                "adaptation_load_failed",
                adaptation_id=adaptation_id,
                error=str(exc)[:200],
            )
            return

        if row is None:
            logger.warning(
                "adaptation_missing_or_terminal",
                adaptation_id=adaptation_id,
            )
            return

        owner_user_id = row.owner_user_id
        cv_structured: dict[str, Any] = (
            source_cv.structured if source_cv is not None else {}
        )

        logger.info(
            "adaptation_started",
            adaptation_id=adaptation_id,
            owner_user_id=owner_user_id,
            cv_id=source_cv.id if source_cv is not None else None,
            jd_text_len=len(jd_text or ""),
        )

        adapted_dict, error_code, error_message = await self._generate_and_validate(
            source=cv_structured,
            jd_text=jd_text,
            owner_user_id=owner_user_id,
        )

        if adapted_dict is None:
            await self._persist_failure(
                adaptation_id=adaptation_id,
                owner_user_id=owner_user_id,
                error_code=error_code or "LLM_ERROR",
                error_message=error_message or "adaptation failed",
            )
            return

        await self._persist_success(
            adaptation_id=adaptation_id,
            owner_user_id=owner_user_id,
            adapted=adapted_dict,
        )

        # Charge the quota in a separate transaction so a credit-tracking
        # hiccup can never roll back a delivered adaptation. The failure
        # is logged at ERROR (billing bug, not a hiccup) but does not
        # fail the job — the LLM spend is already sunk and ``completed``
        # is already committed.
        await self._increment_usage(owner_user_id, adaptation_id=adaptation_id)

    # === Pipeline steps ===

    async def _load(
        self, adaptation_id: int
    ) -> tuple[CVAdaptation | None, UserCV | None, str]:
        """Load the row, the source CV, and the JD text.

        Returns ``(None, None, "")`` when the row is missing or in a
        terminal state. JD text is decoded from ``jd_text`` (raw UTF-8
        bytes). Returns empty string when the bytes are NULL (e.g.
        retention expired) — the LLM will see an empty JD and produce a
        generic output, but the row still flows to a terminal state so
        the client isn't blocked.
        """
        async with self._session_factory() as session:
            await set_rls_user(session, 0, "service")
            row_result = await session.execute(
                select(CVAdaptation).where(CVAdaptation.id == adaptation_id)
            )
            row = row_result.scalar_one_or_none()
            if row is None:
                return None, None, ""
            # Idempotency: skip rows already in a terminal state.
            if row.status in ("completed", "failed"):
                logger.info(
                    "adaptation_skip_terminal",
                    adaptation_id=adaptation_id,
                    status=row.status,
                )
                return None, None, ""
            source_cv: UserCV | None = None
            if row.parent_cv_id is not None:
                cv_result = await session.execute(
                    select(UserCV).where(UserCV.id == row.parent_cv_id)
                )
                source_cv = cv_result.scalar_one_or_none()
            jd_text = ""
            if row.jd_text is not None:
                try:
                    jd_text = row.jd_text.decode("utf-8")
                except UnicodeDecodeError:
                    logger.warning(
                        "adaptation_jd_decode_failed",
                        adaptation_id=adaptation_id,
                    )
                    jd_text = ""
            return row, source_cv, jd_text

    async def _generate_and_validate(
        self,
        *,
        source: dict[str, Any],
        jd_text: str,
        owner_user_id: int,
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        """Run the LLM + validator loop with retries.

        Returns ``(adapted_dict, None, None)`` on success, or
        ``(None, error_code, error_message)`` on terminal failure.
        """
        last_error_code: str | None = None
        last_error_message: str | None = None

        for attempt in range(self._max_retries + 1):
            prompt_jd = jd_text
            if attempt > 0:
                prompt_jd = f"{jd_text}{STRICT_PROMPT_SUFFIX}"
            try:
                adapted_obj = await self._llm_provider.generate_adaptation(
                    source,
                    prompt_jd,
                    max_tokens=4000,
                )
            except Exception as exc:
                logger.exception(
                    "adaptation_llm_failed",
                    owner_user_id=owner_user_id,
                    attempt=attempt,
                    error=str(exc)[:200],
                )
                last_error_code = "LLM_ERROR"
                last_error_message = f"LLM call failed on attempt {attempt + 1}: {exc}"
                if attempt < self._max_retries:
                    await asyncio.sleep(RETRY_SLEEP_SECONDS)
                    continue
                return None, last_error_code, last_error_message

            adapted_dict = adapted_obj.model_dump()
            validation = validate_adaptation(source, adapted_dict)
            if validation.ok:
                return adapted_dict, None, None

            logger.warning(
                "adaptation_validation_failed",
                owner_user_id=owner_user_id,
                attempt=attempt,
                violations=validation.violations[:3],
            )
            last_error_code = "INVALID_HONESTY"
            last_error_message = "; ".join(validation.violations[:3])
            if attempt < self._max_retries:
                await asyncio.sleep(RETRY_SLEEP_SECONDS)
                continue

        return None, last_error_code, last_error_message

    async def _persist_success(
        self,
        *,
        adaptation_id: int,
        owner_user_id: int,
        adapted: dict[str, Any],
    ) -> None:
        """Commit the completed row + populated ``adapted_cv_json``."""
        async with self._session_factory() as session:
            await set_rls_user(session, 0, "service")
            row = await session.get(CVAdaptation, adaptation_id)
            if row is None:
                logger.warning(
                    "adaptation_persist_success_row_missing",
                    adaptation_id=adaptation_id,
                )
                return
            row.status = "completed"
            row.completed_at = datetime.now(UTC)
            row.adapted_cv_json = adapted
            row.error_code = None
            row.error_message = None
            await session.commit()
            logger.info(
                "adaptation_completed",
                adaptation_id=adaptation_id,
                owner_user_id=owner_user_id,
            )

    async def _persist_failure(
        self,
        *,
        adaptation_id: int,
        owner_user_id: int,
        error_code: str,
        error_message: str,
    ) -> None:
        """Mark the row failed with the supplied code + message."""
        async with self._session_factory() as session:
            await set_rls_user(session, 0, "service")
            row = await session.get(CVAdaptation, adaptation_id)
            if row is None:
                logger.warning(
                    "adaptation_persist_failure_row_missing",
                    adaptation_id=adaptation_id,
                )
                return
            row.status = "failed"
            row.error_code = error_code
            row.error_message = error_message[:500] if error_message else None
            row.completed_at = datetime.now(UTC)
            await session.commit()
            logger.info(
                "adaptation_failed",
                adaptation_id=adaptation_id,
                owner_user_id=owner_user_id,
                error_code=error_code,
            )

    async def _increment_usage(
        self, owner_user_id: int, *, adaptation_id: int
    ) -> None:
        """Increment the owner's monthly adaptation counter.

        RLS context: bound to the OWNER, not to service. ``usage_counters``
        has FORCE ROW LEVEL SECURITY (migration 011), and this session
        factory hands out bare connections (``NullPool``, no
        ``server_settings``), so a session that does not bind the GUC
        runs with ``app.current_user_id`` unset: the SELECT sees 0 rows
        and the INSERT fails ``usage_counters_owner_insert`` because
        ``NULL = app_current_user_id()`` is not true. The owner id is
        passed in, so the owner policy is both sufficient and the
        narrowest grant available — the service context is not needed
        and would be strictly broader than this write requires.

        The role argument is deliberately omitted. No ``usage_counters``
        policy reads ``app.user_role`` (they key on the id GUC only),
        and the runner has no trustworthy role for the owner, so we
        assert no role rather than inventing one. This also matches
        ``increment_usage`` itself, which re-binds with the bare id
        after its internal COMMIT.

        The failure is logged at ERROR, not WARNING: a counter that does
        not persist is a billing defect (the subscriber keeps unlimited
        adaptations), and a swallowed exception at WARNING is what made
        it invisible in the first place. It does NOT fail the
        adaptation — by this point the LLM call is already paid for and
        ``completed`` is already committed, so raising would discard a
        delivered result without recovering a cent of the spend.
        """
        try:
            async with self._session_factory() as session:
                await set_rls_user(session, owner_user_id)
                await increment_usage(session, owner_user_id, "adaptation")
        except Exception as exc:
            logger.exception(
                "adaptation_usage_increment_failed",
                adaptation_id=adaptation_id,
                owner_user_id=owner_user_id,
                error=str(exc)[:200],
            )


def build_runner() -> AdaptationRunner:
    """Default factory used by ``get_runner()`` in ``app.api.deps``.

    Wires the singleton LLM provider and the shared session factory.
    Tests inject their own session factory / provider.
    """
    from app.db.session import get_session_factory
    from app.llm.factory import get_llm_provider

    return AdaptationRunner(
        session_factory=get_session_factory(),
        llm_provider=get_llm_provider(),
    )
