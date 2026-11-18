"""
Mercado Pago billing provider — issue #56, slice 3.

Implements ``BillingProvider`` using the ``MercadoPagoClient``.
``MERCADOPAGO_ACCESS_TOKEN`` must be set; missing it raises
``ProviderNotConfiguredError`` at construction time.

How the checkout works:
  1. We create a **Checkout Pro preference** (``POST /checkout/preferences``)
     with the plan, the payer email and a ``back_urls`` set.
  2. We hand the hosted URL (``init_point`` / ``sandbox_init_point``) back to
     the frontend, which redirects the user to Mercado Pago.
  3. Mercado Pago notifies ``/api/v1/webhooks/mercadopago`` and we activate
     the subscription.

The notification body only carries the payment id, so the webhook fetches the
payment (``GET /v1/payments/{id}``) to read the status and the
``external_reference`` we stamped on the preference.

Supported payment methods: card, PSE, Nequi, Bancolombia (COP).
Supported countries: CO (Colombia).

Docs: https://www.mercadopago.com.co/developers/es/docs
"""

from __future__ import annotations

import hashlib
import json
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
from app.services.mercadopago_client import (
    MercadoPagoAuthError,
    MercadoPagoClient,
    MercadoPagoConnectionError,
    MercadoPagoError,
    MercadoPagoRateLimitError,
    MercadoPagoTimeoutError,
)
from app.services.providers.cop_prices import cop_price

if TYPE_CHECKING:
    from app.core.config import Settings


# Human-readable plan names shown in the Mercado Pago checkout.
_PLAN_TITLES: dict[str, str] = {
    "job_seeker_monthly": "eptus — Plan mensual para quien busca empleo",
    "recruiter_starter": "eptus — Recruiter Starter",
    "recruiter_business": "eptus — Recruiter Business",
    "recruiter_agency": "eptus — Recruiter Agency",
}

# Mercado Pago payment status → our normalized event type.
_STATUS_TO_EVENT: dict[str, str] = {
    "approved": "subscription.activated",
    "authorized": "subscription.pending",
    "in_process": "subscription.pending",
    "pending": "subscription.pending",
    "rejected": "subscription.payment_failed",
    "cancelled": "subscription.cancelled",
    "refunded": "subscription.cancelled",
    "charged_back": "subscription.payment_failed",
}

# Mercado Pago payment status → the status our domain understands
# (``data.attributes.status`` in the normalized payload).
_STATUS_TO_ATTRIBUTE: dict[str, str] = {
    "approved": "active",
    "authorized": "incomplete",
    "in_process": "incomplete",
    "pending": "incomplete",
    "rejected": "incomplete",
    "cancelled": "canceled",
    "refunded": "canceled",
    "charged_back": "incomplete",
}


