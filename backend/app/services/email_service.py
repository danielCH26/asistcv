"""
Email delivery service.

Providers (selected by ``EMAIL_PROVIDER``):

* ``console``  — dev/QA mode: the email is logged at INFO (code included)
  and delivery reports success. Lets the whole auth flow run end-to-end
  without any external account.
* ``resend``   — default. Single POST to ``https://api.resend.com/emails``
  with a bearer token; httpx only, no new transitive dependencies.
* ``brevo``    — single POST to ``https://api.brevo.com/v3/smtp/email``
  with an ``api-key`` header. Works with a verified *sender email* and
  no custom domain, which is the $0 path while the product has no
  domain of its own.

The service is best-effort and intentionally never raises from the
provider into the request handler:

* Missing API key (dev / local) → log ``email_service_disabled`` and
  return ``False``. The rest of the request must still succeed.
* Transport / provider error → log ``email_send_failed`` with status +
  latency, return ``False``. The caller decides whether to retry.
"""
import asyncio
import re
from time import perf_counter
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

_logger = get_logger("app.services.email")

# Resend's transactional endpoint. Versioned through the URL so a future
# v2 (if it lands) doesn't silently change the response shape on us.
_RESEND_URL = "https://api.resend.com/emails"

# Brevo (ex-Sendinblue) transactional endpoint.
_BREVO_URL = "https://api.brevo.com/v3/smtp/email"

_FROM_RE = re.compile(r"^(.*?)\s*<([^>]+)>\s*$")


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


def _split_from(from_value: str) -> tuple[str, str]:
    """Split ``"Name <addr@x>"`` into ``(name, addr)`` (``("", v)`` if bare)."""
    match = _FROM_RE.match(from_value.strip())
    if match:
        return match.group(1).strip(), match.group(2)
    return "", from_value.strip()


async def _post_and_log(
    provider: str,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    to: str,
    subject: str,
) -> bool:
    """Shared HTTP tail: POST, log latency/outcome, never raise.

    Returns ``True`` on a 2xx from the provider, ``False`` otherwise.
    """
    start = perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)
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


async def _send_resend(
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None,
    settings: Any,
) -> bool:
    """Dispatch through Resend. Returns ``True`` on 2xx."""
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
    return await _post_and_log(
        "resend", _RESEND_URL, payload, headers, to, subject
    )


async def _send_brevo(
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None,
    settings: Any,
) -> bool:
    """Dispatch through Brevo. Works with a verified sender, no domain.

    Returns ``True`` on 2xx.
    """
    api_key = settings.brevo_api_key
    if not api_key:
        _logger.warning(
            "email_service_disabled",
            reason="missing_brevo_api_key",
            to=to,
            subject=subject,
        )
        return False

    from_name, from_email = _split_from(settings.email_from)
    payload: dict[str, Any] = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html_body,
    }
    if text_body is not None:
        payload["textContent"] = text_body

    headers = {
        "api-key": api_key,
        "content-type": "application/json",
        "accept": "application/json",
    }
    return await _post_and_log(
        "brevo", _BREVO_URL, payload, headers, to, subject
    )


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

    if provider == "console":
        # Dev/QA provider: print the full email to the service log so the
        # auth flow is testable end-to-end without any external account.
        _logger.info(
            "email_console",
            to=to,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
        return True

    if provider == "resend":
        return await _send_resend(to, subject, html_body, text_body, settings)

    if provider == "brevo":
        return await _send_brevo(to, subject, html_body, text_body, settings)

    # Every unknown value is treated as "not configured" so an env-var
    # typo can't ship a request into the void.
    _logger.warning(
        "email_provider_unsupported",
        provider=provider,
        to=to,
    )
    return False
