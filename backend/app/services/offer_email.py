"""
Offer email summary service.

Builds and sends a periodic digest of new job offers to the user.
Uses the existing email_service (Resend) — httpx is NOT reimplemented here.

Design
------
- ``build_offer_summary_html`` is a pure function: same inputs → same outputs,
  no I/O.  This makes it trivially testable without any mocking.
- ``send_offer_summary`` orchestrates: empty offers → no-op (return False);
  otherwise builds the email and delegates to ``send_fn`` (default:
  ``send_email_async`` from email_service).

Parameter contract
------------------
``offers`` is a list of plain dicts — no ORM, no DB session needed:

    {
        "title":   str,
        "company": str,
        "url":     str,
        "snippet": str,
        "score":   float,   # 0.0 – 1.0
    }

Rationale: more testable, no model dependency, aligns with how offers
arrive from the search pipeline.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.core.logging import get_logger
from app.services import email_service

_logger = get_logger("app.services.offer_email")


# ---------------------------------------------------------------------------
# Subject / body framing by frequency
# ---------------------------------------------------------------------------

_SUBJECT_TPL = "{n} {label} para vos"
_OFFER_TPL = """
<h3><a href="{url}">{title}</a></h3>
<p><strong>{company}</strong> — Score: {score:.0%}</p>
<p>{snippet}</p>
"""

_FREQUENCY_BODY_TPL: dict[str, str] = {
    "daily": "<p>Estas son tus ofertas diarias:</p>",
    "weekly": "<p>Este es tu resumen semanal de ofertas:</p>",
}


def _plural_label(n: int) -> tuple[str, str]:
    """Return (subject_label, body_framing) for the given count."""
    if n == 1:
        return ("nueva oferta", "oferta")
    return ("nuevas ofertas", "ofertas")


# ---------------------------------------------------------------------------
# Pure builder
# ---------------------------------------------------------------------------


def build_offer_summary_html(
    offers: list[dict[str, Any]],
    frequency: str = "daily",
) -> tuple[str, str]:
    """
    Build the email subject and HTML body for an offer digest.

    Args:
        offers:    List of offer dicts (title, company, url, snippet, score).
        frequency: ``"daily"`` or ``"weekly"`` — changes framing only.

    Returns:
        A ``(subject, html_body)`` tuple.  ``html_body`` includes the
        frequency intro and one block per offer.

    No I/O — pure function, fully deterministic.
    """
    n = len(offers)
    label, _ = _plural_label(n)
    subject = _SUBJECT_TPL.format(n=n, label=label)

    framing = _FREQUENCY_BODY_TPL.get(frequency, _FREQUENCY_BODY_TPL["daily"])
    offer_blocks = "".join(
        _OFFER_TPL.format(
            title=o.get("title", ""),
            company=o.get("company", ""),
            url=o.get("url", ""),
            snippet=o.get("snippet", ""),
            score=o.get("score", 0.0),
        )
        for o in offers
    )

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{subject}</title></head>
<body>
<p><strong>AsistCV</strong></p>
{framing}
{offer_blocks}
</body>
</html>"""

    return subject, html


# ---------------------------------------------------------------------------
# Protocol so tests can inject a no-I/O mock
# ---------------------------------------------------------------------------


class SendEmailFn(Protocol):
    """Signature compatible with email_service.send_email_async."""

    async def __call__(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
    ) -> bool: ...


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def send_offer_summary(
    email_to: str,
    offers: list[dict[str, Any]],
    *,
    frequency: str = "daily",
    send_fn: SendEmailFn | None = None,
) -> bool:
    """
    Send an offer summary email to ``email_to``.

    Args:
        email_to:  Destination address.
        offers:    List of offer dicts (title, company, url, snippet, score).
        frequency: ``"daily"`` or ``"weekly"`` — framing in subject/body.
        send_fn:   Injectable async send function.  Defaults to
                   ``email_service.send_email_async``.

    Returns:
        ``True`` if the email was sent (or the caller's send_fn returned
        ``True``); ``False`` if there were no offers to send or the
        underlying call returned ``False``.
    """
    if not offers:
        _logger.debug("send_offer_summary_skipped_no_offers", email_to=email_to)
        return False

    if send_fn is None:
        send_fn = email_service.send_email_async

    subject, html_body = build_offer_summary_html(offers, frequency=frequency)

    result = await send_fn(to=email_to, subject=subject, html_body=html_body)
    if not result:
        _logger.warning(
            "send_offer_summary_failed",
            email_to=email_to,
            offer_count=len(offers),
        )
    return result