class MercadoPagoProvider(BillingProvider):
    """Mercado Pago-backed billing provider for Colombia (COP)."""

    provider_id: ClassVar[str] = "mercadopago"

    def __init__(self) -> None:
        from app.core.config import get_settings

        settings: Settings = get_settings()

        if not settings.mercadopago_access_token:
            raise ProviderNotConfiguredError(
                "Mercado Pago billing provider is not configured: "
                "MERCADOPAGO_ACCESS_TOKEN is not set."
            )

        self._settings = settings
        self._client: MercadoPagoClient | None = None

    @property
    def _mp_client(self) -> MercadoPagoClient:
        if self._client is None:
            self._client = MercadoPagoClient(
                access_token=self._settings.mercadopago_access_token or "",
                test_mode=self._settings.mercadopago_test_mode,
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
        """Create a Mercado Pago Checkout Pro preference."""
        plan_id = plan.get("plan_id") or plan.get("tier", "")
        amount_cop = cop_price(plan_id)

        user_id = user.get("id", 0)
        user_email = user.get("email", "")

        # ``external_reference`` es el único campo que Mercado Pago devuelve
        # verbatim en el webhook, así que tiene que llevar user_id y plan_id.
        # Formato:
        #
        #     {user_id}_{plan_id}_{uniq}
        #
        # El plan_id va en el medio porque sus ids llevan "_"
        # ("job_seeker_monthly"): parsear por el primer "_" devolvía "job",
        # un plan inexistente, y el guard de `Subscription.PLAN_TYPES`
        # descartaba el evento — el usuario pagaba y su plan no cambiaba.
        # `uniq` es SIEMPRE la ultima parte, asi que el plan es todo lo de
        # en medio. El idempotency_key no se usa crudo: se hashea para
        # mantener la misma referencia ante reintentos, sin perder
        # user_id ni plan_id.
        if idempotency_key:
            uniq = hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]
        else:
            uniq = str(int(datetime.now(UTC).timestamp()))
        reference = f"{user_id}_{plan_id}_{uniq}"

        payload = {
            "items": [
                {
                    "id": plan_id,
                    "title": _PLAN_TITLES.get(plan_id, "eptus — Suscripción"),
                    "quantity": 1,
                    # Mercado Pago pide el precio en la unidad mayor de la
                    # moneda (pesos), NO en centavos.
                    "unit_price": amount_cop,
                    "currency_id": "COP",
                }
            ],
            "payer": {"email": user_email},
            "external_reference": reference,
            "back_urls": {
                "success": return_urls.success_url,
                "pending": return_urls.success_url,
                "failure": return_urls.cancel_url,
            },
            "auto_return": "approved",
            "metadata": {
                "user_id": str(user_id),
                "plan_id": plan_id,
            },
        }

        notification_url = self._settings.mercadopago_notification_url
        if notification_url:
            payload["notification_url"] = notification_url

        try:
            result = await self._mp_client.create_preference(payload)
        except MercadoPagoAuthError:
            raise
        except MercadoPagoRateLimitError:
            raise
        except MercadoPagoTimeoutError:
            raise
        except MercadoPagoConnectionError:
            raise
        except MercadoPagoError:
            raise

        # En modo test el checkout vive en sandbox_init_point.
        if self._settings.mercadopago_test_mode:
            checkout_url = result.get("sandbox_init_point") or result.get("init_point", "")
        else:
            checkout_url = result.get("init_point", "")

        return CheckoutSession(
            checkout_url=checkout_url,
            session_id=str(result.get("id", "")),
            provider_id=self.provider_id,
        )

    async def handle_webhook(
        self,
        payload: bytes,
        signature: str,
        headers: dict[str, str],
    ) -> WebhookEvent:
        """Verify the notification and return a normalised event."""
        if not self._settings.mercadopago_webhook_secret:
            raise ProviderNotConfiguredError(
                "Mercado Pago webhook not configured: "
                "MERCADOPAGO_WEBHOOK_SECRET is not set."
            )

        lowered_headers = {k.lower(): v for k, v in headers.items()}
        sig_header = signature or lowered_headers.get("x-signature", "")
        request_id = lowered_headers.get("x-request-id", "")

        if not sig_header:
            raise ValueError("Missing x-signature header")

        # x-signature: "ts=1700000000,v1=<hex>"
        ts = ""
        v1 = ""
        for part in sig_header.split(","):
            key, _, value = part.strip().partition("=")
            if key == "ts":
                ts = value
            elif key == "v1":
                v1 = value
        if not ts or not v1:
            raise ValueError("Malformed x-signature header")

        try:
            body = json.loads(payload)
        except json.JSONDecodeError:
            raise ValueError("Invalid payload")

        data = body.get("data") or {}
        data_id = str(data.get("id") or "")
        if not data_id:
            raise ValueError("Invalid payload: missing data.id")

        if not self._mp_client.verify_webhook_signature(
            data_id=data_id,
            request_id=request_id,
            timestamp=ts,
            signature=v1,
            secret=self._settings.mercadopago_webhook_secret,
        ):
            raise ValueError("Invalid signature")

        # La notificación solo trae el id del pago: hay que traer el pago.
        payment = await self._mp_client.get_payment(data_id)

        status = str(payment.get("status", ""))
        external_reference = str(payment.get("external_reference") or "")
        metadata = payment.get("metadata") or {}

        user_id: int | None = None
        plan_id: str | None = metadata.get("plan_id") or None

        if external_reference:
            parts = external_reference.split("_")
            if len(parts) >= 2:
                try:
                    user_id = int(parts[0])
                except ValueError:
                    user_id = None
                parsed_plan = "_".join(parts[1:-1]) if len(parts) > 2 else parts[1]
                if parsed_plan:
                    plan_id = parsed_plan

        if user_id is None and metadata.get("user_id"):
            try:
                user_id = int(metadata["user_id"])
            except (TypeError, ValueError):
                user_id = None

        event_type = _STATUS_TO_EVENT.get(status, f"payment.{status.lower()}")

        # El handler compartido (_handle_webhook_event → _handle_subscription_upsert)
        # lee la forma de Lemon Squeezy: data.attributes.status y
        # data.attributes.renews_at. Mercado Pago manda otro payload, asi que el
        # provider normaliza el suyo a esa forma antes de devolverlo. Sin esto
        # la suscripcion se creaba con el status leido de un dict vacio y SIN
        # fecha de renovacion (current_period_end = null).
        attributes_status = _STATUS_TO_ATTRIBUTE.get(status, "incomplete")
        renews_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        payer = payment.get("payer") or {}

        normalized_raw = {
            "type": body.get("type"),
            "action": body.get("action"),
            "data": {
                "id": data_id,
                "attributes": {
                    "status": attributes_status,
                    "renews_at": renews_at,
                    "customer_id": payer.get("id"),
                },
            },
        }

        return WebhookEvent(
            event_type=event_type,
            user_id=user_id,
            plan_id=plan_id,
            provider_id=self.provider_id,
            raw=normalized_raw,
        )

    async def get_subscription_status(self, user_id: int) -> SubStatus:
        """Return the subscription state from the DB.

        Mercado Pago's recurring subscriptions (preapproval) are not used yet:
        each purchase is a monthly payment, and the period is tracked here.
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

        Mercado Pago's refund/subscription API is not wired yet; the intent is
        recorded locally and the next webhook confirms the real state.
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

        async with get_session_context() as session:
            await session.execute(
                update(Subscription)
                .where(Subscription.user_id == user_id)
                .values(status="canceled")
            )
            await session.commit()

    def supports_country(self, country_code: str) -> bool:
        """Mercado Pago is used here for Colombia (CO)."""
        return country_code.upper() == "CO"
