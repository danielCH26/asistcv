"""
Billing provider adapter layer.

Defines the ``BillingProvider`` ABC (the Adapter pattern from the ODD),
shared types, and a factory that resolves ``provider_id`` → concrete instance.

Slice 1 (feat/pasarela-pagos-56) delivers:
- BillingProvider ABC + 5 concrete methods
- Types: CheckoutUrls, CheckoutSession, WebhookEvent, SubStatus
- ProviderNotConfiguredError
- get_billing_provider() factory
- MockProvider (in-memory, no DB, no secrets)
- StripeProvider (wraps stripe_client.py; STRIPE_SECRET_KEY absent → error)
- LemonSqueezyProvider stub (slice 2)
- MercadoPagoProvider stub (slice 3)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from app.core.config import get_settings

# === Shared types ===

_PROVIDER_IDS = frozenset({"mock", "stripe", "lemon_squeezy", "mercadopago"})


@dataclass(frozen=True, slots=True)
class CheckoutUrls:
    """Return URLs for a checkout session."""

    success_url: str
    cancel_url: str


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    """Result of ``BillingProvider.create_checkout``."""

    checkout_url: str
    session_id: str
    provider_id: str


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    """Normalized webhook event returned by ``BillingProvider.handle_webhook``."""

    event_type: str
    user_id: int | None
    plan_id: str | None
    provider_id: str
    raw: dict


@dataclass(frozen=True, slots=True)
class SubStatus:
    """Normalized subscription status from a provider."""

    plan_id: str
    status: str
    current_period_end: datetime | None
    provider_customer_id: str | None
    provider_subscription_id: str | None
    cancel_at_period_end: bool


# === Error types ===

_STRIPE_ERR_CODE = "BILLING_ERROR"
_UNCONFIGURED_CODE = "PAYMENT_PROVIDER_UNCONFIGURED"


class ProviderNotConfiguredError(Exception):
    """Raised when ``get_billing_provider`` is called for a provider whose
    required env vars are not set.

    Consumers map this to HTTP 503 ``PAYMENT_PROVIDER_UNCONFIGURED``.
    """

    pass


# === BillingProvider ABC ===

VALID_PROVIDER_IDS: frozenset[str] = _PROVIDER_IDS
"""All provider IDs known to the factory."""


class BillingProvider(ABC):
    """Abstract contract for a billing gateway.

    Every concrete provider must expose ``provider_id`` as a class attribute
    and implement the five methods below. The factory vends instances based
    on ``BILLING_PROVIDER_ACTIVE`` (or an explicit ``provider_id`` passed
    to the endpoint).
    """

    provider_id: ClassVar[str]

    @abstractmethod
    async def create_checkout(
        self,
        plan: dict,
        user: dict,
        return_urls: CheckoutUrls,
        *,
        idempotency_key: str | None = None,
    ) -> CheckoutSession:
        """Create a hosted checkout session.

        Args:
            plan: Plan dict from ``PLANS_CATALOG``.
            user: Dict with at least ``id`` and ``email``.
            return_urls: Success/cancel redirect URLs.
            idempotency_key: Caller-supplied dedupe token (e.g. from a client
                Idempotency-Key header). Providers that support it pass it
                through to the underlying API; others ignore it.

        Returns:
            CheckoutSession with the hosted checkout URL.

        Raises:
            ProviderNotConfiguredError: Required env vars are not set.
            ValueError: Plan or other business-logic error.
        """
        ...

    @abstractmethod
    async def handle_webhook(
        self,
        payload: bytes,
        signature: str,
        headers: dict[str, str],
    ) -> WebhookEvent:
        """Verify a webhook payload and return a normalized event.

        Signature verification is provider-specific (Stripe header,
        LS HMAC-SHA256, etc.) and happens inside this method.

        Args:
            payload: Raw request body.
            signature: Raw signature header value.
            headers: All request headers for provider-specific lookups.

        Returns:
            Normalized ``WebhookEvent``.

        Raises:
            ProviderNotConfiguredError: Webhook secret not set.
            ValueError / provider SDK error: Invalid payload or signature.
        """
        ...

    @abstractmethod
    async def get_subscription_status(self, user_id: int) -> SubStatus:
        """Fetch the active subscription status for a user from the provider.

        Args:
            user_id: Application user ID.

        Returns:
            SubStatus for the user's active subscription (or a "no sub" state).

        Raises:
            ProviderNotConfiguredError: Provider credentials not set.
        """
        ...

    @abstractmethod
    async def cancel_subscription(self, user_id: int) -> None:
        """Cancel the active subscription for a user.

        Idempotent: calling on an already-canceled subscription is a no-op.

        Args:
            user_id: Application user ID.

        Raises:
            ProviderNotConfiguredError: Provider credentials not set.
        """
        ...

    @abstractmethod
    def supports_country(self, country_code: str) -> bool:
        """Whether this provider can process payments for the given country.

        Used by the frontend to show/hide provider buttons based on the user's
        detected or selected country.

        Args:
            country_code: ISO 3166-1 alpha-2 country code (e.g. "CO", "US").

        Returns:
            True if the provider supports the country.
        """
        ...


# === Factory ===

_PROVIDER_CACHE: dict[str, BillingProvider] = {}


def _build_provider(provider_id: str) -> BillingProvider:
    """Instantiate the concrete provider for ``provider_id``."""
    if provider_id == "mock":
        from app.services.providers.mock import MockProvider

        return MockProvider()

    if provider_id == "stripe":
        from app.services.providers.stripe import StripeProvider

        return StripeProvider()

    if provider_id == "lemon_squeezy":
        from app.services.providers.lemon_squeezy import LemonSqueezyProvider

        return LemonSqueezyProvider()

    if provider_id == "mercadopago":
        from app.services.providers.mercadopago import MercadoPagoProvider

        return MercadoPagoProvider()

    raise ValueError(f"Unknown billing provider: {provider_id!r}")


def get_billing_provider(provider_id: str | None = None) -> BillingProvider:
    """Resolve ``provider_id`` to a ``BillingProvider`` instance.

    When ``provider_id`` is None the active provider from ``Settings`` is used.
    Instances are cached per process so the config is read once.

    Raises:
        ProviderNotConfiguredError: The resolved provider's required env vars
            are not set (e.g. ``STRIPE_SECRET_KEY`` for the Stripe provider).
        ValueError: ``provider_id`` is not a known provider name.
    """
    settings = get_settings()
    effective_id = (provider_id or settings.billing_provider_active).strip().lower()

    if not effective_id:
        raise ProviderNotConfiguredError(
            "BILLING_PROVIDER_ACTIVE is empty; no billing provider is configured."
        )

    if effective_id not in _PROVIDER_IDS:
        raise ValueError(
            f"Unknown billing provider: {effective_id!r}. "
            f"Known providers: {sorted(_PROVIDER_IDS)}"
        )

    if effective_id not in _PROVIDER_CACHE:
        _PROVIDER_CACHE[effective_id] = _build_provider(effective_id)

    return _PROVIDER_CACHE[effective_id]
