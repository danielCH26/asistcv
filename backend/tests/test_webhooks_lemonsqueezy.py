"""
LS webhook tests: signature verification, idempotency, side effects.

Fixtures mirror the stripe_webhook.py test patterns:
- Valid signature -> 200 + Subscription + PaymentMethod rows.
- Duplicate event -> already_processed (no double write).
- Invalid signature -> 400.
- subscription_cancelled -> both rows canceled.
- Unknown plan_id -> 200, no Subscription/PaymentMethod rows created.

Signatures are computed with HMAC-SHA256 (LS's documented scheme).
Settings are patched on the cached singleton via monkeypatch.setattr,
NEVER via env vars (slice 1 lesson: Settings is @lru_cache'd).
"""

import hashlib
import hmac
import json

import pytest
from sqlmodel import select

from app.db.models import PaymentMethod, Subscription, User

WEBHOOK_URL = "/api/v1/webhooks/lemonsqueezy"


# === Helpers ===


def _sign(payload: bytes, secret: str) -> str:
    """HMAC-SHA256 signature: LS uses raw payload (no timestamp prefix)."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _ls_payload(
    event_name: str,
    *,
    user_id: int = 72,
    plan_id: str = "job_seeker_monthly",
    sub_id: str = "sub_123",
    status: str = "active",
    renews_at: str = "2026-12-01T00:00:00Z",
    ends_at: str | None = None,
    customer_id: int = 1001,
) -> bytes:
    """Build a minimal LS webhook payload matching the documented shape."""
    attrs: dict = {
        "status": status,
        "renews_at": renews_at,
        "customer_id": customer_id,
    }
    if ends_at:
        attrs["ends_at"] = ends_at
    body = {
        "meta": {
            "event_name": event_name,
            "custom_data": {
                "user_id": str(user_id),
                "plan_id": plan_id,
            },
        },
        "data": {
            "id": sub_id,
            "attributes": attrs,
        },
    }
    return json.dumps(body).encode()


# === Fixtures ===


@pytest.fixture
def ls_settings(settings, monkeypatch):
    """Configure LS webhook settings on the cached settings singleton."""
    monkeypatch.setattr(settings, "billing_provider_active", "lemon_squeezy")
    monkeypatch.setattr(settings, "lemon_squeezy_api_key", "test-key")
    monkeypatch.setattr(settings, "lemon_squeezy_store_id", "1")
    monkeypatch.setattr(settings, "lemon_squeezy_webhook_secret", "test-secret")
    monkeypatch.setattr(settings, "lemon_squeezy_signature_header", "X-Signature")
    monkeypatch.setattr(settings, "lemon_squeezy_test_mode", True)
    # Variant stubs (required by LS provider construction).
    monkeypatch.setattr(settings, "lemon_squeezy_variant_job_seeker_monthly", "var_test_js")
    monkeypatch.setattr(settings, "lemon_squeezy_variant_recruiter_starter", "var_test_rs")
    monkeypatch.setattr(settings, "lemon_squeezy_variant_recruiter_business", "var_test_rb")
    monkeypatch.setattr(settings, "lemon_squeezy_variant_recruiter_agency", "var_test_ra")


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


async def _get_subscription(clean_db, user_id: int) -> Subscription | None:
    """Fetch the user's subscription row."""
    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def _get_payment_method(clean_db, user_id: int) -> PaymentMethod | None:
    """Fetch the user's LS payment method row."""
    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(PaymentMethod).where(
                PaymentMethod.user_id == user_id,
                PaymentMethod.provider == "lemon_squeezy",
            )
        )
        return result.scalar_one_or_none()


# === Signature + idempotency tests ===


async def test_webhook_valid_signature_200(
    async_client, clean_db, ls_settings
):
    """Valid HMAC -> 200 processed + Subscription row + PaymentMethod row."""
    user = await _create_user(clean_db, "ls-ok@test.com")
    payload = _ls_payload("subscription_created", user_id=user.id)
    sig = _sign(payload, "test-secret")

    response = await async_client.post(
        WEBHOOK_URL,
        content=payload,
        headers={"X-Signature": sig},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "processed"}

    sub = await _get_subscription(clean_db, user.id)
    assert sub is not None
    assert sub.plan == "job_seeker_monthly"
    assert sub.status == "active"

    pm = await _get_payment_method(clean_db, user.id)
    assert pm is not None
    assert pm.provider == "lemon_squeezy"
    assert pm.provider_subscription_id == "sub_123"
    assert pm.status == "active"
    assert pm.plan_id == "job_seeker_monthly"


