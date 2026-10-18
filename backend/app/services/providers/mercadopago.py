"""
Mercado Pago billing provider (stub — slice 3, feat/pasarela-pagos-56).

Not implemented in slice 1. This stub exists so the factory can accept
``"mercadopago"`` as a valid ``provider_id`` without crashing at import time.
Instantiating ``MercadoPagoProvider`` in slice 1 raises ``NotImplementedError``.

Env vars required (stub, not validated until slice 3):
  MERCADOPAGO_ACCESS_TOKEN
  MERCADOPAGO_PUBLIC_KEY
  MERCADOPAGO_WEBHOOK_SECRET

Supported countries: CO (COP via PSE / Nequi / Bancolombia / card).
See docs/DEPLOY.md and odd/tasks/feat-pasarela-pagos-56.md S6.
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


class MercadoPagoProvider(BillingProvider):
    """Mercado Pago billing provider — slice 3."""

    provider_id: ClassVar[str] = "mercadopago"

    def __init__(self) -> None:
        raise NotImplementedError(
            "MercadoPagoProvider is not yet implemented (slice 3 of #56)."
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
        # Mercado Pago covers CO primarily; PSE / Nequi / card only.
        return country_code.upper() == "CO"
