"""
Tier limits service for billing.

Defines plan limits and provides usage checking functionality.
"""
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscription, UsageCounter
from app.services.rls_context import set_rls_user

# Plan limits configuration
PLAN_LIMITS: dict[str, dict[str, Any]] = {
    "free": {
        "matches_per_month": 3,
        "analyses_per_month": 1,
    },
    "job_seeker_monthly": {
        "matches_per_month": 50,
        "analyses_per_month": 10,
    },
    "recruiter_starter": {
        "matches_per_month": 50,
        "analyses_per_month": None,  # Unlimited
    },
    "recruiter_business": {
        "matches_per_month": 200,
        "analyses_per_month": None,  # Unlimited
    },
    "recruiter_agency": {
        "matches_per_month": None,  # Unlimited
        "analyses_per_month": None,  # Unlimited
    },
}


@dataclass
class PlanLimit:
    """Represents the effective limits for a user's plan."""

    plan: str
    matches_per_month: int | None
    analyses_per_month: int | None
    matches_used: int
    analyses_used: int

    @property
    def matches_remaining(self) -> int | None:
        """Returns remaining matches, or None if unlimited."""
        if self.matches_per_month is None:
            return None
        return max(0, self.matches_per_month - self.matches_used)

    @property
    def analyses_remaining(self) -> int | None:
        """Returns remaining analyses, or None if unlimited."""
        if self.analyses_per_month is None:
            return None
        return max(0, self.analyses_per_month - self.analyses_used)

    def can_use_match(self) -> bool:
        """Check if user can perform a match."""
        if self.matches_per_month is None:
            return True
        return self.matches_used < self.matches_per_month

    def can_use_analysis(self) -> bool:
        """Check if user can perform an analysis."""
        if self.analyses_per_month is None:
            return True
        return self.analyses_used < self.analyses_per_month


async def get_user_plan(session: AsyncSession, user_id: int) -> str:
    """Get the user's current plan."""
    result = await session.execute(
        select(Subscription).where(
            and_(Subscription.user_id == user_id, Subscription.status == "active")
        )
    )
    sub = result.scalar_one_or_none()
    return sub.plan if sub else "free"


async def get_plan_limits(session: AsyncSession, user_id: int, user_role: str = "job_seeker") -> PlanLimit:
    """Get the effective plan limits for a user.

    For recruiters without a paid subscription, returns 0 matches.
    """
    plan = await get_user_plan(session, user_id)

    # Get limits for the plan
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

    # For recruiters without a paid plan, limit is 0
    if user_role == "recruiter" and plan == "free":
        return PlanLimit(
            plan=plan,
            matches_per_month=0,
            analyses_per_month=0,
            matches_used=0,
            analyses_used=0,
        )

    # Get current period usage
    now = datetime.now(UTC)
    period_start = datetime(now.year, now.month, 1, tzinfo=UTC)

    result = await session.execute(
        select(UsageCounter).where(
            and_(
                UsageCounter.user_id == user_id,
                UsageCounter.period_start >= period_start,
            )
        )
    )
    counter = result.scalar_one_or_none()

    matches_used = counter.matches_used if counter else 0
    analyses_used = counter.analyses_used if counter else 0

    return PlanLimit(
        plan=plan,
        matches_per_month=limits["matches_per_month"],
        analyses_per_month=limits["analyses_per_month"],
        matches_used=matches_used,
        analyses_used=analyses_used,
    )


async def check_limit(
    session: AsyncSession, user_id: int, resource: str, user_role: str = "job_seeker"
) -> PlanLimit:
    """Check if user can use resource without incrementing.

    This is a read-only operation that validates whether the user has
    available quota for the given resource.

    Args:
        session: Database session
        user_id: User ID
        resource: "match" or "analysis"
        user_role: User role (job_seeker or recruiter)

    Returns:
        Current PlanLimit with usage info

    Raises:
        ValueError: If user has exceeded their limit
    """
    # Get current limits
    limits = await get_plan_limits(session, user_id, user_role)

    # Check if allowed
    if resource == "match" and not limits.can_use_match():
        raise ValueError("PLAN_LIMIT_REACHED")
    if resource == "analysis" and not limits.can_use_analysis():
        raise ValueError("PLAN_LIMIT_REACHED")

    return limits


async def increment_usage(
    session: AsyncSession, user_id: int, resource: str
) -> PlanLimit:
    """Increment usage counter for a resource.

    This should be called AFTER the operation succeeds to ensure credits
    are only consumed on successful operations.

    Note: This uses a separate transaction from the main operation.
    For high-concurrency scenarios, consider using SELECT ... FOR UPDATE
    to prevent race conditions. For MVP, we accept that concurrent requests
    may slightly exceed the limit.

    Args:
        session: Database session
        user_id: User ID
        resource: "match" or "analysis"

    Returns:
        Updated PlanLimit after incrementing
    """
    # Get or create usage counter for current period
    now = datetime.now(UTC)
    period_start = datetime(now.year, now.month, 1, tzinfo=UTC)

    result = await session.execute(
        select(UsageCounter).where(
            and_(
                UsageCounter.user_id == user_id,
                UsageCounter.period_start == period_start,
            )
        )
    )
    counter = result.scalar_one_or_none()

    if counter is None:
        counter = UsageCounter(user_id=user_id, period_start=period_start)
        session.add(counter)
        await session.flush()

    # Increment the counter
    if resource == "match":
        counter.matches_used += 1
    else:
        counter.analyses_used += 1

    await session.commit()

    # SET LOCAL context died with the COMMIT above; re-bind before the
    # follow-up read so usage_counters/subscriptions remain visible (RLS).
    await set_rls_user(session, user_id)

    # Return updated limits
    return await get_plan_limits(session, user_id, "job_seeker")
