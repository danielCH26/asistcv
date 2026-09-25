"""
Stripe client service.

Thin wrapper around Stripe SDK for checkout, portal, and customer management.
Mockable for tests.
"""
from typing import Any

import stripe

from app.core.config import get_settings


def _get_stripe():
    """Get configured Stripe module."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise ValueError("Stripe is not configured. Set STRIPE_SECRET_KEY.")
    stripe.api_key = settings.stripe_secret_key
    return stripe


async def create_customer(user_id: int, email: str, name: str | None = None) -> dict[str, Any]:
    """Create a Stripe customer for a user."""
    s = _get_stripe()
    response = s.Customer.create(
        email=email,
        name=name or "",
        metadata={"user_id": str(user_id)},
    )
    return {
        "id": response.id,
        "email": response.email,
        "name": response.name,
    }


async def create_checkout_session(
    user_id: int,
    plan_id: str,
    payment_method: str,
    customer_email: str,
    success_url: str,
    cancel_url: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Create a Stripe Checkout session.

    Args:
        user_id: User ID
        plan_id: Plan to purchase (job_seeker_monthly, recruiter_starter, etc.)
        payment_method: "card" or "pse"
        customer_email: Customer email
        success_url: URL to redirect on success
        cancel_url: URL to redirect on cancel
        idempotency_key: Optional idempotency key

    Returns:
        Dict with checkout URL and session ID
    """
    s = _get_stripe()

    # Get price ID for plan
    price_id = _get_price_id(plan_id)

    # Build checkout parameters
    params: dict[str, Any] = {
        "mode": "subscription",
        "customer_email": customer_email,
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {"user_id": str(user_id), "plan_id": plan_id},
    }

    # Configure payment method types
    if payment_method == "pse":
        params["payment_method_types"] = ["pse"]
        params["payment_method_options"] = {"pse": {"country": "CO"}}
    else:
        params["payment_method_types"] = ["card"]

    # Add idempotency key if provided
    if idempotency_key:
        params["idempotency_key"] = idempotency_key

    response = s.checkout.Session.create(**params)

    return {
        "session_id": response.id,
        "checkout_url": response.url,
    }


async def create_portal_session(customer_id: str, return_url: str) -> dict[str, Any]:
    """Create a Stripe Customer Portal session.

    Args:
        customer_id: Stripe customer ID
        return_url: URL to redirect after portal

    Returns:
        Dict with portal URL
    """
    s = _get_stripe()
    response = s.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return {"portal_url": response.url}


def _get_price_id(plan_id: str) -> str:
    """Get Stripe price ID for plan."""
    settings = get_settings()

    price_map = {
        "job_seeker_monthly": settings.stripe_price_job_seeker_monthly,
        "recruiter_starter": settings.stripe_price_recruiter_starter,
        "recruiter_business": settings.stripe_price_recruiter_business,
        "recruiter_agency": settings.stripe_price_recruiter_agency,
    }

    if plan_id not in price_map:
        raise ValueError(f"Unknown plan: {plan_id}")

    return price_map[plan_id]
