"""
Lemon Squeezy billing provider — issue #56, slice 2.

Implements ``BillingProvider`` using the ``LemonSqueezyClient``.
``LEMON_SQUEEZY_API_KEY`` and ``LEMON_SQUEEZY_STORE_ID`` must be set;
missing either raises ``ProviderNotConfiguredError`` at construction time.

Variant mapping (plan_id → env variant ID):
  job_seeker_monthly  → LEMON_SQUEEZY_VARIANT_JOB_SEEKER_MONTHLY
  recruiter_starter   → LEMON_SQUEEZY_VARIANT_RECRUITER_STARTER
  recruiter_business  → LEMON_SQUEEZY_VARIANT_RECRUITER_BUSINESS
  recruiter_agency    → LEMON_SQUEEZY_VARIANT_RECRUITER_AGENCY
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import TYPE_CHECKING, ClassVar

from app.services.billing_provider import (
    BillingProvider,
    CheckoutSession,
    CheckoutUrls,
    ProviderNotConfiguredError,
    SubStatus,
    WebhookEvent,
)
from app.services.lemon_squeezy_client import (
    LemonSqueezyAuthError,
    LemonSqueezyConnectionError,
    LemonSqueezyError,
    LemonSqueezyRateLimitError,
    LemonSqueezyTimeoutError,
)

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.services.lemon_squeezy_client import LemonSqueezyClient


# Variant resolution map: plan_id (or tier) → settings attribute name
_VARIANT_SETTINGS: dict[str, str] = {
    "job_seeker_monthly": "lemon_squeezy_variant_job_seeker_monthly",
    "recruiter_starter": "lemon_squeezy_variant_recruiter_starter",
    "recruiter_business": "lemon_squeezy_variant_recruiter_business",
    "recruiter_agency": "lemon_squeezy_variant_recruiter_agency",
}


def _resolve_variant(settings: Settings, plan_id: str) -> str:
    """Return the configured LS variant ID for ``plan_id``.

    Raises:
        ValueError: No variant is configured for the given plan.
    """
    attr = _VARIANT_SETTINGS.get(plan_id)
    if not attr:
        raise ValueError(f"No Lemon Squeezy variant configured for plan: {plan_id}")
    variant: str | None = getattr(settings, attr, None)
    if not variant:
        raise ValueError(f"No Lemon Squeezy variant configured for plan: {plan_id}")
    return variant


class LemonSqueezyProvider(BillingProvider):
    """Lemon Squeezy-backed billing provider."""

    provider_id: ClassVar[str] = "lemon_squeezy"

    def __init__(self) -> None:
        from app.core.config import get_settings

        settings: Settings = get_settings()

        if not settings.lemon_squeezy_api_key:
            raise ProviderNotConfiguredError(
                "Lemon Squeezy billing provider is not configured: "
                "LEMON_SQUEEZY_API_KEY is not set."
            )
        if not settings.lemon_squeezy_store_id:
            raise ProviderNotConfiguredError(
                "Lemon Squeezy billing provider is not configured: "
                "LEMON_SQUEEZY_STORE_ID is not set."
            )

        self._settings = settings
        self._client: LemonSqueezyClient | None = None

    @property
    def _ls_client(self) -> LemonSqueezyClient:
        if self._client is None:
            self._client = LemonSqueezyClient(
                api_key=self._settings.lemon_squeezy_api_key,
            )
        return self._client

    async def create_checkout(
        self,
        plan: dict,
        user: dict,
        return_urls: CheckoutUrls,
        *,
        idempotency_key: str | None = None,
    ) -> CheckoutSession:
        """Create a Lemon Squeezy hosted checkout session."""
        plan_id = plan.get("plan_id") or plan.get("tier", "")

        # Resolve variant (raises ValueError for unknown/missing plan → mapped to 503)
        variant_id = _resolve_variant(self._settings, plan_id)

        custom: dict[str, str] = {
            "user_id": str(user["id"]),
            "plan_id": plan_id,
        }

        # Lemon Squeezy errors surface as typed exceptions; the caller maps
        # generic LemonSqueezyError → 503 BILLING_ERROR. Auth/rate-limit
        # subclasses are re-raised as-is so the endpoint can handle them distinctly.
        try:
            result = await self._ls_client.create_checkout(
                store_id=self._settings.lemon_squeezy_store_id,
                variant_id=variant_id,
                custom=custom,
                test_mode=self._settings.lemon_squeezy_test_mode,
                redirect_url=return_urls.success_url,
            )
        except LemonSqueezyAuthError:
            raise
        except LemonSqueezyRateLimitError:
            raise
        except LemonSqueezyTimeoutError:
            raise
        except LemonSqueezyConnectionError:
            raise
        except LemonSqueezyError:
            raise

        return CheckoutSession(
            checkout_url=result["checkout_url"],
            session_id=result["checkout_id"],
            provider_id=self.provider_id,
        )

    async def handle_webhook(
        self,
        payload: bytes,
        signature: str,
        headers: dict[str, str],
    ) -> WebhookEvent:
        """Verify LS HMAC-SHA256 signature and return a normalised event."""
        if not self._settings.lemon_squeezy_webhook_secret:
            raise ProviderNotConfiguredError(
                "Lemon Squeezy webhook not configured: "
                "LEMON_SQUEEZY_WEBHOOK_SECRET is not set."
            )

        # Resolve signature: prefer the explicit ``signature`` argument (set by
        # the caller from the raw header), but fall back to a case-insensitive
        # headers lookup if the caller passed an empty string (e.g. header
        # forwarded via a proxy that normalises it to lowercase).
        sig = signature
        if not sig:
            for k, v in headers.items():
                if k.lower() == self._settings.lemon_squeezy_signature_header.lower():
                    sig = v
                    break

        secret = self._settings.lemon_squeezy_webhook_secret.encode()
        expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig.strip()):
            raise ValueError("Invalid signature")

        try:
            body = json.loads(payload)
        except json.JSONDecodeError:
            raise ValueError("Invalid payload")

        meta = body.get("meta", {})
        event_type: str = meta.get("event_name", "")
        custom_data: dict = meta.get("custom_data", {})
        user_id_str = custom_data.get("user_id")
        user_id: int | None = int(user_id_str) if user_id_str else None
        plan_id: str | None = custom_data.get("plan_id")

        return WebhookEvent(
            event_type=event_type,
            user_id=user_id,
            plan_id=plan_id,
            provider_id=self.provider_id,
            raw=body,
        )

    async def get_subscription_status(self, user_id: int) -> SubStatus:
        """Return subscription state from the DB (no remote API call).

        Remote status sync (LS API → DB) lands in slice 3 (T3/T4) together
        with the payment_methods table, which provides the LS subscription ID
        needed for the API call.
        """
        from sqlalchemy import and_, select

        from app.db.models import Subscription
        from app.db.session import get_session_context

        async with get_session_context() as session:
            result = await session.execute(
                select(Subscription).where(
                    and_(
                        Subscription.user_id == user_id,
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

        return SubStatus(
            plan_id=sub.plan or "free",
            status=sub.status or "active",
            current_period_end=sub.current_period_end,
            provider_customer_id=None,
            provider_subscription_id=None,
            cancel_at_period_end=sub.status == "canceled",
        )

    async def cancel_subscription(self, user_id: int) -> None:
        """Cancel the user's subscription locally in the DB.

        The LS API cancel call lands in slice 3 (T3/T4) together with the
        payment_methods table, which provides the LS subscription ID needed
        for the API call. The DB cancel here is a local-only, best-effort
        no-op: it sets status="canceled" when a Subscription row exists so
        that the next /status call reflects the intent immediately. The
        incoming webhook from LS will confirm the actual cancellation.
        """
        from sqlalchemy import and_, select, update

        from app.db.models import Subscription
        from app.db.session import get_session_context

        async with get_session_context() as session:
            result = await session.execute(
                select(Subscription).where(
                    and_(Subscription.user_id == user_id)
                )
            )
            sub = result.scalar_one_or_none()

        if sub is None:
            return  # No-op for unknown users (idempotent by contract)

        # Local-only cancellation: set status="canceled" immediately so that
        # get_subscription_status reflects it without waiting for a webhook.
        async with get_session_context() as session:
            await session.execute(
                update(Subscription)
                .where(Subscription.user_id == user_id)
                .values(status="canceled")
            )
            await session.commit()

    def supports_country(self, country_code: str) -> bool:
        """Lemon Squeezy is a global "Money of Record" provider; all countries."""
        return True
