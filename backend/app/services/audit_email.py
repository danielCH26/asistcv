"""
Audit result email service.

When an anonymous-audit visitor leaves their email (capture-email), the
result they just saw on screen is re-sent to that inbox. This module
builds the email from the stored ``audit_result_json`` and delegates
delivery to ``email_service`` — no provider logic lives here.

Design (mirrors ``offer_email.py``)
-----------------------------------
- ``build_audit_result_email`` is a pure function: same ``result_json``
  → same (subject, html, text). Trivially testable without I/O.
- ``send_audit_result_email`` orchestrates and NEVER raises: a provider
  outage is logged and reported as ``False``. The capture endpoint
  already committed the funnel step before calling us, so a failed
  delivery must not turn a 202 into a 500 (same best-effort contract
  as the auth code email).

Parameter contract
------------------
``result_json`` is the dict persisted on ``audit_uploads.audit_result_json``
by ``audit_runner`` (plain dicts — no ORM, no session needed):

    Common:    mode, score, energy_level, reasoning
    jd_directed: strengths, gaps
    cv_only:   fortalezas (mirrored in ``strengths``), gaps (derived),
               problematicas: [{seccion, problema, severidad}],
               recomendaciones
"""

from __future__ import annotations

from html import escape
from typing import Any, Protocol

from app.core import brand
from app.core.logging import get_logger
from app.services import email_service

_logger = get_logger("app.services.audit_email")

_SEVERITY_LABELS = {"high": "alta", "medium": "media", "low": "baja"}

_MODE_TITLES = {
    "cv_only": "Auditoría de calidad de CV",
    "jd_directed": "Auditoría CV vs oferta",
}


# ---------------------------------------------------------------------------
# Pure builder
# ---------------------------------------------------------------------------


def _subject_for(mode: str, score: Any) -> str:
    title = _MODE_TITLES.get(mode, _MODE_TITLES["cv_only"])
    return f"{title}: puntaje {score}/100 — eptus"


def _section(title: str, items: list[str]) -> str:
    """HTML <ul> section for a list of plain strings (escaped)."""
    if not items:
        return ""
    lis = "".join(f"<li>{escape(str(item))}</li>" for item in items)
    return (
        f'<h3 style="color:{brand.INK};font-size:16px;margin:20px 0 6px;">'
        f"{escape(title)}</h3><ul style=\"padding-left:18px;margin:0;\">{lis}</ul>"
    )


def build_audit_result_email(
    result_json: dict[str, Any],
) -> tuple[str, str, str]:
    """
    Build (subject, html_body, text_body) for an audit result email.

    Works for both modes; unknown keys are ignored so the payload can
    grow (e.g. ``captured_email``) without touching this builder.

    No I/O — pure function, fully deterministic.
    """
    mode = str(result_json.get("mode", "cv_only"))
    score = result_json.get("score", 0)
    subject = _subject_for(mode, score)

    # cv_only stores the LLM's own list under both ``fortalezas`` and
    # ``strengths``; jd_directed only has ``strengths``.
    strengths = result_json.get("strengths") or result_json.get("fortalezas") or []
    gaps = result_json.get("gaps") or []

    # --- HTML ---------------------------------------------------------
    problematicas_html = ""
    problematicas = result_json.get("problematicas") or []
    if problematicas:
        rows = "".join(
            "<li>"
            f"<strong>{escape(str(p.get('seccion', '')))}</strong> "
            f"(severidad {escape(_SEVERITY_LABELS.get(str(p.get('severidad', '')), str(p.get('severidad', ''))))}): "
            f"{escape(str(p.get('problema', '')))}"
            "</li>"
            for p in problematicas
            if isinstance(p, dict)
        )
        problematicas_html = (
            f'<h3 style="color:{brand.INK};font-size:16px;margin:20px 0 6px;">'
            f"Problemáticas detectadas</h3>"
            f'<ul style="padding-left:18px;margin:0;">{rows}</ul>'
        )

    score_badge = (
        f'<p style="font-size:26px;margin:14px 0 4px;">'
        f'<strong style="color:{brand.ACTION};">{escape(str(score))}/100</strong></p>'
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{escape(subject)}</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;color:{brand.INK_MUTED};">
<p>{brand.brand_lockup()}</p>
<h2 style="color:{brand.INK};font-size:19px;margin:16px 0 4px;">{escape(_MODE_TITLES.get(mode, _MODE_TITLES["cv_only"]))}</h2>
{score_badge}
{_section("Fortalezas", strengths)}
{problematicas_html}
{_section("Brechas detectadas", gaps) if mode == "jd_directed" else ""}
{_section("Recomendaciones", result_json.get("recomendaciones") or [])}
{('<h3 style="color:' + brand.INK + ';font-size:16px;margin:20px 0 6px;">Detalle del análisis</h3><p style="white-space:pre-line;">' + escape(str(result_json.get("reasoning", ""))) + "</p>") if result_json.get("reasoning") else ""}
<p style="margin-top:24px;font-size:12px;color:{brand.INK_MUTED};">
Este resultado también está disponible en la web durante 1 hora desde que se generó.
</p>
</body>
</html>"""

    # --- Plain text -----------------------------------------------------
    lines = [brand.NAME.upper(), "", _MODE_TITLES.get(mode, _MODE_TITLES["cv_only"]), f"Puntaje: {score}/100", ""]
    if strengths:
        lines += ["Fortalezas:"]
        lines += [f"- {s}" for s in strengths]
        lines += [""]
    if problematicas:
        lines += ["Problemáticas detectadas:"]
        lines += [
            f"- {p.get('seccion', '')} (severidad {_SEVERITY_LABELS.get(str(p.get('severidad', '')), str(p.get('severidad', '')))}): {p.get('problema', '')}"
            for p in problematicas
            if isinstance(p, dict)
        ]
        lines += [""]
    if mode == "jd_directed" and gaps:
        lines += ["Brechas detectadas:"]
        lines += [f"- {g}" for g in gaps]
        lines += [""]
    recomendaciones = result_json.get("recomendaciones") or []
    if recomendaciones:
        lines += ["Recomendaciones:"]
        lines += [f"- {r}" for r in recomendaciones]
        lines += [""]
    reasoning = result_json.get("reasoning")
    if reasoning:
        lines += ["Detalle del análisis:", str(reasoning), ""]
    text_body = "\n".join(lines)

    return subject, html_body, text_body


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


async def send_audit_result_email(
    email_to: str,
    result_json: dict[str, Any],
    *,
    send_fn: SendEmailFn | None = None,
) -> bool:
    """
    Send the stored audit result to ``email_to``. Best-effort, never raises.

    Args:
        email_to:   Destination address (already validated by the endpoint).
        result_json: The ``audit_uploads.audit_result_json`` payload.
        send_fn:    Injectable async send function. Defaults to
                    ``email_service.send_email_async`` (looked up at call
                    time so tests can patch it on the module).

    Returns:
        ``True`` when the provider accepted the email, ``False`` otherwise.
    """
    if not email_to or not result_json:
        _logger.warning("audit_email_skipped_missing_payload", email_to=email_to)
        return False

    if send_fn is None:
        send_fn = email_service.send_email_async

    try:
        subject, html_body, text_body = build_audit_result_email(result_json)
        return await send_fn(to=email_to, subject=subject, html_body=html_body, text_body=text_body)
    except Exception as exc:  # noqa: BLE001 — the caller's request must survive
        _logger.error(
            "audit_email_send_crashed",
            email_to=email_to,
            error=str(exc)[:200],
            error_type=type(exc).__name__,
        )
        return False
