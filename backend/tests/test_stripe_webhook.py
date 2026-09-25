"""Stripe webhook tests: signature verification, idempotency, side effects.

Scenarios covered:
- Valid signature -> 200 processed, event recorded with processed_at.
- Duplicate event -> already_processed, no double side effects.
- Invalid signature -> 400.
- checkout.session.completed -> subscription row active + current_period_end.
- customer.subscription.updated -> status/period updated.
- customer.subscription.deleted -> status canceled -> effective plan free.
- invoice.payment_failed -> status past_due + notification event row.

Signatures are computed with Stripe's documented v1 scheme
(HMAC-SHA256 of "{timestamp}.{payload}" with the webhook secret).
"""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from app.db.models import SecurityEvent, StripeWebhookEvent, Subscription, User
from app.services.tier_limits import get_user_plan

WEBHOOK_URL = "/api/v1/webhooks/stripe"
SECRET = "whsec_test"


# === Helpers ===


def _sign(payload: str, secret: str, timestamp: int) -> str:
    """Stripe v1 signature scheme: HMAC-SHA256(secret, "{ts}.{payload}")."""
    mac = hmac.new(secret.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256)
    return mac.hexdigest()


def _signed_event(
    event_id: str, event_type: str, data: dict, secret: str = SECRET
) -> tuple[bytes, dict[str, str]]:
    """Build a signed Stripe event (body bytes + Stripe-Signature header)."""
    body = json.dumps({"id": event_id, "type": event_type, "data": {"object": data}})
    timestamp = int(time.time())
    signature = _sign(body, secret, timestamp)
    return body.encode(), {"Stripe-Signature": f"t={timestamp},v1={signature}"}


async def _create_user(clean_db, email: str) -> User:
    """Create a User row in the test DB."""
    async with clean_db.session_factory() as session:
        user = User(
            email=email,
            password_hash="hashed",
            role="job_seeker",
            full_name="Webhook Tester",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _create_subscription(
    clean_db, user_id: int, *, plan: str, stripe_subscription_id: str
) -> Subscription:
    """Create an active subscription tied to a Stripe subscription id."""
    async with clean_db.session_factory() as session:
        sub = Subscription(
            user_id=user_id,
            plan=plan,
            status="active",
            stripe_subscription_id=stripe_subscription_id,
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return sub


def _to_utc(value: datetime) -> datetime:
    """Normalize a DB datetime to timezone-aware UTC for comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _get_subscription(clean_db, user_id: int) -> Subscription | None:
    """Fetch the user's subscription row."""
    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        return result.scalar_one_or_none()


# === Fixtures ===


@pytest.fixture
def webhook_secret(settings, monkeypatch):
    """Configure the webhook secret on the cached settings singleton."""
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)
    return SECRET


# === Signature + idempotency tests ===


async def test_webhook_valid_signature_200(
    async_client, clean_db, webhook_secret
):
    """Valid signature -> 200 processed + event recorded and marked processed."""
    body, headers = _signed_event("evt_ok_1", "invoice.paid", {"id": "in_ok_1"})

    response = await async_client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "processed"}

    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(StripeWebhookEvent).where(StripeWebhookEvent.event_id == "evt_ok_1")
        )
        row = result.scalar_one()
        assert row.type == "invoice.paid"
        assert row.processed_at is not None


async def test_webhook_duplicate_event_already_processed(
    async_client, clean_db, webhook_secret
):
    """Same event twice -> 2nd returns already_processed, no double side effects."""
    user = await _create_user(clean_db, "dup-event@test.com")
    data = {
        "metadata": {"user_id": str(user.id), "plan_id": "job_seeker_monthly"},
        "customer": "cus_dup_1",
        "subscription": "sub_dup_1",
    }
    body, headers = _signed_event("evt_dup_1", "checkout.session.completed", data)

    first = await async_client.post(WEBHOOK_URL, content=body, headers=headers)
    second = await async_client.post(WEBHOOK_URL, content=body, headers=headers)

    assert first.status_code == 200
    assert first.json() == {"status": "processed"}
    assert second.status_code == 200
    assert second.json() == {"status": "already_processed"}

    async with clean_db.session_factory() as session:
        subs = (await session.execute(select(Subscription))).scalars().all()
        assert len(subs) == 1, "checkout handler must run only once"

        events = (await session.execute(select(StripeWebhookEvent))).scalars().all()
        assert len(events) == 1
        assert events[0].processed_at is not None