async def test_webhook_duplicate_already_processed(
    async_client, clean_db, ls_settings
):
    """Same payload twice -> second returns already_processed, only ONE row write."""
    user = await _create_user(clean_db, "ls-dup@test.com")
    payload = _ls_payload("subscription_created", user_id=user.id)
    sig = _sign(payload, "test-secret")

    first = await async_client.post(
        WEBHOOK_URL,
        content=payload,
        headers={"X-Signature": sig},
    )
    second = await async_client.post(
        WEBHOOK_URL,
        content=payload,
        headers={"X-Signature": sig},
    )

    assert first.status_code == 200
    assert first.json() == {"status": "processed"}
    assert second.status_code == 200
    assert second.json() == {"status": "already_processed"}

    async with clean_db.session_factory() as session:
        subs = (await session.execute(select(Subscription))).scalars().all()
        assert len(subs) == 1, "handler must run subscription upsert only once"

        pmes = (await session.execute(select(PaymentMethod))).scalars().all()
        assert len(pmes) == 1, "PaymentMethod upsert must run only once"


async def test_webhook_invalid_signature_400(
    async_client, clean_db, ls_settings
):
    """Tampered signature -> 400 Invalid signature."""
    payload = _ls_payload("subscription_created")
    bad_sig = _sign(payload, "wrong-secret")[:-1] + "0"  # alter last char

    response = await async_client.post(
        WEBHOOK_URL,
        content=payload,
        headers={"X-Signature": bad_sig},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid signature"


async def test_webhook_cancelled_event(
    async_client, clean_db, ls_settings
):
    """subscription_cancelled -> Subscription.status=canceled, PaymentMethod.status=canceled."""
    user = await _create_user(clean_db, "ls-cancel@test.com")

    # Pre-create active rows via subscription_created first.
    create_payload = _ls_payload(
        "subscription_created",
        user_id=user.id,
        status="active",
        renews_at="2026-12-01T00:00:00Z",
    )
    sig = _sign(create_payload, "test-secret")
    await async_client.post(
        WEBHOOK_URL,
        content=create_payload,
        headers={"X-Signature": sig},
    )

    # Now send the cancel event.
    cancel_payload = _ls_payload(
        "subscription_cancelled",
        user_id=user.id,
        status="cancelled",
        ends_at="2026-12-01T00:00:00Z",
    )
    cancel_sig = _sign(cancel_payload, "test-secret")
    cancel_resp = await async_client.post(
        WEBHOOK_URL,
        content=cancel_payload,
        headers={"X-Signature": cancel_sig},
    )

    assert cancel_resp.status_code == 200
    assert cancel_resp.json() == {"status": "processed"}

    sub = await _get_subscription(clean_db, user.id)
    assert sub is not None
    assert sub.status == "canceled"

    pm = await _get_payment_method(clean_db, user.id)
    assert pm is not None
    assert pm.status == "canceled"


async def test_webhook_unknown_plan_skips(
    async_client, clean_db, ls_settings
):
    """Unknown plan_id in custom_data -> 200 but no Subscription/PaymentMethod row created."""
    user = await _create_user(clean_db, "ls-unknown-plan@test.com")
    payload = _ls_payload(
        "subscription_created",
        user_id=user.id,
        plan_id="nonexistent_plan_xyz",
    )
    sig = _sign(payload, "test-secret")

    response = await async_client.post(
        WEBHOOK_URL,
        content=payload,
        headers={"X-Signature": sig},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "processed"}

    sub = await _get_subscription(clean_db, user.id)
    assert sub is None, "unknown plan must not create a Subscription row"

    pm = await _get_payment_method(clean_db, user.id)
    assert pm is None, "unknown plan must not create a PaymentMethod row"
