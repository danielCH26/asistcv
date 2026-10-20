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

import hashlib
import hmac
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
    """Clear the provider cache and settings cache before and after each test."""
    _PROVIDER_CACHE.clear()
    yield
    _PROVIDER_CACHE.clear()
    # Clear the lru_cache on get_settings so tests can patch fresh instances
    try:
        from app.core.config import get_settings
        get_settings.cache_clear()
    except Exception:
        pass


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


# === Lemon Squeezy factory and config tests ===

def test_factory_lemon_squeezy_without_api_key_raises(monkeypatch):
    """get_billing_provider('lemon_squeezy') without LEMON_SQUEEZY_API_KEY raises."""
    from app.core.config import get_settings

    _PROVIDER_CACHE.clear()
    # Clear lru_cache so we get fresh settings with patched attrs
    get_settings.cache_clear()
    s = get_settings()

    monkeypatch.setattr(s, "lemon_squeezy_api_key", None)
    monkeypatch.setattr(s, "lemon_squeezy_store_id", "store_1")
    monkeypatch.setattr(s, "billing_provider_active", "lemon_squeezy")

    with pytest.raises(ProviderNotConfiguredError, match="LEMON_SQUEEZY_API_KEY"):
        get_billing_provider("lemon_squeezy")


def test_factory_lemon_squeezy_without_store_id_raises(monkeypatch):
    """get_billing_provider('lemon_squeezy') without LEMON_SQUEEZY_STORE_ID raises."""
    from app.core.config import get_settings

    _PROVIDER_CACHE.clear()
    get_settings.cache_clear()
    s = get_settings()

    monkeypatch.setattr(s, "lemon_squeezy_api_key", "key_abc")
    monkeypatch.setattr(s, "lemon_squeezy_store_id", None)
    monkeypatch.setattr(s, "billing_provider_active", "lemon_squeezy")

    with pytest.raises(ProviderNotConfiguredError, match="LEMON_SQUEEZY_STORE_ID"):
        get_billing_provider("lemon_squeezy")


def test_factory_lemon_squeezy_resolves_with_config(monkeypatch):
    """With api_key + store_id configured, factory returns a LemonSqueezyProvider."""
    from app.core.config import get_settings
    from app.services.providers.lemon_squeezy import LemonSqueezyProvider

    _PROVIDER_CACHE.clear()
    get_settings.cache_clear()
    s = get_settings()

    monkeypatch.setattr(s, "lemon_squeezy_api_key", "key_abc")
    monkeypatch.setattr(s, "lemon_squeezy_store_id", "store_1")
    monkeypatch.setattr(s, "billing_provider_active", "lemon_squeezy")

    provider = get_billing_provider("lemon_squeezy")
    assert isinstance(provider, LemonSqueezyProvider)
    assert provider.provider_id == "lemon_squeezy"


# === Lemon Squeezy webhook signature tests ===

def _ls_webhook_payload(event_name: str, user_id: str, plan_id: str) -> bytes:
    """Return a synthetic LS webhook payload as bytes."""
    return json.dumps({
        "meta": {
            "event_name": event_name,
            "custom_data": {
                "user_id": user_id,
                "plan_id": plan_id,
            },
        },
        "data": {
            "id": "evt_abc",
            "attributes": {"status": "active"},
        },
    }).encode("utf-8")


def _ls_webhook_signature(payload: bytes, secret: str) -> str:
    """Compute the HMAC-SHA256 hexdigest for a payload with the given secret."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.fixture
def ls_provider_with_secret(monkeypatch):
    """Return a LemonSqueezyProvider with all required settings patched."""
    from app.core.config import get_settings

    _PROVIDER_CACHE.clear()
    get_settings.cache_clear()
    s = get_settings()

    monkeypatch.setattr(s, "lemon_squeezy_api_key", "test_key")
    monkeypatch.setattr(s, "lemon_squeezy_store_id", "store_1")
    monkeypatch.setattr(s, "lemon_squeezy_webhook_secret", "webhook_secret_abc")
    monkeypatch.setattr(s, "lemon_squeezy_signature_header", "X-Signature")
    monkeypatch.setattr(s, "billing_provider_active", "lemon_squeezy")

    return get_billing_provider("lemon_squeezy")


@pytest.mark.asyncio
async def test_ls_webhook_signature_valid(ls_provider_with_secret):
    """Valid HMAC-SHA256 signature returns a correct WebhookEvent."""
    payload = _ls_webhook_payload("subscription_created", "72", "job_seeker_monthly")
    sig = _ls_webhook_signature(payload, "webhook_secret_abc")

    result = await ls_provider_with_secret.handle_webhook(payload, sig, {})

    assert isinstance(result, WebhookEvent)
    assert result.event_type == "subscription_created"
    assert result.user_id == 72
    assert result.plan_id == "job_seeker_monthly"
    assert result.provider_id == "lemon_squeezy"
    assert result.raw["meta"]["custom_data"]["user_id"] == "72"


@pytest.mark.asyncio
async def test_ls_webhook_signature_invalid(ls_provider_with_secret):
    """Wrong HMAC signature raises ValueError('Invalid signature')."""
    payload = _ls_webhook_payload("subscription_created", "1", "job_seeker_monthly")
    wrong_sig = "not_a_valid_signature_at_all_xxxxxxxxxxxxxxxxxx"

    with pytest.raises(ValueError, match="Invalid signature"):
        await ls_provider_with_secret.handle_webhook(payload, wrong_sig, {})


@pytest.mark.asyncio
async def test_ls_webhook_missing_secret_raises(monkeypatch):
    """handle_webhook raises ProviderNotConfiguredError when webhook secret is not set."""
    from app.core.config import get_settings

    _PROVIDER_CACHE.clear()
    get_settings.cache_clear()
    s = get_settings()

    monkeypatch.setattr(s, "lemon_squeezy_api_key", "test_key")
    monkeypatch.setattr(s, "lemon_squeezy_store_id", "store_1")
    monkeypatch.setattr(s, "lemon_squeezy_webhook_secret", None)
    monkeypatch.setattr(s, "billing_provider_active", "lemon_squeezy")

    provider = get_billing_provider("lemon_squeezy")

    with pytest.raises(ProviderNotConfiguredError, match="LEMON_SQUEEZY_WEBHOOK_SECRET"):
        await provider.handle_webhook(b'{"meta":{"event_name":"test"}}', "sig", {})


@pytest.mark.asyncio
async def test_ls_webhook_invalid_json(ls_provider_with_secret):
    """Valid signature over garbage bytes raises ValueError('Invalid payload')."""
    garbage_payload = b'not valid json at all {"broken":'
    sig = _ls_webhook_signature(garbage_payload, "webhook_secret_abc")

    with pytest.raises(ValueError, match="Invalid payload"):
        await ls_provider_with_secret.handle_webhook(garbage_payload, sig, {})


@pytest.mark.asyncio
async def test_ls_webhook_signature_from_headers_fallback(ls_provider_with_secret):
    """When explicit signature is empty, provider reads from headers dict case-insensitively."""
    payload = _ls_webhook_payload("subscription_updated", "99", "recruiter_business")
    sig = _ls_webhook_signature(payload, "webhook_secret_abc")

    # Pass empty string as the explicit signature, but provide it in headers
    result = await ls_provider_with_secret.handle_webhook(
        payload,
        "",  # empty explicit signature
        {"x-signature": sig},  # lowercase header (case-insensitive match)
    )

    assert result.event_type == "subscription_updated"
    assert result.user_id == 99
    assert result.plan_id == "recruiter_business"
