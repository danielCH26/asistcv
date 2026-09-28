"""
Tests for the ``adaptation`` resource in the tier limits system.

Slice A (sprint-adapt-cv-outreach, PR2) extends the existing match /
analysis quota with a third resource: ``adaptation``. This file
exercises the new field on ``PlanLimit`` and the new branch in
``check_limit`` / ``increment_usage``.

We follow the same test pattern used for the existing tier resources
(see ``test_stripe_webhook.py`` for the subscription setup helpers and
the way ``PLAN_LIMITS`` is consumed).
"""
from __future__ import annotations

import pytest

from app.db.models import Subscription, User
from app.services.rls_context import set_rls_user
from app.services.tier_limits import (
    PLAN_LIMITS,
    PlanLimit,
    check_limit,
    get_plan_limits,
    increment_usage,
)


async def _create_user(clean_db, email: str, role: str = "job_seeker") -> User:
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


class TestPlanLimitsConfiguration:
    """The PLAN_LIMITS dict must declare ``adaptations_per_month``."""

    @pytest.mark.parametrize(
        "plan,expected",
        [
            ("free", 0),
            ("job_seeker_monthly", 5),
            ("recruiter_starter", 10),
            ("recruiter_business", 20),
        ],
    )
    def test_paid_plans_adaptations_caps(self, plan: str, expected: int) -> None:
        assert PLAN_LIMITS[plan]["adaptations_per_month"] == expected

    def test_agency_plan_adaptations_unlimited(self) -> None:
        assert PLAN_LIMITS["recruiter_agency"]["adaptations_per_month"] is None

    def test_free_plan_adaptations_disabled(self) -> None:
        """Free users cannot adapt (audit funnel is the free path)."""
        assert PLAN_LIMITS["free"]["adaptations_per_month"] == 0


class TestPlanLimitAdaptations:
    """The dataclass exposes ``adaptations_remaining`` and ``can_use_adaptation``."""

    def test_can_use_adaptation_when_within_cap(self) -> None:
        limit = PlanLimit(
            plan="seeker_monthly",
            matches_per_month=50,
            analyses_per_month=10,
            adaptations_per_month=5,
            matches_used=0,
            analyses_used=0,
            adaptations_used=3,
        )
        assert limit.can_use_adaptation() is True
        assert limit.adaptations_remaining == 2

    def test_cannot_use_adaptation_when_at_cap(self) -> None:
        limit = PlanLimit(
            plan="seeker_monthly",
            matches_per_month=50,
            analyses_per_month=10,
            adaptations_per_month=5,
            matches_used=0,
            analyses_used=0,
            adaptations_used=5,
        )
        assert limit.can_use_adaptation() is False
        assert limit.adaptations_remaining == 0

    def test_unlimited_adaptation_always_allowed(self) -> None:
        limit = PlanLimit(
            plan="recruiter_agency",
            matches_per_month=None,
            analyses_per_month=None,
            adaptations_per_month=None,
            matches_used=999,
            analyses_used=999,
            adaptations_used=999,
        )
        assert limit.can_use_adaptation() is True
        assert limit.adaptations_remaining is None


class TestFreeUserAdaptations:
    """Free users cannot run adaptations — value=0 blocks them."""

    async def test_free_user_adaptation_blocked(
        self, clean_db
    ) -> None:
        user = await _create_user(clean_db, "free@example.com")
        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            with pytest.raises(ValueError, match="PLAN_LIMIT_REACHED"):
                await check_limit(session, user.id, "adaptation", "job_seeker")


class TestRecruiterFreeAdaptations:
    """Recruiters on free plan get the recruiter-on-free 0-cap override."""

    async def test_recruiter_free_adaptation_blocked(
        self, clean_db
    ) -> None:
        user = await _create_user(clean_db, "rec@example.com", role="recruiter")
        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "recruiter")
            with pytest.raises(ValueError, match="PLAN_LIMIT_REACHED"):
                await check_limit(session, user.id, "adaptation", "recruiter")


