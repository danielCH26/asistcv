"""
Endpoint tests for ``/v1/adaptations`` and ``/internal/adaptations/cleanup``.

These exercise the API surface end-to-end:

- POST /v1/adaptations → 202 happy path, 402 PLAN_LIMIT_REACHED,
  503 FEATURE_DISABLED, 400/422 invalid body, 404 NO_CV_FOUND,
  200 cached hit.
- GET /v1/adaptations/{id} → 200 completed, 200 pending, 404 NOT_FOUND.
- GET /v1/adaptations/by-cv/{cv_id} → 200 with the user's rows,
  404 NO_CV_FOUND.
- Kill-switch → with ``ADAPTATION_ENABLED=false`` the POST AND both GETs
  return 503 ``FEATURE_DISABLED`` and no statement is issued.
- POST /internal/adaptations/cleanup → 401 missing token,
  200 with deleted count.

We mock the runner (``get_runner`` dependency override) so the
endpoints run without any LLM provider. The cache-hit test seeds a
completed row directly so we can exercise the 200 short-circuit
without standing up a fake LLM at all.

Auth uses ``app.dependency_overrides[get_current_user]`` with a real
``CurrentUser`` object — same pattern as the rest of the test suite
(see ``tests/test_billing.py``).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.api.deps import CurrentUser, get_current_user, get_runner
from app.core.config import get_settings
from app.db.models import CVAdaptation, Subscription, User, UserCV
from app.services.adaptation_cache import compute_jd_text_hash
from app.services.rls_context import set_rls_user

# === Auth + user fixtures


def _make_current_user(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id, name=user.full_name, role=user.role, auth_method="jwt"
    )


async def _create_user(
    clean_db, email: str = "owner@example.com", role: str = "job_seeker"
) -> User:
    async with clean_db.session_factory() as session:
        user = User(
            email=email,
            password_hash="x",
            role=role,
            full_name=email.split("@")[0].title(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _create_subscription(
    clean_db, user_id: int, plan: str, status: str = "active"
) -> Subscription:
    async with clean_db.session_factory() as session:
        sub = Subscription(
            user_id=user_id,
            plan=plan,
            status=status,
            stripe_subscription_id=f"sub_{user_id}",
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return sub


async def _create_cv(clean_db, owner_user_id: int) -> UserCV:
    async with clean_db.session_factory() as session:
        cv = UserCV(
            owner_user_id=owner_user_id,
            original_filename="cv.pdf",
            structured={
                "full_name": "Owner",
                "experience": [
                    {
                        "title": "Senior Backend Engineer",
                        "company": "Acme",
                        "dates": "2020-2024",
                        "description": "Built Python services on AWS Lambda.",
                    }
                ],
                "skills": ["Python", "AWS"],
                "education": [],
                "languages": ["English"],
            },
            content_version=1,
        )
        session.add(cv)
        await session.commit()
        await session.refresh(cv)
        return cv


@asynccontextmanager
async def _override_current_user(user: User):
    """Install a ``get_current_user`` override and clean up after."""
    current = _make_current_user(user)
    app = __import__("app.main", fromlist=["app"]).app
    app.dependency_overrides[get_current_user] = lambda: current
    try:
        yield current
    finally:
        app.dependency_overrides.pop(get_current_user, None)


class _FakeRunner:
    """Test double for ``AdaptationRunner``.

    Records calls without doing DB work — keeps the row in its
    ``pending`` state so the endpoint test can verify the row was
    created (not completed). The runner test file exercises the real
    persistence behavior.
    """

    def __init__(self) -> None:
        self.calls: list[int] = []

    async def run(self, adaptation_id: int) -> None:
        self.calls.append(adaptation_id)


@asynccontextmanager
async def _override_runner(runner: _FakeRunner | None = None):
    """Install a ``get_runner`` override that returns a fake runner."""
    app = __import__("app.main", fromlist=["app"]).app
    fake = runner or _FakeRunner()
    app.dependency_overrides[get_runner] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_runner, None)


@asynccontextmanager
async def _enable_adaptation_flag():
    """Flip the ADAPTATION_ENABLED flag for tests that need the feature."""
    settings = get_settings()
    original = settings.adaptation_enabled
    settings.adaptation_enabled = True
    try:
        yield
    finally:
        settings.adaptation_enabled = original


# === POST /v1/adaptations


class TestCreateAdaptation:
    """POST /v1/adaptations happy paths and error codes."""

    @pytest.mark.asyncio
    async def test_post_202_happy_path(
        self, async_client, clean_db, monkeypatch
    ) -> None:
        """A valid request → 202 with adaptation_id; a new pending row in DB."""
        # Make the increment_usage path a no-op so the fake runner's
        # post-success write doesn't try to hit the subscriptions table
        # under the service context.
        async def _noop_increment(session, user_id, resource):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            "app.services.adaptation_runner.increment_usage", _noop_increment
        )

        user = await _create_user(clean_db)
        await _create_subscription(clean_db, user.id, "job_seeker_monthly")
        cv = await _create_cv(clean_db, user.id)
        fake_runner = _FakeRunner()

        async with _enable_adaptation_flag(), _override_current_user(user), _override_runner(fake_runner):
            response = await async_client.post(
                "/v1/adaptations",
                json={
                    "cv_id": cv.id,
                    "jd_text": "Looking for a Senior Backend Engineer with Python and AWS.",
                },
            )

        assert response.status_code == 202, response.text
        body = response.json()
        assert body["status"] == "pending"
        assert isinstance(body["adaptation_id"], int)
        assert body["adaptation_id"] > 0

        # Row exists in DB with status=pending.
        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            row = await session.get(CVAdaptation, body["adaptation_id"])
            assert row is not None
            assert row.status == "pending"
            assert row.parent_cv_id == cv.id
            assert row.owner_user_id == user.id

        # Fake runner was spawned with the row's id.
        assert fake_runner.calls == [body["adaptation_id"]]

    @pytest.mark.asyncio
    async def test_post_402_plan_limit_reached(
        self, async_client, clean_db
    ) -> None:
        """A free-tier user → 402 PLAN_LIMIT_REACHED."""
        user = await _create_user(clean_db)  # No subscription → free → 0 adaptations.
        cv = await _create_cv(clean_db, user.id)

        async with _enable_adaptation_flag(), _override_current_user(user), _override_runner():
            response = await async_client.post(
                "/v1/adaptations",
                json={
                    "cv_id": cv.id,
                    "jd_text": "Looking for a Senior Backend Engineer with Python and AWS.",
                },
            )

        assert response.status_code == 402
        assert response.json()["detail"] == "PLAN_LIMIT_REACHED"

    @pytest.mark.asyncio
    async def test_post_503_feature_disabled(
        self, async_client, clean_db
    ) -> None:
        """Flag off → 503 FEATURE_DISABLED (gated by ``require_adaptation_enabled``)."""
        # ADAPTATION_ENABLED defaults to False; no override needed.
        user = await _create_user(clean_db)
        cv = await _create_cv(clean_db, user.id)

        async with _override_current_user(user), _override_runner():
            response = await async_client.post(
                "/v1/adaptations",
                json={"cv_id": cv.id, "jd_text": "anything"},
            )

        assert response.status_code == 503
        assert response.json()["detail"] == "FEATURE_DISABLED"

    @pytest.mark.asyncio
    async def test_post_422_invalid_body_no_cv_id(
        self, async_client, clean_db
    ) -> None:
        """Body missing ``cv_id`` → 422 from pydantic validation."""
        user = await _create_user(clean_db)
        async with _enable_adaptation_flag(), _override_current_user(user), _override_runner():
            response = await async_client.post(
                "/v1/adaptations",
                json={
                    "jd_text": "Looking for a Senior Backend Engineer with Python and AWS."
                },
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_post_422_invalid_body_empty_jd_text(
        self, async_client, clean_db
    ) -> None:
        """Body with empty ``jd_text`` → 422 from pydantic validation."""
        user = await _create_user(clean_db)
        cv = await _create_cv(clean_db, user.id)
        async with _enable_adaptation_flag(), _override_current_user(user), _override_runner():
            response = await async_client.post(
                "/v1/adaptations",
                json={"cv_id": cv.id, "jd_text": ""},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_post_422_jd_text_below_minimum(
        self, async_client, clean_db
    ) -> None:
        """1-49 character ``jd_text`` → 422 from pydantic, runner NOT called.

        Catches the regression where ``min_length`` was loosened and short
        JDs started costing slots on the paid LLM (#83). The runner is
        injected so we can prove pydantic rejected the body BEFORE the
        handler ran -- otherwise a 1-char JD would reach the runner, do
        useless work, and still be charged as a successful slot on
        completion (5 such requests exhaust a ``job_seeker_monthly`` quota).
        """
        user = await _create_user(clean_db)
        await _create_subscription(clean_db, user.id, "job_seeker_monthly")
        cv = await _create_cv(clean_db, user.id)
        fake_runner = _FakeRunner()

        async with (
            _enable_adaptation_flag(),
            _override_current_user(user),
            _override_runner(fake_runner),
        ):
            response = await async_client.post(
                "/v1/adaptations",
                json={"cv_id": cv.id, "jd_text": "x" * 30},
            )

        assert response.status_code == 422, response.text
        # The runner must not be called -- pydantic rejected before the
        # handler ran, so no slot was charged.
        assert fake_runner.calls == [], (
            "runner must not be called when jd_text is below the minimum length; "
            f"calls observed: {fake_runner.calls!r}"
        )

    @pytest.mark.asyncio
    async def test_post_404_no_cv_found(
        self, async_client, clean_db
    ) -> None:
        """cv_id not owned by the caller → 404 NO_CV_FOUND."""
        user = await _create_user(clean_db)
        await _create_subscription(clean_db, user.id, "job_seeker_monthly")

        async with _enable_adaptation_flag(), _override_current_user(user), _override_runner():
            response = await async_client.post(
                "/v1/adaptations",
                json={
                    "cv_id": 999999,
                    "jd_text": "Looking for a Senior Backend Engineer with Python and AWS.",
                },
            )
        assert response.status_code == 404
        assert response.json()["detail"] == "NO_CV_FOUND"

    @pytest.mark.asyncio
    async def test_post_200_cache_hit_returns_cached(
        self, async_client, clean_db
    ) -> None:
        """A cache hit → 200 with the cached payload, no new row created."""
        user = await _create_user(clean_db)
        await _create_subscription(clean_db, user.id, "job_seeker_monthly")
        cv = await _create_cv(clean_db, user.id)
        jd_text = "Looking for a Senior Backend Engineer with Python and AWS."
        jd_hash = compute_jd_text_hash(jd_text)

        # Seed a completed row matching the cache key.
        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            cached = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=jd_hash,
                jd_text=jd_text.encode("utf-8"),
                adapted_cv_json={
                    "full_name": "Owner",
                    "experience": [],
                    "skills": ["Python", "AWS"],
                    "education": [],
                    "languages": ["English"],
                },
                status="completed",
                completed_at=datetime.now(UTC),
            )
            session.add(cached)
            await session.commit()
            await session.refresh(cached)
            cached_id = cached.id

        async with _enable_adaptation_flag(), _override_current_user(user), _override_runner():
            response = await async_client.post(
                "/v1/adaptations",
                json={"cv_id": cv.id, "jd_text": jd_text},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        # Same id as the cached row (no new row created).
        assert body["id"] == cached_id
        assert body["status"] == "completed"
        assert body["adapted_cv"]["full_name"] == "Owner"


# === Concurrent POSTs for the same (cv, jd) ===


class TestConcurrentDuplicatePost:
    """Two POSTs for one (cv, jd) must converge on a single job.

    ``uq_cv_adapt_parent_jd_hash_pending`` (migration 021) allows at most
    one IN-FLIGHT row per (cv, jd), so the second insert of a concurrent
    pair raises ``IntegrityError``. The endpoint resolves the existing
    row and returns 202 with the SAME ``adaptation_id``: one LLM call,
    both clients polling one job, nothing stuck in ``pending``.
    """

    @pytest.mark.asyncio
    async def test_second_post_returns_the_inflight_job(
        self, async_client, clean_db
    ) -> None:
        """A pending row already in flight → 202 with the SAME id.

        Deterministic: seeds the exact row a losing racer would find, so
        the conflict path is exercised without relying on timing.
        """
        user = await _create_user(clean_db)
        await _create_subscription(clean_db, user.id, "job_seeker_monthly")
        cv = await _create_cv(clean_db, user.id)
        jd_text = "Senior Backend Engineer with Python, AWS and PostgreSQL experience."

        inflight = CVAdaptation(
            parent_cv_id=cv.id,
            owner_user_id=user.id,
            jd_text_hash=compute_jd_text_hash(jd_text),
            jd_text=jd_text.encode("utf-8"),
            adapted_cv_json={},
            status="pending",
        )
        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            session.add(inflight)
            await session.commit()
            await session.refresh(inflight)

        fake_runner = _FakeRunner()
        async with (
            _enable_adaptation_flag(),
            _override_current_user(user),
            _override_runner(fake_runner),
        ):
            response = await async_client.post(
                "/v1/adaptations", json={"cv_id": cv.id, "jd_text": jd_text}
            )

        assert response.status_code == 202, response.text
        body = response.json()
        assert body["adaptation_id"] == inflight.id
        assert body["status"] == "pending"
        # No second runner: the work is already in flight.
        assert fake_runner.calls == []

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            result = await session.execute(
                select(CVAdaptation).where(
                    CVAdaptation.parent_cv_id == cv.id,
                    CVAdaptation.status == "pending",
                )
            )
            rows = result.scalars().all()
            assert [r.id for r in rows] == [inflight.id]

    @pytest.mark.asyncio
    async def test_concurrent_posts_leave_no_stuck_pending(
        self, async_client, clean_db
    ) -> None:
        """Two POSTs fired together → 202s, one row, one runner call.

        The cache only ever serves ``completed`` rows, so a pending row
        never satisfies the second request: the loser always reaches the
        INSERT and always loses. The assertion therefore holds whether or
        not the two requests actually overlap.
        """
        user = await _create_user(clean_db)
        await _create_subscription(clean_db, user.id, "job_seeker_monthly")
        cv = await _create_cv(clean_db, user.id)
        payload = {
            "cv_id": cv.id,
            "jd_text": "Platform engineer with Kubernetes, Go and observability experience.",
        }

        fake_runner = _FakeRunner()
        async with (
            _enable_adaptation_flag(),
            _override_current_user(user),
            _override_runner(fake_runner),
        ):
            first, second = await asyncio.gather(
                async_client.post("/v1/adaptations", json=payload),
                async_client.post("/v1/adaptations", json=payload),
            )

        assert first.status_code == 202, first.text
        assert second.status_code == 202, second.text
        # Both clients are pointed at the same job.
        assert first.json()["adaptation_id"] == second.json()["adaptation_id"]
        # Exactly one runner was spawned, so exactly one LLM call.
        assert len(fake_runner.calls) == 1

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            result = await session.execute(
                select(CVAdaptation).where(
                    CVAdaptation.parent_cv_id == cv.id
                )
            )
            rows = result.scalars().all()
            assert len(rows) == 1
            assert rows[0].id == fake_runner.calls[0]
            # The one row that exists is the in-flight job, not a
            # duplicate left behind by the losing request.
            assert rows[0].status == "pending"


# === Kill-switch: ADAPTATION_ENABLED=false must gate the READ surface too ===


@asynccontextmanager
async def _spy_on_session_statements(monkeypatch):
    """Record every statement issued through ``AsyncSession.execute``.

    Yields the list of statement strings. Patching the class method (not
    an instance) is what makes this catch the endpoint's own session,
    which is created by ``get_db`` inside the request.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    statements: list[str] = []
    original = AsyncSession.execute

    async def _spy(self, statement, *args, **kwargs):  # noqa: ANN001, ANN202
        statements.append(str(statement))
        return await original(self, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", _spy)
    try:
        yield statements
    finally:
        monkeypatch.setattr(AsyncSession, "execute", original)


class TestAdaptationKillSwitch:
    """``ADAPTATION_ENABLED=false`` 503s every route on the adaptations router.

    Regression cover for the incident where only the POST was gated:
    ``GET /v1/adaptations/{id}`` and ``GET /v1/adaptations/by-cv/{cv_id}``
    kept returning 200/404 and kept querying the database while the switch
    was off. The switch is declared once on the router, so a route added
    later is gated by default.
    """

    @pytest.mark.asyncio
    async def test_get_503_feature_disabled(
        self, async_client, clean_db, monkeypatch
    ) -> None:
        """GET by id with the flag off -> 503 FEATURE_DISABLED, not 404/200."""
        user = await _create_user(clean_db)
        cv = await _create_cv(clean_db, user.id)

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            row = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=compute_jd_text_hash("Readable JD"),
                jd_text=b"Readable JD",
                adapted_cv_json={"full_name": "Owner"},
                status="completed",
                completed_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            row_id = row.id

        # ADAPTATION_ENABLED defaults to False; no override needed.
        async with _spy_on_session_statements(monkeypatch) as statements:
            async with _override_current_user(user):
                response = await async_client.get(f"/v1/adaptations/{row_id}")

        assert response.status_code == 503, response.text
        assert response.json()["detail"] == "FEATURE_DISABLED"
        # The gate lives on the router, so FastAPI never solves ``get_db``:
        # the endpoint cannot even open a session, let alone query a row.
        assert statements == [], (
            f"no statement should be issued while the switch is off, got {statements}"
        )

    @pytest.mark.asyncio
    async def test_list_by_cv_503_feature_disabled(
        self, async_client, clean_db, monkeypatch
    ) -> None:
        """GET by-cv with the flag off -> 503 FEATURE_DISABLED, not 404/200."""
        user = await _create_user(clean_db)
        cv = await _create_cv(clean_db, user.id)

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            row = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=compute_jd_text_hash("Listable JD"),
                jd_text=b"Listable JD",
                adapted_cv_json={},
                status="pending",
            )
            session.add(row)
            await session.commit()

        async with _spy_on_session_statements(monkeypatch) as statements:
            async with _override_current_user(user):
                response = await async_client.get(f"/v1/adaptations/by-cv/{cv.id}")

        assert response.status_code == 503, response.text
        assert response.json()["detail"] == "FEATURE_DISABLED"
        assert statements == [], (
            f"no statement should be issued while the switch is off, got {statements}"
        )

    @pytest.mark.asyncio
    async def test_flag_on_still_serves_reads(
        self, async_client, clean_db, monkeypatch
    ) -> None:
        """Negative control: with the flag on, the same GETs reach the DB.

        Proves the 503 above comes from the switch and not from an
        unrelated breakage in the read path, and that the statement spy
        is actually wired (it must observe the query).
        """
        user = await _create_user(clean_db)
        cv = await _create_cv(clean_db, user.id)

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            row = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=compute_jd_text_hash("Visible JD"),
                jd_text=b"Visible JD",
                adapted_cv_json={"full_name": "Owner"},
                status="completed",
                completed_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            row_id = row.id

        async with _spy_on_session_statements(monkeypatch) as statements:
            async with _enable_adaptation_flag(), _override_current_user(user):
                response = await async_client.get(f"/v1/adaptations/{row_id}")

        assert response.status_code == 200, response.text
        assert response.json()["id"] == row_id
        assert any("cv_adaptations" in s for s in statements), (
            f"spy should observe the cv_adaptations query, got {statements}"
        )


# === GET /v1/adaptations/{id}


class TestGetAdaptation:
    """GET /v1/adaptations/{id} detail polling."""

    @pytest.mark.asyncio
    async def test_get_200_completed(
        self, async_client, clean_db
    ) -> None:
        """A completed row returns the full payload including ``adapted_cv``."""
        user = await _create_user(clean_db)
        cv = await _create_cv(clean_db, user.id)
        jd_hash = compute_jd_text_hash("Some JD")

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            row = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=jd_hash,
                jd_text=b"Some JD",
                adapted_cv_json={
                    "full_name": "Owner",
                    "experience": [],
                    "skills": ["Python"],
                    "education": [],
                    "languages": [],
                },
                status="completed",
                completed_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            row_id = row.id

        async with _enable_adaptation_flag(), _override_current_user(user):
            response = await async_client.get(f"/v1/adaptations/{row_id}")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == row_id
        assert body["status"] == "completed"
        assert body["adapted_cv"] is not None
        assert body["error_code"] is None
        assert body["error_message"] is None

    @pytest.mark.asyncio
    async def test_get_200_pending(
        self, async_client, clean_db
    ) -> None:
        """A pending row returns ``status=pending`` and no adapted_cv."""
        user = await _create_user(clean_db)
        cv = await _create_cv(clean_db, user.id)
        jd_hash = compute_jd_text_hash("Pending JD")

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            row = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=jd_hash,
                jd_text=b"Pending JD",
                adapted_cv_json={},
                status="pending",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            row_id = row.id

        async with _enable_adaptation_flag(), _override_current_user(user):
            response = await async_client.get(f"/v1/adaptations/{row_id}")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "pending"
        assert body["adapted_cv"] is None

    @pytest.mark.asyncio
    async def test_get_404_cross_user(
        self, async_client, clean_db
    ) -> None:
        """Cross-user lookup → 404 NOT_FOUND."""
        owner = await _create_user(clean_db, "owner@example.com")
        attacker = await _create_user(clean_db, "attacker@example.com")
        cv = await _create_cv(clean_db, owner.id)
        jd_hash = compute_jd_text_hash("owner-only JD")

        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            row = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=owner.id,
                jd_text_hash=jd_hash,
                jd_text=b"owner-only JD",
                adapted_cv_json={},
                status="pending",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            row_id = row.id

        # Attacker tries to read — RLS + owner check both 404.
        async with _enable_adaptation_flag(), _override_current_user(attacker):
            response = await async_client.get(f"/v1/adaptations/{row_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_404_missing(
        self, async_client, clean_db
    ) -> None:
        """A non-existent id → 404 NOT_FOUND."""
        user = await _create_user(clean_db)
        async with _enable_adaptation_flag(), _override_current_user(user):
            response = await async_client.get("/v1/adaptations/999999")
        assert response.status_code == 404


# === GET /v1/adaptations/by-cv/{cv_id}


class TestListByCV:
    """GET /v1/adaptations/by-cv/{cv_id} list endpoint."""

    @pytest.mark.asyncio
    async def test_list_returns_user_rows_newest_first(
        self, async_client, clean_db
    ) -> None:
        """The list is in reverse chronological order, RLS-filtered."""
        user = await _create_user(clean_db)
        cv = await _create_cv(clean_db, user.id)
        jd_hash = compute_jd_text_hash("x")

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            older = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=jd_hash,
                jd_text=b"x",
                adapted_cv_json={},
                status="completed",
                created_at=datetime.now(UTC) - timedelta(hours=2),
                completed_at=datetime.now(UTC) - timedelta(hours=2),
            )
            newer = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=jd_hash,
                jd_text=b"x",
                adapted_cv_json={},
                status="pending",
                created_at=datetime.now(UTC) - timedelta(minutes=5),
            )
            session.add(older)
            session.add(newer)
            await session.commit()

        async with _enable_adaptation_flag(), _override_current_user(user):
            response = await async_client.get(f"/v1/adaptations/by-cv/{cv.id}")

        assert response.status_code == 200, response.text
        items = response.json()
        assert [item["id"] for item in items] == [newer.id, older.id]
        assert all(item["cv_id"] == cv.id for item in items)

    @pytest.mark.asyncio
    async def test_list_404_no_cv(
        self, async_client, clean_db
    ) -> None:
        """Asking for a CV the caller doesn't own → 404 NO_CV_FOUND."""
        user = await _create_user(clean_db)
        async with _enable_adaptation_flag(), _override_current_user(user):
            response = await async_client.get("/v1/adaptations/by-cv/999999")
        assert response.status_code == 404
        assert response.json()["detail"] == "NO_CV_FOUND"

    @pytest.mark.asyncio
    async def test_list_rls_filters_cross_user(
        self, async_client, clean_db
    ) -> None:
        """A second user's row doesn't appear in the first user's list."""
        owner = await _create_user(clean_db, "owner@example.com")
        attacker = await _create_user(clean_db, "attacker@example.com")
        cv = await _create_cv(clean_db, owner.id)
        jd_hash = compute_jd_text_hash("x")

        async with clean_db.session_factory() as session:
            await set_rls_user(session, owner.id, "job_seeker")
            row = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=owner.id,
                jd_text_hash=jd_hash,
                jd_text=b"x",
                adapted_cv_json={},
                status="completed",
                completed_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()

        # Attacker lists by their own (non-existent) CV → 404.
        async with _enable_adaptation_flag(), _override_current_user(attacker):
            response = await async_client.get(f"/v1/adaptations/by-cv/{cv.id}")
        assert response.status_code == 404


