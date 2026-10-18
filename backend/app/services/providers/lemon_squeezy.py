"""
Lemon Squeezy billing provider (stub — slice 2, feat/pasarela-pagos-56).

Not implemented in slice 1. This stub exists so the factory can accept
``"lemon_squeezy"`` as a valid ``provider_id`` without crashing at import time.
Instantiating ``LemonSqueezyProvider`` in slice 1 raises ``NotImplementedError``.

Env vars required (stub, not validated until slice 2):
  LEMON_SQUEEZY_API_KEY
  LEMON_SQUEEZY_STORE_ID
  LEMON_SQUEEZY_WEBHOOK_SECRET
  LEMON_SQUEEZY_SIGNATURE_HEADER  (default "X-Signature")
  LEMON_SQUEEZY_VARIANT_JOB_SEEKER_MONTHLY
  LEMON_SQUEEZY_VARIANT_RECRUITER_STARTER
  LEMON_SQUEEZY_VARIANT_RECRUITER_BUSINESS
  LEMON_SQUEEZY_VARIANT_RECRUITER_AGENCY

See docs/DEPLOY.md and odd/tasks/feat-pasarela-pagos-56.md S5.
"""

from __future__ import annotations

from typing import ClassVar

from app.services.billing_provider import (
    BillingProvider,
    CheckoutSession,
    CheckoutUrls,
    SubStatus,
    WebhookEvent,
)


class LemonSqueezyProvider(BillingProvider):
    """Lemon Squeezy billing provider — slice 2."""

    provider_id: ClassVar[str] = "lemon_squeezy"

    def __init__(self) -> None:
        raise NotImplementedError(
            "LemonSqueezyProvider is not yet implemented (slice 2 of #56)."
        )

    async def create_checkout(
        self,
        plan: dict,
        user: dict,
        return_urls: CheckoutUrls,
    ) -> CheckoutSession:
        raise NotImplementedError

    async def handle_webhook(
        self,
        payload: bytes,
        signature: str,
        headers: dict[str, str],
    ) -> WebhookEvent:
        raise NotImplementedError

    async def get_subscription_status(self, user_id: int) -> SubStatus:
        raise NotImplementedError

    async def cancel_subscription(self, user_id: int) -> None:
        raise NotImplementedError

    def supports_country(self, country_code: str) -> bool:
        # LS supports USD globally; COP/USD only for CO/US/EU out of scope.
        return True
