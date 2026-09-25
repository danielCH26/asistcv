"""
Billing API endpoints.

Provides plans catalog, checkout, portal, and subscription management.
"""
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, select

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.models import Subscription, User
from app.services import stripe_client, tier_limits
from app.services.rls_context import bind_rls_context

router = APIRouter(prefix="/billing", tags=["billing"])


# === Request/Response Models ===

class CheckoutRequest(BaseModel):
    """Request to create a checkout session."""

    plan_id: str
    payment_method: str = "card"


class CheckoutResponse(BaseModel):
    """Response with checkout URL."""

    checkout_url: str


class PortalResponse(BaseModel):
    """Response with portal URL."""

    portal_url: str


class SubscriptionResponse(BaseModel):
    """User subscription details."""

    plan_id: str
    status: str
    current_period_end: str | None = None
    limits: dict[str, Any]
    usage: dict[str, Any]
    overage: int = 0
    stripe_customer_id: str | None = None
    has_portal_access: bool = False


# Statuses that grant access to the Stripe Customer Portal. A canceled or
# incomplete subscription has no Stripe customer (or a stale one), so the
# portal CTA must be hidden to avoid a 400 NO_CUSTOMER from /v1/billing/portal.
_PORTAL_STATUSES = frozenset({"active", "trialing", "past_due"})


class PlanResponse(BaseModel):
    """Plan details."""

    plan_id: str
    name: str
    tier: str
    price_cents: int
    currency: str
    interval: str
    features: list[str]
    limits: dict[str, Any]


# === Public Endpoints ===

PLANS_CATALOG = [
    {
        "plan_id": "free",
        "name": "Free",
        "tier": "free",
        "price_cents": 0,
        "currency": "usd",
        "interval": "month",
        "features": ["3 matches/month", "Basic CV analysis"],
        "limits": {"matches_per_month": 3, "analyses_per_month": 1},
    },
    {
        "plan_id": "job_seeker_monthly",
        "name": "Job Seeker Monthly",
        "tier": "job_seeker_monthly",
        "price_cents": 900,
        "currency": "usd",
        "interval": "month",
        "features": ["50 matches/month", "Priority analysis", "Email support"],
        "limits": {"matches_per_month": 50, "analyses_per_month": 10},
    },
    {
        "plan_id": "recruiter_starter",
        "name": "Recruiter Starter",
        "tier": "recruiter_starter",
        "price_cents": 2900,
        "currency": "usd",
        "interval": "month",
        "features": ["50 candidate matches", "Unlimited analyses", "Email support"],
        "limits": {"matches_per_month": 50, "analyses_per_month": None},
    },
    {
        "plan_id": "recruiter_business",
        "name": "Recruiter Business",
        "tier": "recruiter_business",
        "price_cents": 9900,
        "currency": "usd",
        "interval": "month",
        "features": ["200 candidate matches", "Unlimited analyses", "Priority support"],
        "limits": {"matches_per_month": 200, "analyses_per_month": None},
    },
    {
        "plan_id": "recruiter_agency",
        "name": "Recruiter Agency",
        "tier": "recruiter_agency",
        "price_cents": 29900,
        "currency": "usd",
        "interval": "month",
        "features": ["Unlimited matches", "Unlimited analyses", "Dedicated support"],
        "limits": {"matches_per_month": None, "analyses_per_month": None},
    },
]


@router.get("/plans", response_model=list[PlanResponse])
async def get_plans(tier: str | None = None):
    """Get available plans.

    Optional filter by tier (e.g., 'job_seeker_monthly', 'recruiter_starter').
    """
    plans = PLANS_CATALOG
    if tier:
        plans = [p for p in plans if p["tier"] == tier]
    return plans


# === Protected Endpoints ===

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Create a Stripe Checkout session for plan purchase.

    Requires authenticated user with verified email.

    Supports Idempotency-Key header for safe retries - same key with same
    payload returns the same checkout URL without creating duplicate sessions.
    """
    # Check email verification
    if not current_user.email_verified_at:
        raise HTTPException(
            status_code=403,
            detail="Email verification required to purchase plans",
        )

    # Validate plan
    valid_plans = ["job_seeker_monthly", "recruiter_starter", "recruiter_business", "recruiter_agency"]
    if request.plan_id not in valid_plans:
        raise HTTPException(status_code=400, detail="Invalid plan_id")

    # Validate payment method
    if request.payment_method not in ["card", "pse"]:
        raise HTTPException(status_code=400, detail="Invalid payment_method")

    # Validate recruiter plans require recruiter role
    if request.plan_id.startswith("recruiter_") and current_user.role != "recruiter":
        raise HTTPException(
            status_code=400,
            detail="Recruiter plans require recruiter role",
        )

    settings = get_settings()
    success_url = f"{settings.frontend_url}/billing/subscription?status=success"
    cancel_url = f"{settings.frontend_url}/billing/plans"

    try:
        # Same-key retries return the same session (Stripe-side idempotency); verified by test_checkout_idempotency_key_passthrough
        result = await stripe_client.create_checkout_session(
            user_id=current_user.id,
            plan_id=request.plan_id,
            payment_method=request.payment_method,
            customer_email=current_user.email,
            success_url=success_url,
            cancel_url=cancel_url,
            idempotency_key=idempotency_key,
        )
        return CheckoutResponse(checkout_url=result["checkout_url"])
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/portal", response_model=PortalResponse)
async def create_portal(current_user: User = Depends(get_current_user)):
    """Create a Stripe Customer Portal session.

    Allows users to manage/cancel their subscription.
    """
    from app.db.session import get_session_context

    async with get_session_context() as session:
        await bind_rls_context(session, current_user.id, current_user.role)
        result = await session.execute(
            select(Subscription).where(
                and_(
                    Subscription.user_id == current_user.id,
                    Subscription.stripe_customer_id.isnot(None),
                )
            )
        )
        sub = result.scalar_one_or_none()

        if not sub or not sub.stripe_customer_id:
            raise HTTPException(
                status_code=400,
                detail="NO_CUSTOMER",
            )

    settings = get_settings()
    return_url = f"{settings.frontend_url}/billing/subscription"

    try:
        result = await stripe_client.create_portal_session(
            customer_id=sub.stripe_customer_id,
            return_url=return_url,
        )
        return PortalResponse(portal_url=result["portal_url"])
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(current_user: User = Depends(get_current_user)):
    """Get current user's subscription details."""
    from app.db.session import get_session_context

    async with get_session_context() as session:
        await bind_rls_context(session, current_user.id, current_user.role)
        # Get subscription
        result = await session.execute(
            select(Subscription).where(
                and_(
                    Subscription.user_id == current_user.id,
                    Subscription.status == "active",
                )
            )
        )
        sub = result.scalar_one_or_none()

        # Get plan limits and usage
        limits = await tier_limits.get_plan_limits(session, current_user.id, current_user.role)

    # Calculate overage: matches used beyond the plan limit
    overage = 0
    if limits.matches_per_month is not None:
        overage = max(0, limits.matches_used - limits.matches_per_month)

    return SubscriptionResponse(
        plan_id=limits.plan,
        status=sub.status if sub else "active",
        current_period_end=sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
        limits={
            "matches_per_month": limits.matches_per_month,
            "analyses_per_month": limits.analyses_per_month,
        },
        usage={
            "matches_this_month": limits.matches_used,
            "analyses_used": limits.analyses_used,
        },
        overage=overage,
        stripe_customer_id=sub.stripe_customer_id if sub else None,
        has_portal_access=bool(
            sub is not None
            and sub.stripe_customer_id is not None
            and sub.status in _PORTAL_STATUSES
        ),
    )
