"""
Lemon Squeezy webhook handler.

Processes LS webhooks with HMAC-SHA256 signature verification and
idempotency. Mirrors the pattern established by ``webhooks/stripe.py``.

Key design decisions (issue #56, slice 2):
- Event ID derivation: LS does not always include a stable top-level id.
  Primary: ``data.id`` (the subscription/order/item identifier). Fallback:
  ``hashlib.sha256(payload).hexdigest()``. The hash fallback is safe for
  deduplication because the same raw bytes always produce the same digest.
- Custom data passthrough: the checkout carries
  ``checkout_data.custom = {"user_id": ..., "plan_id": ...}`` (S2 spec).
  LS re-sends this in every ``meta.custom_data`` field of every webhook.
- Status mapping: LS uses ``on_trial`` / ``paused`` which our domain does
  not model. ``on_trial`` is treated as ``active`` (the user has paid
  access) and ``paused`` as ``past_due``.
"""
import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import and_, select

from app.db.models import PaymentMethod, PaymentWebhookEvent, Subscription
from app.db.session import get_session_context
from app.services.billing_provider import ProviderNotConfiguredError, get_billing_provider
from app.services.rls_context import set_rls_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

# LS event types that map to specific handlers.
_EVENT_SUBSCRIPTION_CREATED = "subscription_created"
_EVENT_SUBSCRIPTION_UPDATED = "subscription_updated"
_EVENT_SUBSCRIPTION_CANCELLED = "subscription_cancelled"
_EVENT_SUBSCRIPTION_EXPIRED = "subscription_expired"
_EVENT_SUBSCRIPTION_RESUMED = "subscription_resumed"
_EVENT_SUBSCRIPTION_PAYMENT_SUCCESS = "subscription_payment_success"


