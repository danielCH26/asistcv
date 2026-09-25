"""
Stripe webhook handler.

Processes Stripe webhooks with signature verification and idempotency.
"""
import logging
from datetime import UTC, datetime

import stripe
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import StripeWebhookEvent, Subscription
from app.db.session import get_session_context
from app.services.rls_context import set_rls_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


async def process_webhook(payload: bytes, sig_header: str | None) -> dict:
    """Process a Stripe webhook event.

    Verifies signature, checks idempotency, and dispatches to handlers.
    """
    settings = get_settings()

    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Stripe webhook not configured")

    # Verify signature
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # stripe-python >= 15 returns a StripeObject: no dict methods (.get) and
    # not JSON-serializable. Convert to a plain dict immediately after parsing.
    event_dict = event.to_dict()

    # Check idempotency - don't process same event twice
    async with get_session_context() as session:
        await set_rls_service(session)
        result = await session.execute(
            select(StripeWebhookEvent).where(
                StripeWebhookEvent.event_id == event_dict["id"]
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            if existing.processed_at:
                logger.info(f"Webhook already processed: {event_dict['id']}")
                logger.info(f"webhook_dedup: {event_dict['id']}")
                return {"status": "already_processed"}
            # Event exists but not processed - continue processing

        # Record event for idempotency
        if not existing:
            webhook_event = StripeWebhookEvent(
                event_id=event_dict["id"],
                type=event_dict["type"],
                payload_json=event_dict.get("data", {}).get("object", {}),
            )
            session.add(webhook_event)
            await session.commit()

    # Process event
    await _handle_event(event_dict)

    # Mark as processed
    async with get_session_context() as session:
        await set_rls_service(session)
        result = await session.execute(
            select(StripeWebhookEvent).where(
                StripeWebhookEvent.event_id == event_dict["id"]
            )
        )
        webhook_event = result.scalar_one()
        webhook_event.processed_at = datetime.now(UTC)
        await session.commit()

    return {"status": "processed"}


async def _handle_event(event: dict) -> None:
    """Handle a Stripe event based on its type."""
    event_type = event["type"]
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data)
    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(data)
    else:
        logger.info(f"Unhandled event type: {event_type}")


async def _handle_checkout_completed(data: dict) -> None:
    """Handle checkout.session.completed event."""
    from app.db.session import get_session_context

    # Extract metadata
    user_id = data.get("metadata", {}).get("user_id")
    plan_id = data.get("metadata", {}).get("plan_id")
    customer_id = data.get("customer")
    subscription_id = data.get("subscription")

    if not user_id or not plan_id:
        logger.error(f"Missing metadata in checkout event: {data}")
        return

    async with get_session_context() as session:
        await set_rls_service(session)
        # Find or create subscription
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == int(user_id))
        )
        sub = result.scalar_one_or_none()

        if sub is None:
            sub = Subscription(user_id=int(user_id))
            session.add(sub)

        # Update subscription
        sub.plan = plan_id
        sub.status = "active"
        sub.stripe_customer_id = customer_id
        sub.stripe_subscription_id = subscription_id
        sub.current_period_start = datetime.now(UTC)

        # Set current_period_end: try to get from subscription details,
        # fallback to 30 days from now if not available
        subscription_details = data.get("subscription_details", {})
        if subscription_details:
            period_end = subscription_details.get("subscription", {}).get("current_period_end")
            if period_end:
                sub.current_period_end = datetime.fromtimestamp(period_end, UTC)
            else:
                # Default: 30 days from now if not provided by Stripe
                from datetime import timedelta
                sub.current_period_end = datetime.now(UTC) + timedelta(days=30)
        else:
            # Default: 30 days from now if subscription_details not available
            from datetime import timedelta
            sub.current_period_end = datetime.now(UTC) + timedelta(days=30)

        await session.commit()

        logger.info(f"Subscription created for user {user_id}: {plan_id}")


async def _handle_subscription_deleted(data: dict) -> None:
    """Handle customer.subscription.deleted event."""
    from app.db.session import get_session_context

    subscription_id = data.get("id")

    async with get_session_context() as session:
        await set_rls_service(session)
        result = await session.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == subscription_id
            )
        )
        sub = result.scalar_one_or_none()

        if sub:
            sub.status = "canceled"
            await session.commit()
            logger.info(f"Subscription canceled: {subscription_id}")


async def _handle_subscription_updated(data: dict) -> None:
    """Handle customer.subscription.updated event."""
    from app.db.session import get_session_context

    subscription_id = data.get("id")
    current_period_start = data.get("current_period_start")
    current_period_end = data.get("current_period_end")
    status = data.get("status")

    async with get_session_context() as session:
        await set_rls_service(session)
        result = await session.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == subscription_id
            )
        )
        sub = result.scalar_one_or_none()

        if sub:
            if current_period_start:
                sub.current_period_start = datetime.fromtimestamp(current_period_start, UTC)
            if current_period_end:
                sub.current_period_end = datetime.fromtimestamp(current_period_end, UTC)
            if status:
                sub.status = status
            await session.commit()
            logger.info(f"Subscription updated: {subscription_id}")


async def _handle_payment_failed(data: dict) -> None:
    """Handle invoice.payment_failed event."""
    from app.db.models import SecurityEvent
    from app.db.session import get_session_context

    subscription_id = data.get("subscription")

    if not subscription_id:
        return

    async with get_session_context() as session:
        await set_rls_service(session)
        result = await session.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == subscription_id
            )
        )
        sub = result.scalar_one_or_none()

        if sub:
            sub.status = "past_due"
            await session.commit()
            logger.info(f"Subscription marked past_due: {subscription_id}")

            # Record notification event for the user
            notification = SecurityEvent(
                event="payment_failed",
                user_id=sub.user_id,
                details={
                    "subscription_id": subscription_id,
                    "invoice_id": data.get("id"),
                    "amount_due": data.get("amount_due"),
                    "currency": data.get("currency"),
                    "message": "Payment failed. Please update your payment method to avoid service interruption.",
                },
            )
            session.add(notification)
            await session.commit()
            logger.info(f"Payment failure notification recorded for user {sub.user_id}")


@router.post("/stripe")
async def stripe_webhook(request: Request):
    """Stripe webhook endpoint.

    IMPORTANT: This endpoint reads raw body BEFORE any parsing.
    """
    # Get raw body for signature verification
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    result = await process_webhook(payload, sig_header)
    return result
