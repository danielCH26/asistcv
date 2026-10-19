"""
BillingProvider adapter tests (slice 1, feat/pasarela-pagos-56).

Tests the BillingProvider ABC contract, the factory, and MockProvider.
No DB, no external HTTP, no Stripe SDK — fully self-contained.

These tests verify:
- MockProvider returns deterministic checkout URLs and session IDs.
- MockProvider.handle_webhook parses a JSON payload and returns a WebhookEvent.
- MockProvider.get_subscription_status returns SubStatus for known and unknown users.
- MockProvider.cancel_subscription is idempotent.
- Factory: get_billing_provider("mock") returns a MockProvider instance.
- Factory: get_billing_provider("stripe") without STRIPE_SECRET_KEY raises ProviderNotConfiguredError.
- Factory: unknown provider raises ValueError.
- ProviderNotConfiguredError is raised (not returned as a broken provider).
"""

import json

import pytest

from app.services.billing_provider import (
    _PROVIDER_CACHE,
    BillingProvider,
    CheckoutSession,
    CheckoutUrls,
    ProviderNotConfiguredError,
    SubStatus,
    WebhookEvent,
    get_billing_provider,
)

# === Fixtures ===

@pytest.fixture(autouse=True)
def clean_provider_cache():
    """Clear the provider cache before and after each test."""
    _PROVIDER_CACHE.clear()
    yield
    _PROVIDER_CACHE.clear()


@pytest.fixture
def mock_provider():
    """Return a fresh MockProvider instance."""
    from app.services.providers.mock import MockProvider

    return MockProvider()


# === MockProvider: create_checkout ===

@pytest.mark.asyncio
async def test_mock_provider_create_checkout_returns_url_and_session_id(mock_provider):
    """MockProvider.create_checkout returns a checkout URL and session_id."""
    plan = {"plan_id": "job_seeker_monthly", "tier": "job_seeker_monthly"}
    user = {"id": 42, "email": "test@example.com"}
    return_urls = CheckoutUrls(
        success_url="https://app.example.com/billing/success",
        cancel_url="https://app.example.com/billing/cancel",
    )

    result = await mock_provider.create_checkout(plan, user, return_urls)

    assert isinstance(result, CheckoutSession)
    assert result.provider_id == "mock"
    assert result.session_id.startswith("mock_cs_")
    assert "42" in result.session_id
    assert "job_seeker_monthly" in result.session_id
    assert result.checkout_url.startswith("https://checkout.mock/session")


@pytest.mark.asyncio
async def test_mock_provider_create_checkout_deterministic_per_user(mock_provider):
    """Two checkouts for the same user+plan share the prefix (stable for testing)."""
    plan = {"plan_id": "job_seeker_monthly", "tier": "job_seeker_monthly"}
    user = {"id": 99, "email": "alice@example.com"}
    urls = CheckoutUrls(success_url="https://app.example.com/ok", cancel_url="https://app.example.com/ko")

    result1 = await mock_provider.create_checkout(plan, user, urls)
    result2 = await mock_provider.create_checkout(plan, user, urls)

    assert result1.provider_id == result2.provider_id == "mock"
    assert "mock_cs_99" in result1.session_id
    assert "mock_cs_99" in result2.session_id


# === MockProvider: handle_webhook ===

@pytest.mark.asyncio
async def test_mock_provider_handle_webhook_subscription_created(mock_provider):
    """handle_webhook parses a subscription_created payload and returns a WebhookEvent."""
    payload = json.dumps({
        "event_type": "subscription_created",
        "user_id": 7,
        "plan_id": "recruiter_starter",
        "provider_id": "mock",
    }).encode("utf-8")

    result = await mock_provider.handle_webhook(payload, "somesig", {})

    assert isinstance(result, WebhookEvent)
    assert result.event_type == "subscription_created"
    assert result.user_id == 7
    assert result.plan_id == "recruiter_starter"
    assert result.provider_id == "mock"
    assert isinstance(result.raw, dict)


@pytest.mark.asyncio
async def test_mock_provider_handle_webhook_unknown_event(mock_provider):
    """handle_webhook returns raw dict in .raw for unrecognised event types."""
    payload = json.dumps({"event_type": "payment.succeeded", "amount": 900}).encode("utf-8")

    result = await mock_provider.handle_webhook(payload, "", {})

    assert result.event_type == "payment.succeeded"
    assert result.raw["amount"] == 900


@pytest.mark.asyncio
async def test_mock_provider_handle_webhook_invalid_json_raises(mock_provider):
    """handle_webhook raises ValueError when payload is not valid JSON."""
    with pytest.raises(ValueError, match="Invalid mock webhook payload"):
        await mock_provider.handle_webhook(b"not json", "", {})


# === MockProvider: get_subscription_status ===

