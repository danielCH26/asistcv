"""
Implements ``BillingProvider`` using the ``WompiClient``.
``WOMPI_PRIVATE_KEY`` and ``WOMPI_PUBLIC_KEY`` must be set;
missing them raises ``ProviderNotConfiguredError`` at construction time.

Supported payment methods:
  - CARD (credit/debit)
  - PSE (ACH bank transfer)
  - NEQUI (digital wallet)
  - BANCOLOMBIA_TRANSFER

Supported countries: CO (Colombia).
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

from app.services.billing_provider import (
    BillingProvider,
    CheckoutSession,
    CheckoutUrls,
    ProviderNotConfiguredError,
    SubStatus,
    WebhookEvent,
)
from app.services.providers.cop_prices import cop_amount_cents
from app.services.wompi_client import WompiClient

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.services.wompi_client import WompiClient


class WompiProvider(BillingProvider):
    """Wompi-backed billing provider for Colombia (Bancolombia gateway)."""

    provider_id: ClassVar[str] = "wompi"

    def __init__(self) -> None:
        from app.core.config import get_settings

        settings: Settings = get_settings()

        if not settings.wompi_private_key:
            raise ProviderNotConfiguredError(
                "Wompi billing provider is not configured: "
                "WOMPI_PRIVATE_KEY is not set."
            )
        if not settings.wompi_public_key:
            raise ProviderNotConfiguredError(
                "Wompi billing provider is not configured: "
                "WOMPI_PUBLIC_KEY is not set."
            )

        self._settings = settings
        self._client: WompiClient | None = None

    @property
    def _wompi_client(self) -> WompiClient:
        if self._client is None:
            self._client = WompiClient(
                private_key=self._settings.wompi_private_key,
                public_key=self._settings.wompi_public_key,
                acceptance_token=self._settings.wompi_acceptance_token,
                test_mode=self._settings.wompi_test_mode,
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
        """Crea el checkout de Wompi como URL de Web Checkout alojado.

        El checkout NO se crea por API: Wompi exige el `token` de una
        tarjeta tokenizada para crear una transaccion de tarjeta, y para PSE
        pide los datos completos del pagador. La via soportada es el Web
        Checkout (`https://checkout.wompi.co/p/`), que es un formulario GET
        con la llave publica, el monto, la referencia y la firma de
        integridad. Wompi crea la transaccion cuando el usuario paga ahi y
        despues avisa por webhook (`transaction.updated`), que es lo que
        activa la suscripcion.

        Por eso `plan["payment_method"]` no decide nada aqui: el metodo de
        pago lo elige el usuario en la pagina de Wompi.
        """
        plan_id = plan.get("plan_id") or plan.get("tier", "")

        # Get price from the shared COP price table.
        #
        # Wompi pide el monto en CENTAVOS: 29.000 COP son 2.900.000. La
        # tabla compartida guarda los precios en pesos y convierte acá.
        # (La versión anterior mandaba 29000 como centavos → cobraba
        # 290.000 COP, diez veces lo que dice el catálogo.)
        amount = cop_amount_cents(plan_id)

        user_email = user.get("email", "")
        user_id = user.get("id", 0)

        # Build reference.
        #
        # El reference es el ÚNICO campo libre que Wompi devuelve en el webhook,
        # asi que tiene que llevar user_id y plan_id (el webhook los necesita
        # para activar la suscripcion). Formato:
        #
        #     {user_id}_{plan_id}_{uniq}
        #
        # El plan_id va en el medio porque sus ids llevan "_"
        # ("job_seeker_monthly"): parsear por el primer "_" devolvía "job",
        # un plan inexistente, y el guard de `Subscription.PLAN_TYPES`
        # descartaba el evento — el usuario pagaba y su plan no cambiaba.
        # `uniq` es SIEMPRE la ultima parte, asi que el plan es todo lo de
        # en medio. El idempotency_key no se usa crudo como reference: se
        # hashea para mantener la misma referencia (y la misma transaccion)
        # ante reintentos, sin perder user_id ni plan_id.
        if idempotency_key:
            uniq = hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]
        else:
            uniq = str(int(time.time()))
        reference = f"{user_id}_{plan_id}_{uniq}"

        # La firma de integridad la calcula el cliente al armar la URL.
        checkout_url = self._wompi_client.build_web_checkout_url(
            reference=reference,
            amount_in_cents=amount,
            currency="COP",
            customer_email=user_email,
            redirect_url=return_urls.success_url,
            integrity_key=self._settings.wompi_integrity_key or "",
        )

        return CheckoutSession(
            checkout_url=checkout_url,
            session_id=reference,
            provider_id=self.provider_id,
        )

    async def handle_webhook(
        self,
        payload: bytes,
        signature: str,
        headers: dict[str, str],
    ) -> WebhookEvent:
        """Verify Wompi webhook and return normalized event."""
        if not self._settings.wompi_webhook_secret:
            raise ProviderNotConfiguredError(
                "Wompi webhook not configured: "
                "WOMPI_WEBHOOK_SECRET is not set."
            )

        # Verify signature using Wompi's SHA256 method
        if not self._wompi_client.verify_webhook_signature(
            payload,
            signature,
            self._settings.wompi_webhook_secret,
        ):
            raise ValueError("Invalid Wompi webhook signature")

        try:
            body = json.loads(payload)
        except json.JSONDecodeError:
            raise ValueError("Invalid webhook payload")

        # Extract event data
        data = body.get("data", {})
        transaction = data.get("transaction", {})
        reference = transaction.get("reference", "")
        user_id: int | None = None
        plan_id: str | None = None

        # Parse reference format: {user_id}_{plan_id}_{uniq}
        # El plan_id ocupa todo lo de en medio: sus ids llevan "_" y el
        # ultimo segmento es siempre el sufijo unico.
        if reference:
            parts = reference.split("_")
            if len(parts) >= 2:
                try:
                    user_id = int(parts[0])
                    plan_id = "_".join(parts[1:-1]) if len(parts) > 2 else parts[1]
                except ValueError:
                    pass

        # Map Wompi status to normalized event type
        status = transaction.get("status", "")
        status_map = {
            "APPROVED": "subscription.activated",
            "PENDING": "subscription.pending",
            "DECLINED": "subscription.payment_failed",
            "VOIDED": "subscription.cancelled",
            "REFUNDED": "subscription.cancelled",
            "ERROR": "subscription.payment_failed",
        }

        normalized_event = status_map.get(status, f"payment.{status.lower()}")

        # El handler compartido (_handle_webhook_event → _handle_subscription_upsert)
        # lee la forma de Lemon Squeezy: data.attributes.status y
        # data.attributes.renews_at. Wompi manda data.transaction.*, asi que el
        # provider normaliza su payload a esa forma antes de devolverlo. Sin
        # esto la suscripcion se creaba con el status leido de un dict vacio y
        # SIN fecha de renovacion (current_period_end = null).
        attributes_status = {
            "APPROVED": "active",
            "PENDING": "incomplete",
            "DECLINED": "incomplete",
            "VOIDED": "canceled",
            "REFUNDED": "canceled",
            "ERROR": "incomplete",
        }.get(status, "active")
        renews_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        normalized_raw = {
            **body,
            "data": {
                **data,
                "attributes": {
                    "status": attributes_status,
                    "renews_at": renews_at,
                },
            },
        }

        return WebhookEvent(
            event_type=normalized_event,
            user_id=user_id,
            plan_id=plan_id,
            provider_id=self.provider_id,
            raw=normalized_raw,
        )

    async def get_subscription_status(self, user_id: int) -> SubStatus:
        """Return subscription state from the DB.

        Wompi doesn't have a subscription API. We store subscription info
        in our DB (via webhook) and query it here.
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

        Note: Wompi doesn't have a direct subscription cancellation API.
        We store the intent locally and the next webhook confirmation
        will update the actual status.
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
            return  # No-op for unknown users

        async with get_session_context() as session:
            await session.execute(
                update(Subscription)
                .where(Subscription.user_id == user_id)
                .values(status="canceled")
            )
            await session.commit()

    def supports_country(self, country_code: str) -> bool:
        """Wompi is only available in Colombia (CO)."""
        return country_code.upper() == "CO"

    @property
    def public_key(self) -> str:
        """Return public key for frontend Wompi Widget initialization."""
        return self._wompi_client.public_key