async def _handle_webhook_event(
    provider_id: str,
    payload: bytes,
    signature: str,
    headers: dict[str, str],
) -> dict:
    """Generic webhook event handler for any billing provider.

    This function handles webhook processing for Mercado Pago, Wompi,
    and other providers that follow the same pattern as Lemon Squeezy.

    Args:
        provider_id: The billing provider identifier (e.g., "mercadopago", "wompi")
        payload: Raw request body
        signature: Raw signature header value
        headers: All request headers

    Returns:
        Dict with status and event_type
    """
    from app.services.billing_provider import WebhookEvent

    # --- Provider / signature verification ---
    try:
        provider = get_billing_provider(provider_id)
    except ProviderNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail=f"{provider_id} webhook not configured",
        )
    except ValueError:
        raise HTTPException(
            status_code=503,
            detail=f"{provider_id} webhook not configured",
        )

    try:
        event: WebhookEvent = await provider.handle_webhook(payload, signature, headers)
    except ValueError:
        # Bad signature or unparseable JSON.
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    # --- Event ID derivation ---
    # Use hash of payload as fallback for providers without stable IDs
    body_dict: dict[str, Any] = event.raw
    data: dict[str, Any] = body_dict.get("data", {})
    transaction: dict[str, Any] = data.get("transaction", {})

    # Try various ID fields depending on provider
    event_id: str = (
        str(transaction.get("id"))
        or str(data.get("id"))
        or str(body_dict.get("id", ""))
        or ""
    )
    if not event_id:
        event_id = hashlib.sha256(payload).hexdigest()

    # --- Idempotency ---
    async with get_session_context() as session:
        await set_rls_service(session)
        result = await session.execute(
            select(PaymentWebhookEvent).where(
                and_(
                    PaymentWebhookEvent.provider == provider_id,
                    PaymentWebhookEvent.event_id == event_id,
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing and existing.processed_at:
            logger.info(f"{provider_id} webhook already processed: {event_id}")
            return {"status": "already_processed", "event_type": event.event_type}

        if not existing:
            webhook_event = PaymentWebhookEvent(
                provider=provider_id,
                event_id=event_id,
                type=event.event_type,
                payload_json=body_dict,
            )
            session.add(webhook_event)
            await session.commit()

    # --- Dispatch ---
    if event.user_id:
        await _dispatch(event)

    # --- Mark processed ---
    async with get_session_context() as session:
        await set_rls_service(session)
        result = await session.execute(
            select(PaymentWebhookEvent).where(
                and_(
                    PaymentWebhookEvent.provider == provider_id,
                    PaymentWebhookEvent.event_id == event_id,
                )
            )
        )
        record = result.scalar_one_or_none()
        if record:
            record.processed_at = datetime.now(UTC)
            await session.commit()

    return {"status": "processed", "event_type": event.event_type}


async def process_webhook(payload: bytes, signature: str | None) -> dict:
    """Process a Lemon Squeezy webhook event.

    Verifies HMAC signature, checks idempotency, dispatches to handlers,
    and marks the event processed.
    """
    # --- Provider / signature verification ---
    try:
        provider = get_billing_provider("lemon_squeezy")
    except ProviderNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail="LS webhook not configured",
        )
    except ValueError:
        raise HTTPException(
            status_code=503,
            detail="LS webhook not configured",
        )

    try:
        event = await provider.handle_webhook(payload, signature or "", {})
    except ValueError:
        # Bad HMAC or unparseable JSON.
        raise HTTPException(status_code=400, detail="Invalid signature")

    # --- Event ID derivation ---
    # LS webhooks carry no top-level event id. Deriving it from data.id is
    # WRONG: distinct events about the SAME subscription (created →
    # cancelled) share data.id and would collide in the idempotency ledger.
    # The SHA-256 of the raw payload is the correct key: an LS retry
    # delivers the exact same bytes (same hash → deduped), while any
    # different event produces a different payload (different hash →
    # processed).
    event_id: str = hashlib.sha256(payload).hexdigest()

    # --- Idempotency ---
    async with get_session_context() as session:
        await set_rls_service(session)
        result = await session.execute(
            select(PaymentWebhookEvent).where(
                and_(
                    PaymentWebhookEvent.provider == "lemon_squeezy",
                    PaymentWebhookEvent.event_id == event_id,
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing and existing.processed_at:
            logger.info(f"LS webhook already processed: {event_id}")
            return {"status": "already_processed"}

        if not existing:
            webhook_event = PaymentWebhookEvent(
                provider="lemon_squeezy",
                event_id=event_id,
                type=event.event_type,
                payload_json=body_dict,
            )
            session.add(webhook_event)
            await session.commit()

    # --- Dispatch ---
    if event.user_id:
        await _dispatch(event)

    # --- Mark processed ---
    async with get_session_context() as session:
        await set_rls_service(session)
        result = await session.execute(
            select(PaymentWebhookEvent).where(
                and_(
                    PaymentWebhookEvent.provider == "lemon_squeezy",
                    PaymentWebhookEvent.event_id == event_id,
                )
            )
        )
        record = result.scalar_one_or_none()
        if record:
            record.processed_at = datetime.now(UTC)
            await session.commit()

    return {"status": "processed"}


async def _dispatch(event) -> None:
    """Dispatch to the appropriate handler based on ``event.event_type``.

    This function handles events from any provider by normalizing event types
    to a common set that the handlers understand.
    """
    et = event.event_type

    # Normalize event types from different providers
    # Mercado Pago: subscription.activated, subscription.payment_failed, etc.
    # Wompi: payment.approved, payment.pending, etc.
    if et in (
        _EVENT_SUBSCRIPTION_CREATED,
        _EVENT_SUBSCRIPTION_UPDATED,
        "subscription.activated",
        "subscription.created",
        "payment.approved",
    ):
        await _handle_subscription_upsert(event)
    elif et in (
        _EVENT_SUBSCRIPTION_CANCELLED,
        _EVENT_SUBSCRIPTION_EXPIRED,
        "subscription.cancelled",
        "payment.voided",
        "payment.refunded",
    ):
        await _handle_subscription_cancelled(event)
    elif et == _EVENT_SUBSCRIPTION_RESUMED:
        await _handle_subscription_resumed(event)
    elif et in (_EVENT_SUBSCRIPTION_PAYMENT_SUCCESS, "payment.completed"):
        await _handle_payment_success(event)
    elif et in ("subscription.pending", "payment.pending"):
        # Log pending events but don't activate subscription yet
        logger.info(f"Pending payment event: {et} for user {event.user_id}")
    elif et in ("subscription.payment_failed", "payment.declined", "payment.rejected"):
        logger.warning(f"Payment failed: {et} for user {event.user_id}")
    else:
        logger.info(f"Unhandled webhook event: provider={event.provider}, type={et}")


async def _handle_subscription_upsert(event) -> None:
    """Handle subscription_created / subscription_updated.

    Upserts both ``Subscription`` and ``PaymentMethod`` rows for the user.
    ``on_trial`` is treated as ``active`` because the user has granted
    payment and has full access — only ``cancelled`` / ``expired`` / ``paused``
    represent a loss of entitlement.
    """
    if not event.user_id:
        return

    # Guard: only accept known plan IDs; skip unknown plans silently.
    if event.plan_id and event.plan_id not in Subscription.PLAN_TYPES:
        logger.warning(
            f"LS webhook: unknown plan_id={event.plan_id!r} for user {event.user_id}, skipping."
        )
        return

    data: dict[str, Any] = event.raw.get("data", {})
    attributes: dict[str, Any] = data.get("attributes", {})

    # Map LS status to our domain.
    ls_status: str = attributes.get("status", "")
    _status_map = {
        "active": "active",
        "on_trial": "active",  # Trial users have paid access.
        "cancelled": "canceled",
        "expired": "canceled",
        "paused": "past_due",
        "past_due": "past_due",
        "incomplete": "incomplete",
    }
    mapped_status = _status_map.get(ls_status, "active")

    # current_period_end: renews_at wins unless the sub is ending.
    renews_at_str: str | None = attributes.get("renews_at")
    ends_at_str: str | None = attributes.get("ends_at")
    period_end: datetime | None = None
    if ls_status in ("cancelled", "expired") and ends_at_str:
        try:
            period_end = datetime.fromisoformat(ends_at_str.replace("Z", "+00:00"))
        except ValueError:
            pass
    elif renews_at_str:
        try:
            period_end = datetime.fromisoformat(renews_at_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    plan_id = event.plan_id or "free"

    async with get_session_context() as session:
        await set_rls_service(session)

        # Upsert Subscription.
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == event.user_id)
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            sub = Subscription(user_id=event.user_id)
            session.add(sub)

        sub.plan = plan_id
        sub.status = mapped_status
        if period_end:
            sub.current_period_end = period_end

        # Upsert PaymentMethod.
        sub_id = str(data.get("id")) if data.get("id") else None
        customer_id = attributes.get("customer_id")

        if sub_id:
            result_pm = await session.execute(
                select(PaymentMethod).where(
                    PaymentMethod.provider_subscription_id == sub_id
                )
            )
            pm = result_pm.scalar_one_or_none()
            if pm is None:
                pm = PaymentMethod(
                    user_id=event.user_id,
                    provider="lemon_squeezy",
                    provider_subscription_id=sub_id,
                )
                session.add(pm)

            pm.status = mapped_status
            pm.plan_id = plan_id
            pm.current_period_end = period_end
            if customer_id:
                pm.provider_customer_id = str(customer_id)

        await session.commit()
        logger.info(
            f"LS upsert sub: user={event.user_id} plan={plan_id} status={mapped_status}"
        )


async def _handle_subscription_cancelled(event) -> None:
    """Handle subscription_cancelled / subscription_expired.

    Sets ``Subscription.status = "canceled"`` and
    ``PaymentMethod.status = "canceled"``.
    """
    if not event.user_id:
        return

    data: dict[str, Any] = event.raw.get("data", {})
    attributes: dict[str, Any] = data.get("attributes", {})
    ends_at_str: str | None = attributes.get("ends_at")
    period_end: datetime | None = None
    if ends_at_str:
        try:
            period_end = datetime.fromisoformat(ends_at_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    async with get_session_context() as session:
        await set_rls_service(session)

        result = await session.execute(
            select(Subscription).where(Subscription.user_id == event.user_id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            sub.status = "canceled"
            if period_end:
                sub.current_period_end = period_end

        sub_id = str(data.get("id")) if data.get("id") else None
        if sub_id:
            result_pm = await session.execute(
                select(PaymentMethod).where(
                    and_(
                        PaymentMethod.provider == "lemon_squeezy",
                        PaymentMethod.provider_subscription_id == sub_id,
                    )
                )
            )
            pm = result_pm.scalar_one_or_none()
            if pm:
                pm.status = "canceled"
                if period_end:
                    pm.current_period_end = period_end

        await session.commit()
        logger.info(f"LS canceled: user={event.user_id}")


async def _handle_subscription_resumed(event) -> None:
    """Handle subscription_resumed: restore active status on both rows."""
    if not event.user_id:
        return

    data: dict[str, Any] = event.raw.get("data", {})
    attributes: dict[str, Any] = data.get("attributes", {})
    renews_at_str: str | None = attributes.get("renews_at")
    period_end: datetime | None = None
    if renews_at_str:
        try:
            period_end = datetime.fromisoformat(renews_at_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    async with get_session_context() as session:
        await set_rls_service(session)

        result = await session.execute(
            select(Subscription).where(Subscription.user_id == event.user_id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            sub.status = "active"
            if period_end:
                sub.current_period_end = period_end

        sub_id = str(data.get("id")) if data.get("id") else None
        if sub_id:
            result_pm = await session.execute(
                select(PaymentMethod).where(
                    and_(
                        PaymentMethod.provider == "lemon_squeezy",
                        PaymentMethod.provider_subscription_id == sub_id,
                    )
                )
            )
            pm = result_pm.scalar_one_or_none()
            if pm:
                pm.status = "active"
                if period_end:
                    pm.current_period_end = period_end

        await session.commit()
        logger.info(f"LS resumed: user={event.user_id}")


async def _handle_payment_success(event) -> None:
    """Handle subscription_payment_success: refresh current_period_end."""
    if not event.user_id:
        return

    data: dict[str, Any] = event.raw.get("data", {})
    attributes: dict[str, Any] = data.get("attributes", {})
    renews_at_str: str | None = attributes.get("renews_at")
    period_end: datetime | None = None
    if renews_at_str:
        try:
            period_end = datetime.fromisoformat(renews_at_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    if not period_end:
        return

    async with get_session_context() as session:
        await set_rls_service(session)

        result = await session.execute(
            select(Subscription).where(Subscription.user_id == event.user_id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            sub.current_period_end = period_end

        sub_id = str(data.get("id")) if data.get("id") else None
        if sub_id:
            result_pm = await session.execute(
                select(PaymentMethod).where(
                    and_(
                        PaymentMethod.provider == "lemon_squeezy",
                        PaymentMethod.provider_subscription_id == sub_id,
                    )
                )
            )
            pm = result_pm.scalar_one_or_none()
            if pm:
                pm.current_period_end = period_end

        await session.commit()
        logger.info(f"LS payment success: user={event.user_id}, period_end refreshed")


@router.post("/lemonsqueezy")
async def ls_webhook(request: Request):
    """Lemon Squeezy webhook endpoint.

    Reads raw body BEFORE any parsing for HMAC verification.
    The signature header name comes from ``settings.lemon_squeezy_signature_header``
    (default ``X-Signature``).
    """
    from app.core.config import get_settings

    payload = await request.body()
    settings = get_settings()
    sig_header = request.headers.get(settings.lemon_squeezy_signature_header)

    return await process_webhook(payload, sig_header)
