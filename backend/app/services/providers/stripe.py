"""
Stripe billing provider.

Wraps the existing ``stripe_client`` module (kept as a thin shim) and adds
the ``BillingProvider`` interface contract. ``STRIPE_SECRET_KEY`` absent →
``ProviderNotConfiguredError`` at construction time, propagated by the factory.

Architectural decision (constraint #8 of the ODD):
  ``stripe_client.py`` is kept as-is (3 sync functions) and imported from
  inside this provider's methods. No inlining — the existing module is
  tested and stable; wrapping it preserves those guarantees.

Slice 1 — feat/pasarela-pagos-56.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import stripe

from app.services.billing_provider import (
    BillingProvider,
    CheckoutSession,
    CheckoutUrls,
    ProviderNotConfiguredError,
    SubStatus,
    WebhookEvent,
)

if TYPE_CHECKING:
    from app.core.config import Settings


class StripeProvider(BillingProvider):
    """Stripe-backed billing provider, conforming to the BillingProvider ABC."""

    provider_id: ClassVar[str] = "stripe"

    def __init__(self) -> None:
        # Read settings once at construction so the factory surfaces the error
        # immediately rather than on first use. Webhook-only tests must
        # monkeypatch ``stripe_secret_key`` on the cached Settings instance
        # *before* this constructor runs (autouse fixture in test_billing_provider
        # clears ``_PROVIDER_CACHE`` between tests so caching is not an issue).
        from app.core.config import get_settings

        settings: Settings = get_settings()
        if not settings.stripe_secret_key:
            raise ProviderNotConfiguredError(
                "Stripe billing provider is not configured: "
                "STRIPE_SECRET_KEY is not set."
            )
        self._settings = settings

    async def create_checkout(
        self,
        plan: dict,
        user: dict,
        return_urls: CheckoutUrls,
        *,
        idempotency_key: str | None = None,
    ) -> CheckoutSession:
        """Create a Stripe Checkout session via the existing client wrapper."""
        if not self._settings.stripe_secret_key:
            raise ProviderNotConfiguredError(
                "Stripe billing provider is not configured: "
                "STRIPE_SECRET_KEY is not set."
            )

        from app.services import stripe_client

        user_id = user.get("id")
        plan_id = plan.get("plan_id") or plan.get("tier", "")
        payment_method = plan.get("payment_method", "card")

        try:
            result = await stripe_client.create_checkout_session(
                user_id=user_id,
                plan_id=plan_id,
                payment_method=payment_method,
                customer_email=user.get("email", ""),
                success_url=return_urls.success_url,
                cancel_url=return_urls.cancel_url,
                idempotency_key=idempotency_key,
            )
        except ValueError:
            # The wrapper raises ValueError for unknown plan or missing key.
            # Re-raise as-is so callers can map it to a 503.
            raise

        return CheckoutSession(
            checkout_url=result["checkout_url"],
            session_id=result["session_id"],
            provider_id=self.provider_id,
        )

    async def handle_webhook(
        self,
        payload: bytes,
        signature: str,
        headers: dict[str, str],
    ) -> WebhookEvent:
        """Verify Stripe webhook signature and return a normalized event.

        Calls ``stripe.Webhook.construct_event`` which raises
        ``stripe.error.SignatureVerificationError`` on bad signatures.
        The caller (webhook endpoint) maps that to HTTP 400.

        Raises:
            ProviderNotConfiguredError: ``stripe_webhook_secret`` is not set.
        """
        if not self._settings.stripe_webhook_secret:
            raise ProviderNotConfiguredError(
                "Stripe webhook not configured: STRIPE_WEBHOOK_SECRET is not set."
            )

        # stripe-python >= 15 returns a StripeObject: convert to dict immediately.
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            self._settings.stripe_webhook_secret,
        )
        event_dict = event.to_dict()

        # Extract user_id and plan_id from metadata if present.
        metadata = event_dict.get("data", {}).get("object", {}).get("metadata", {})
        user_id_str = metadata.get("user_id")
        plan_id = metadata.get("plan_id")

        # For subscription-level events the object itself has subscription data.
        obj = event_dict.get("data", {}).get("object", {})
        sub_user_id = obj.get("metadata", {}).get("user_id")
        if not user_id_str and sub_user_id:
            user_id_str = sub_user_id

        user_id: int | None = int(user_id_str) if user_id_str else None

        return WebhookEvent(
            event_type=event_dict["type"],
            user_id=user_id,
            plan_id=plan_id,
            provider_id=self.provider_id,
            raw=event_dict,
        )

    async def get_subscription_status(self, user_id: int) -> SubStatus:
        """Read the user's active subscription from the DB and fetch live status.

        The Stripe subscription state is the source of truth; the DB Subscription
        row carries the ``stripe_subscription_id`` and ``stripe_customer_id``.
        If Stripe returns no subscription for the stored ID we fall back to
        the DB row's ``plan`` and ``status`` fields.
        """
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import and_, select

        from app.db.models import Subscription
        from app.db.session import get_session_context

        async with get_session_context() as session:
            result = await session.execute(
                select(Subscription).where(
                    and_(
                        Subscription.user_id == user_id,
                        Subscription.stripe_subscription_id.isnot(None),
                    )
                )
            )
            sub = result.scalar_one_or_none()

        if sub is None:
            return SubStatus(
                plan_id="free",
                status="active",
                current_period_end=None,
                provider_customer_id=None,
                provider_subscription_id=None,
                cancel_at_period_end=False,
            )

        stripe.api_key = self._settings.stripe_secret_key

        try:
            stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)
        except stripe.error.StripeError:
            # Subscription may have been deleted on Stripe side; fall back to DB.
            return SubStatus(
                plan_id=sub.plan or "free",
                status=sub.status or "unknown",
                current_period_end=sub.current_period_end,
                provider_customer_id=sub.stripe_customer_id,
                provider_subscription_id=sub.stripe_subscription_id,
                cancel_at_period_end=False,
            )

        period_end: datetime | None = None
        if stripe_sub.current_period_end:
            period_end = datetime.fromtimestamp(
                stripe_sub.current_period_end, tz=UTC
            )
        else:
            period_end = datetime.now(UTC) + timedelta(days=30)

        return SubStatus(
            plan_id=sub.plan or "free",
            status=stripe_sub.status,
            current_period_end=period_end,
            provider_customer_id=sub.stripe_customer_id,
            provider_subscription_id=sub.stripe_subscription_id,
            cancel_at_period_end=stripe_sub.cancel_at_period_end,
        )

    async def cancel_subscription(self, user_id: int) -> None:
        """Cancel the user's Stripe subscription (idempotent)."""
        from sqlalchemy import and_, select

        from app.db.models import Subscription
        from app.db.session import get_session_context

        stripe.api_key = self._settings.stripe_secret_key

        async with get_session_context() as session:
            result = await session.execute(
                select(Subscription).where(
                    and_(
                        Subscription.user_id == user_id,
                        Subscription.stripe_subscription_id.isnot(None),
                    )
                )
            )
            sub = result.scalar_one_or_none()

        if sub and sub.stripe_subscription_id:
            try:
                stripe.Subscription.delete(sub.stripe_subscription_id)
            except stripe.error.StripeError:
                # Already canceled or not found — idempotent by contract.
                pass

    def supports_country(self, country_code: str) -> bool:
        """Stripe is a global provider; supports all countries."""
        return True
