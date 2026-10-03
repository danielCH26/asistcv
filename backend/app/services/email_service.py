"""
Email delivery service.

Provider: Resend (default) over HTTPS. The HTTP API is a single POST to
``https://api.resend.com/emails`` with a bearer token; using httpx means
no SMTP / DNS plumbing and no new transitive dependencies (httpx is
already required for Groq / HuggingFace).

The service is best-effort and intentionally never raises from the
provider into the request handler:

* Missing ``RESEND_API_KEY`` (dev / local) → log ``email_service_disabled``
  and return ``False``. The rest of the request must still succeed —
  verify-email still returns 202 because the token row is persisted, and
  the user can pick the link up from the logs.
* Transport / provider error → log ``email_send_failed`` with status +
  latency, return ``False``. The caller decides whether to retry; right
  now nothing does (one shot per request).

Selecting a different provider is a matter of adding a branch in
``_dispatch`` and a corresponding env var. ``sendgrid`` and ``smtp`` are
listed as the next two on purpose so the switch is mechanical.
"""
import asyncio
from time import perf_counter
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

_logger = get_logger("app.services.email")

# Resend's transactional endpoint. Versioned through the URL so a future
# v2 (if it lands) doesn't silently change the response shape on us.
_RESEND_URL = "https://api.resend.com/emails"


def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> bool:
    """Synchronous wrapper around the async dispatch.

    Kept as a plain ``def`` so callers that already have the loop (FastAPI
    endpoints, async workers) can ``await`` ``send_email_async`` directly
    instead. From sync call sites this version hops into a fresh event
    loop via ``asyncio.run`` — fine because it does no I/O outside of
    httpx and the function never raises.

    Returns ``True`` on a 2xx from the provider, ``False`` otherwise.
    """
    return asyncio.run(_dispatch(to, subject, html_body, text_body))


async def send_email_async(
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> bool:
    """Async variant for use from inside an existing event loop.

    Identical contract to ``send_email``; the split just keeps us from
    creating a nested loop with ``asyncio.run`` when called from a
    FastAPI handler or any other coroutine.
    """
    return await _dispatch(to, subject, html_body, text_body)


async def _dispatch(
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None,
) -> bool:
    """Async dispatch that fans out to the configured provider.

    Returns ``True`` on a 2xx from the provider, ``False`` otherwise.
    Never raises — the rest of the request must keep working even when
    email is unavailable (dev mode, missing key, provider outage).
    """
    settings = get_settings()
    provider = settings.email_provider

    if provider != "resend":
        # Future: dispatch by provider name. For now every non-resend value
        # is treated as "not configured" so an env-var typo can't ship a
        # request into the void.
        _logger.warning(
            "email_provider_unsupported",
            provider=provider,
            to=to,
        )
        return False

    api_key = settings.resend_api_key
    if not api_key:
        # Graceful dev fallback: no key, no email. Log loudly so it's
        # obvious in dev logs (and in tests that want to assert it).
        _logger.warning(
            "email_service_disabled",
            reason="missing_resend_api_key",
            to=to,
            subject=subject,
        )
        return False

    payload: dict[str, Any] = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    if text_body is not None:
        payload["text"] = text_body

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # Resend tags the source so dashboards can split by app
        "X-Entity-Ref": "asistcv-verify-email",
    }

    start = perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(_RESEND_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        latency_ms = round((perf_counter() - start) * 1000, 2)
        _logger.error(
            "email_send_failed",
            provider=provider,
            to=to,
            latency_ms=latency_ms,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return False

    latency_ms = round((perf_counter() - start) * 1000, 2)
    if 200 <= response.status_code < 300:
        _logger.info(
            "email_sent",
            provider=provider,
            to=to,
            latency_ms=latency_ms,
            status=response.status_code,
        )
        return True

    _logger.error(
        "email_send_failed",
        provider=provider,
        to=to,
        latency_ms=latency_ms,
        status=response.status_code,
        body=response.text[:500],
    )
    return False