@pytest.mark.asyncio
async def test_mock_provider_get_subscription_status_free_user(mock_provider):
    """Unknown user returns free-tier SubStatus."""
    result = await mock_provider.get_subscription_status(user_id=9999)

    assert isinstance(result, SubStatus)
    assert result.plan_id == "free"
    assert result.status == "active"
    assert result.current_period_end is None
    assert result.provider_customer_id is None
    assert result.provider_subscription_id is None
    assert result.cancel_at_period_end is False


@pytest.mark.asyncio
async def test_mock_provider_get_subscription_status_active_sub(mock_provider):
    """After a subscription_created webhook, get_subscription_status reflects it."""
    # Simulate a checkout completed webhook first
    payload = json.dumps({
        "event_type": "subscription_created",
        "user_id": 55,
        "plan_id": "job_seeker_monthly",
    }).encode("utf-8")
    await mock_provider.handle_webhook(payload, "", {})

    result = await mock_provider.get_subscription_status(user_id=55)

    assert result.plan_id == "job_seeker_monthly"
    assert result.status == "active"
    assert result.current_period_end is not None
    assert result.provider_customer_id == "mock_cus_55"
    assert result.provider_subscription_id == "mock_sub_55"
    assert result.cancel_at_period_end is False


# === MockProvider: cancel_subscription ===

@pytest.mark.asyncio
async def test_mock_provider_cancel_subscription_idempotent(mock_provider):
    """cancel_subscription is a no-op for an unknown user (idempotent)."""
    # Must not raise
    await mock_provider.cancel_subscription(user_id=12345)
    await mock_provider.cancel_subscription(user_id=12345)


@pytest.mark.asyncio
async def test_mock_provider_cancel_subscription_after_active(mock_provider):
    """After subscription_created + cancel, status is canceled."""
    # Create subscription
    payload = json.dumps({
        "event_type": "subscription_created",
        "user_id": 88,
        "plan_id": "recruiter_business",
    }).encode("utf-8")
    await mock_provider.handle_webhook(payload, "", {})

    await mock_provider.cancel_subscription(user_id=88)

    status = await mock_provider.get_subscription_status(user_id=88)
    assert status.status == "canceled"


# === MockProvider: supports_country ===

@pytest.mark.asyncio
async def test_mock_provider_supports_all_countries(mock_provider):
    """MockProvider supports every country."""
    assert mock_provider.supports_country("CO") is True
    assert mock_provider.supports_country("US") is True
    assert mock_provider.supports_country("XX") is True


# === Factory ===

def test_factory_returns_mock_provider():
    """get_billing_provider('mock') returns a MockProvider instance."""
    provider = get_billing_provider("mock")
    assert isinstance(provider, BillingProvider)
    assert provider.provider_id == "mock"


def test_factory_unknown_provider_raises_value_error():
    """Unknown provider_id raises ValueError."""
    with pytest.raises(ValueError, match="Unknown billing provider"):
        get_billing_provider("unknown_vendor")


def test_factory_stripe_without_key_raises_provider_not_configured():
    """get_billing_provider('stripe') without STRIPE_SECRET_KEY raises ProviderNotConfiguredError."""
    # ProviderNotConfiguredError, not a generic exception and NOT a broken
    # provider silently returned. This is the key contract: the factory
    # raises rather than returning a broken object.
    with pytest.raises(ProviderNotConfiguredError):
        get_billing_provider("stripe")


def test_factory_default_uses_billing_provider_active_setting(monkeypatch):
    """When provider_id is None, factory uses Settings.billing_provider_active (default mock)."""
    _PROVIDER_CACHE.clear()

    # Ensure BILLING_PROVIDER_ACTIVE is not set in the environment so the default kicks in
    monkeypatch.delenv("BILLING_PROVIDER_ACTIVE", raising=False)

    provider = get_billing_provider(None)
    assert provider.provider_id == "mock"


def test_factory_not_silent_on_missing_key():
    """Factory raises ProviderNotConfiguredError — it never returns a broken provider."""
    with pytest.raises(ProviderNotConfiguredError):
        get_billing_provider("stripe")

    # Also verify the cache was NOT populated (the error happened before caching)
    assert "stripe" not in _PROVIDER_CACHE


# === ABC contract: provider_id attribute ===

def test_mock_provider_has_provider_id():
    """MockProvider exposes provider_id as a class attribute."""
    from app.services.providers.mock import MockProvider

    assert hasattr(MockProvider, "provider_id")
    assert MockProvider.provider_id == "mock"


def test_factory_raises_not_returns():
    """The factory raises ProviderNotConfiguredError, never returns None or a broken object."""
    with pytest.raises(ProviderNotConfiguredError):
        get_billing_provider("stripe")

    # Unknown provider raises ValueError, not silent fallback
    with pytest.raises(ValueError):
        get_billing_provider("definitely_not_a_provider")