class TestSeekerMonthlyAdaptations:
    """Seeker monthly: 5 adaptations / month, 6th → 402 PLAN_LIMIT_REACHED."""

    async def test_5_adaptations_allowed_then_6th_blocked(
        self, clean_db
    ) -> None:
        user = await _create_user(clean_db, "seeker@example.com")
        await _create_subscription(clean_db, user.id, "job_seeker_monthly")

        # Burn through 5 adaptations.
        for _ in range(5):
            async with clean_db.session_factory() as session:
                await set_rls_user(session, user.id, "job_seeker")
                await check_limit(session, user.id, "adaptation", "job_seeker")
                await increment_usage(session, user.id, "adaptation")

        # 6th call must trip PLAN_LIMIT_REACHED.
        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            with pytest.raises(ValueError, match="PLAN_LIMIT_REACHED"):
                await check_limit(session, user.id, "adaptation", "job_seeker")

    async def test_counter_increments_correctly(
        self, clean_db
    ) -> None:
        """After N increments, ``adaptations_used`` reflects N."""
        user = await _create_user(clean_db, "counter@example.com")
        await _create_subscription(clean_db, user.id, "job_seeker_monthly")

        for _ in range(3):
            async with clean_db.session_factory() as session:
                await set_rls_user(session, user.id, "job_seeker")
                await increment_usage(session, user.id, "adaptation")

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            limits = await get_plan_limits(session, user.id, "job_seeker")
            assert limits.adaptations_used == 3
            assert limits.adaptations_remaining == 2
            assert limits.adaptations_per_month == 5


class TestRecruiterAgencyUnlimitedAdaptations:
    """Agency plan: adaptations_per_month=None → unlimited."""

    async def test_agency_user_adaptation_unbounded(
        self, clean_db
    ) -> None:
        user = await _create_user(clean_db, "agency@example.com", role="recruiter")
        await _create_subscription(clean_db, user.id, "recruiter_agency")

        # Even after a lot of increments the check stays clean.
        for _ in range(50):
            async with clean_db.session_factory() as session:
                await set_rls_user(session, user.id, "recruiter")
                await check_limit(session, user.id, "adaptation", "recruiter")
                await increment_usage(session, user.id, "adaptation")

        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "recruiter")
            limits = await get_plan_limits(session, user.id, "recruiter")
            assert limits.adaptations_per_month is None
            assert limits.adaptations_remaining is None
            assert limits.adaptations_used == 50


class TestResourceIsolation:
    """Adaptation quota is independent of match/analysis quotas."""

    async def test_match_quota_does_not_block_adaptation(
        self, clean_db
    ) -> None:
        """Burning all match quota leaves adaptation quota untouched."""
        user = await _create_user(clean_db, "iso1@example.com")
        await _create_subscription(clean_db, user.id, "job_seeker_monthly")

        # Exhaust match quota (50).
        for _ in range(50):
            async with clean_db.session_factory() as session:
                await set_rls_user(session, user.id, "job_seeker")
                await increment_usage(session, user.id, "match")

        # Adaptation should still be allowed — independent resource.
        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            limits = await check_limit(
                session, user.id, "adaptation", "job_seeker"
            )
            assert limits.adaptations_remaining == 5

    async def test_adaptation_quota_does_not_block_match(
        self, clean_db
    ) -> None:
        """Burning all adaptation quota leaves match quota untouched."""
        user = await _create_user(clean_db, "iso2@example.com")
        await _create_subscription(clean_db, user.id, "job_seeker_monthly")

        for _ in range(5):
            async with clean_db.session_factory() as session:
                await set_rls_user(session, user.id, "job_seeker")
                await increment_usage(session, user.id, "adaptation")

        # Match should still be allowed (50/month, used 0).
        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            limits = await check_limit(session, user.id, "match", "job_seeker")
            assert limits.matches_remaining == 50
            assert limits.matches_used == 0


class TestUnknownResourceRejected:
    """A typo in the resource string must surface as a ValueError."""

    async def test_unknown_resource_increment_raises(
        self, clean_db
    ) -> None:
        user = await _create_user(clean_db, "typo@example.com")
        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            with pytest.raises(ValueError, match="Unknown resource"):
                await increment_usage(session, user.id, "wrong")  # type: ignore[arg-type]