async def test_webhook_invalid_signature_400(async_client, clean_db, webhook_secret):
    """Tampered v1 signature -> 400 Invalid signature."""
    body, _ = _signed_event("evt_bad_1", "invoice.paid", {"id": "in_bad_1"})
    bad_headers = {"Stripe-Signature": "t=1,v1=" + "0" * 64}

    response = await async_client.post(WEBHOOK_URL, content=body, headers=bad_headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid signature"


# === Event handler tests ===


async def test_checkout_completed_activates_subscription(
    async_client, clean_db, webhook_secret
):
    """checkout.session.completed -> subscription active + period end set."""
    user = await _create_user(clean_db, "checkout-done@test.com")
    data = {
        "metadata": {"user_id": str(user.id), "plan_id": "job_seeker_monthly"},
        "customer": "cus_new_1",
        "subscription": "sub_new_1",
    }
    body, headers = _signed_event("evt_cs_1", "checkout.session.completed", data)

    response = await async_client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == 200

    sub = await _get_subscription(clean_db, user.id)
    assert sub is not None
    assert sub.plan == "job_seeker_monthly"
    assert sub.status == "active"
    assert sub.stripe_customer_id == "cus_new_1"
    assert sub.stripe_subscription_id == "sub_new_1"
    assert sub.current_period_end is not None
    period_end = _to_utc(sub.current_period_end)
    assert period_end > datetime.now(UTC)
    assert period_end < datetime.now(UTC) + timedelta(days=31)


async def test_subscription_updated_changes_plan(
    async_client, clean_db, webhook_secret
):
    """customer.subscription.updated -> status + current period updated.

    Note: the task named this "changes_plan", but the handler updates
    status/period (not plan); plan changes arrive via checkout.session.completed.
    """
    user = await _create_user(clean_db, "sub-updated@test.com")
    await _create_subscription(
        clean_db,
        user.id,
        plan="job_seeker_monthly",
        stripe_subscription_id="sub_upd_1",
    )
    period_start = int(time.time())
    period_end = period_start + 30 * 24 * 3600
    data = {
        "id": "sub_upd_1",
        "status": "active",
        "current_period_start": period_start,
        "current_period_end": period_end,
    }
    body, headers = _signed_event("evt_sub_upd", "customer.subscription.updated", data)

    response = await async_client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == 200

    sub = await _get_subscription(clean_db, user.id)
    assert sub is not None
    assert sub.status == "active"
    expected_end = datetime.fromtimestamp(period_end, UTC)
    assert sub.current_period_end is not None
    assert abs((_to_utc(sub.current_period_end) - expected_end).total_seconds()) < 1


async def test_subscription_deleted_downgrades_to_free(
    async_client, clean_db, webhook_secret
):
    """customer.subscription.deleted -> canceled, effective plan becomes free."""
    user = await _create_user(clean_db, "sub-deleted@test.com")
    await _create_subscription(
        clean_db,
        user.id,
        plan="job_seeker_monthly",
        stripe_subscription_id="sub_del_1",
    )
    body, headers = _signed_event(
        "evt_sub_del", "customer.subscription.deleted", {"id": "sub_del_1"}
    )

    response = await async_client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == 200

    sub = await _get_subscription(clean_db, user.id)
    assert sub is not None
    assert sub.status == "canceled"

    async with clean_db.session_factory() as session:
        assert await get_user_plan(session, user.id) == "free"


async def test_payment_failed_past_due_and_notification(
    async_client, clean_db, webhook_secret
):
    """invoice.payment_failed -> status past_due + notification event row."""
    user = await _create_user(clean_db, "payment-failed@test.com")
    await _create_subscription(
        clean_db,
        user.id,
        plan="recruiter_starter",
        stripe_subscription_id="sub_pf_1",
    )
    data = {
        "id": "in_pf_1",
        "subscription": "sub_pf_1",
        "amount_due": 2900,
        "currency": "usd",
    }
    body, headers = _signed_event("evt_pf_1", "invoice.payment_failed", data)

    response = await async_client.post(WEBHOOK_URL, content=body, headers=headers)

    assert response.status_code == 200

    sub = await _get_subscription(clean_db, user.id)
    assert sub is not None
    assert sub.status == "past_due"

    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(SecurityEvent).where(SecurityEvent.user_id == user.id)
        )
        notification = result.scalar_one()
        assert notification.event == "payment_failed"
        assert notification.details["invoice_id"] == "in_pf_1"
        assert notification.details["amount_due"] == 2900