# === POST /internal/adaptations/cleanup


class TestCleanupEndpoint:
    """POST /internal/adaptations/cleanup (cron-only)."""

    @pytest.mark.asyncio
    async def test_cleanup_401_missing_api_key(
        self, async_client, clean_db, monkeypatch
    ) -> None:
        """No X-Backend-API-Key header → 401 UNAUTHORIZED."""
        # Pin BACKEND_API_KEY so the endpoint isn't open.
        monkeypatch.setattr(
            "app.api.v1.internal.adaptations._verify_api_key",
            lambda provided: provided == "test-secret",
        )
        # Override the settings-aware verifier with our own.
        from app.api.v1.internal import adaptations as internal_module

        monkeypatch.setattr(
            internal_module,
            "_verify_api_key",
            lambda provided: bool(provided) and provided == "test-secret",
        )

        response = await async_client.post("/internal/adaptations/cleanup")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_cleanup_200_deletes_old_rows(
        self, async_client, clean_db, monkeypatch
    ) -> None:
        """Happy path: returns ``{deleted: N}`` and removes eligible rows."""
        user = await _create_user(clean_db)
        cv = await _create_cv(clean_db, user.id)

        now = datetime.now(UTC)

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            # 91-day-old completed row → eligible.
            old_completed = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=compute_jd_text_hash("old"),
                jd_text=b"old",
                adapted_cv_json={},
                status="completed",
                created_at=now - timedelta(days=100),
                completed_at=now - timedelta(days=91),
            )
            # 30-day-old completed row → kept.
            fresh_completed = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=compute_jd_text_hash("fresh"),
                jd_text=b"fresh",
                adapted_cv_json={},
                status="completed",
                created_at=now - timedelta(days=10),
                completed_at=now - timedelta(days=10),
            )
            # 2-hour-old pending row → orphan, eligible.
            old_pending = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=compute_jd_text_hash("old_pending"),
                jd_text=b"old_pending",
                adapted_cv_json={},
                status="pending",
                created_at=now - timedelta(hours=2),
            )
            # 30-minute-old pending row → kept.
            fresh_pending = CVAdaptation(
                parent_cv_id=cv.id,
                owner_user_id=user.id,
                jd_text_hash=compute_jd_text_hash("fresh_pending"),
                jd_text=b"fresh_pending",
                adapted_cv_json={},
                status="pending",
                created_at=now - timedelta(minutes=30),
            )
            session.add_all([old_completed, fresh_completed, old_pending, fresh_pending])
            await session.commit()

        # Force the API-key check to pass without setting the env var.
        from app.api.v1.internal import adaptations as internal_module

        monkeypatch.setattr(
            internal_module,
            "_verify_api_key",
            lambda provided: provided == "test-secret",
        )

        response = await async_client.post(
            "/internal/adaptations/cleanup",
            headers={"X-Backend-API-Key": "test-secret"},
        )

        assert response.status_code == 200, response.text
        assert response.json() == {"deleted": 2}

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            from sqlalchemy import select

            rows = (
                await session.execute(
                    select(CVAdaptation).order_by(CVAdaptation.id)
                )
            ).scalars().all()
            # Two rows remain: fresh_completed + fresh_pending.
            remaining_ids = {row.id for row in rows}
            assert remaining_ids == {fresh_completed.id, fresh_pending.id}

    @pytest.mark.asyncio
    async def test_cleanup_401_wrong_api_key(
        self, async_client, clean_db, monkeypatch
    ) -> None:
        """Wrong key → 401."""
        from app.api.v1.internal import adaptations as internal_module

        monkeypatch.setattr(
            internal_module,
            "_verify_api_key",
            lambda provided: provided == "right",
        )
        response = await async_client.post(
            "/internal/adaptations/cleanup",
            headers={"X-Backend-API-Key": "wrong"},
        )
        assert response.status_code == 401
