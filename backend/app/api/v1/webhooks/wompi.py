"""
Wompi webhook handler.

Processes Wompi webhooks with signature verification.

BillingProvider adapter (feat/pasarela-pagos-56, new provider):
  Signature verification is delegated to ``WompiProvider.handle_webhook``.
  The endpoint owns idempotency (DB commits) and dispatches to handlers.

Docs: https://docs.wompi.co/docs/colombia/eventos/
"""
import logging

from fastapi import APIRouter, HTTPException, Request

from app.api.v1.webhooks.lemonsqueezy import _handle_webhook_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post("/wompi")
async def wompi_webhook(request: Request):
    """Receive Wompi webhook notifications.

    Wompi sends webhooks to this endpoint when transaction events occur.
    Configure this URL in your Wompi Dashboard:
    - Panel de Control → Aplicativos → Tu app → "Notifica via Webhook"

    URL para Sandbox: http://localhost:8000/api/v1/webhooks/wompi
    URL para Producción: https://tu-dominio.com/api/v1/webhooks/wompi
    """
    payload = await request.body()

    # Wompi sends the checksum in X-Event-Checksum header
    # Also check wompi_hash for compatibility
    checksum_header = request.headers.get("X-Event-Checksum")
    if not checksum_header:
        checksum_header = request.headers.get("x-event-checksum")
    if not checksum_header:
        checksum_header = request.headers.get("wompi_hash")

    try:
        result = await _handle_webhook_event(
            provider_id="wompi",
            payload=payload,
            signature=checksum_header or "",
            headers=dict(request.headers),
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error in Wompi webhook")
        raise HTTPException(status_code=500, detail="Internal error") from exc
