"""
Mercado Pago webhook handler.

Processes Mercado Pago notifications with signature verification and
idempotency. Mirrors the pattern established by ``webhooks/wompi.py``.

Signature: Mercado Pago sends ``x-signature: ts=<unix>,v1=<hex>`` plus
``x-request-id``. The HMAC is verified inside
``MercadoPagoProvider.handle_webhook``.

Docs: https://www.mercadopago.com.co/developers/es/docs/your-integrations/notifications
"""
import logging

from fastapi import APIRouter, HTTPException, Request

from app.api.v1.webhooks.lemonsqueezy import _handle_webhook_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post("/mercadopago")
async def mercadopago_webhook(request: Request):
    """Receive Mercado Pago payment notifications.

    Configure this URL in your Mercado Pago dashboard:
    - Panel → Tus integraciones → Notificaciones → Mercado Pago → URL de
      notificación.

    URL para Sandbox: http://localhost:8000/api/v1/webhooks/mercadopago
    URL para Producción: https://tu-dominio.com/api/v1/webhooks/mercadopago
    """
    payload = await request.body()

    signature = request.headers.get("x-signature") or request.headers.get("X-Signature")

    try:
        result = await _handle_webhook_event(
            provider_id="mercadopago",
            payload=payload,
            signature=signature or "",
            headers=dict(request.headers),
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error in Mercado Pago webhook")
        raise HTTPException(status_code=500, detail="Internal error") from exc
