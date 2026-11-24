"""
Tests for audit_email — re-sending the anonymous audit result by email.

Three test layers (matching the offer_email contract):
1. Pure builder: ``build_audit_result_email(result_json) → (subject, html, text)``
2. ``send_audit_result_email`` with injected send_fn (no I/O)
3. Integration: patch ``send_email_async`` from email_service
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.services import audit_email

_CV_ONLY_RESULT = {
    "mode": "cv_only",
    "score": 68,
    "problematicas": [
        {"seccion": "Experiencia", "problema": "Logros sin cuantificar", "severidad": "high"},
        {"seccion": "Educación", "problema": "Fechas inconsistentes", "severidad": "medium"},
    ],
    "recomendaciones": ["Cuantificá logros con métricas", "Unificá el formato de fechas"],
    "fortalezas": ["Buena estructura general"],
    "strengths": ["Buena estructura general"],
    "gaps": ["Logros sin cuantificar", "Fechas inconsistentes"],
    "energy_level": "medium",
    "reasoning": "Auditoría de calidad del CV: 2 problemáticas detectadas.",
}

_JD_RESULT = {
    "mode": "jd_directed",
    "score": 80,
    "strengths": ["Strong Python skills"],
    "gaps": ["Limited leadership"],
    "energy_level": "high",
    "reasoning": "Solid match overall.",
}


# ---------------------------------------------------------------------------
# Pure builder tests
# ---------------------------------------------------------------------------


class TestBuildAuditResultEmail:
    """Pure builder — no I/O, no mocks."""

    def test_cv_only_subject_carries_score(self):
        subject, _, _ = audit_email.build_audit_result_email(_CV_ONLY_RESULT)
        assert "68" in subject
        assert "auditoría" in subject.lower()

    def test_jd_subject_mentions_offer_comparison(self):
        subject, _, _ = audit_email.build_audit_result_email(_JD_RESULT)
        assert "80" in subject
        assert "oferta" in subject.lower()

    def test_deterministic_same_input_same_output(self):
        first = audit_email.build_audit_result_email(_CV_ONLY_RESULT)
        second = audit_email.build_audit_result_email(_CV_ONLY_RESULT)
        assert first == second

    def test_cv_only_html_lists_problematicas_and_recomendaciones(self):
        _, html, _ = audit_email.build_audit_result_email(_CV_ONLY_RESULT)
        assert "Logros sin cuantificar" in html
        assert "Experiencia" in html
        assert "alta" in html  # severidad high traducida
        assert "Cuantificá logros con métricas" in html
        assert "Buena estructura general" in html

    def test_jd_html_lists_strengths_and_gaps(self):
        _, html, _ = audit_email.build_audit_result_email(_JD_RESULT)
        assert "Strong Python skills" in html
        assert "Limited leadership" in html
        assert "Solid match overall." in html
        assert "Recomendaciones" not in html  # jd_directed no tiene ese bloque

    def test_text_body_mirrors_html_content(self):
        _, _, text = audit_email.build_audit_result_email(_CV_ONLY_RESULT)
        assert "68/100" in text
        assert "Logros sin cuantificar" in text
        assert "Cuantificá logros con métricas" in text

    def test_llm_strings_are_html_escaped(self):
        result = {
            **_JD_RESULT,
            "strengths": ["<script>alert('x')</script>"],
        }
        _, html, _ = audit_email.build_audit_result_email(result)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_unknown_keys_are_ignored(self):
        result = {**_CV_ONLY_RESULT, "captured_email": "visitor@example.com"}
        subject, html, text = audit_email.build_audit_result_email(result)
        assert "visitor@example.com" not in html
        assert "visitor@example.com" not in text
        assert "68" in subject

    def test_empty_payload_still_builds(self):
        subject, html, text = audit_email.build_audit_result_email({})
        assert html
        assert text
        assert "0/100" in subject


# ---------------------------------------------------------------------------
# send_audit_result_email with injected send_fn (no I/O)
# ---------------------------------------------------------------------------


class TestSendAuditResultEmailInjected:
    """send_audit_result_email with a mock send_fn — no I/O."""

    async def test_sends_with_built_content(self):
        calls: list[dict] = []

        async def send_fn(to, subject, html_body, text_body=None):
            calls.append(
                {"to": to, "subject": subject, "html": html_body, "text": text_body}
            )
            return True

        ok = await audit_email.send_audit_result_email(
            "visitor@example.com", _CV_ONLY_RESULT, send_fn=send_fn
        )

        assert ok is True
        assert len(calls) == 1
        assert calls[0]["to"] == "visitor@example.com"
        assert "68" in calls[0]["subject"]
        assert "Logros sin cuantificar" in calls[0]["html"]
        assert calls[0]["text"] is not None

    async def test_send_fn_false_propagates_as_false(self):
        async def send_fn(to, subject, html_body, text_body=None):
            return False

        ok = await audit_email.send_audit_result_email(
            "visitor@example.com", _JD_RESULT, send_fn=send_fn
        )
        assert ok is False

    async def test_send_fn_exception_is_swallowed(self):
        """A crash inside the send path returns False — never raises."""

        async def send_fn(to, subject, html_body, text_body=None):
            raise RuntimeError("provider exploded")

        ok = await audit_email.send_audit_result_email(
            "visitor@example.com", _JD_RESULT, send_fn=send_fn
        )
        assert ok is False

    async def test_missing_email_or_payload_is_no_op(self):
        sent: list[str] = []

        async def send_fn(to, subject, html_body, text_body=None):
            sent.append(to)
            return True

        assert await audit_email.send_audit_result_email("", _JD_RESULT, send_fn=send_fn) is False
        assert await audit_email.send_audit_result_email("x@y.com", {}, send_fn=send_fn) is False
        assert sent == []


# ---------------------------------------------------------------------------
# Integration: patch send_email_async from email_service
# ---------------------------------------------------------------------------


class TestSendAuditResultEmailIntegration:
    """Full stack with email_service mocked — exercises the real wiring."""

    async def test_defaults_to_email_service_send_email_async(self):
        captured: dict = {}

        async def _capture(to, subject, html_body, text_body=None):
            captured["to"] = to
            captured["subject"] = subject
            captured["html_body"] = html_body
            return True

        with patch(
            "app.services.email_service.send_email_async", _capture
        ):
            ok = await audit_email.send_audit_result_email(
                "visitor@example.com", _CV_ONLY_RESULT
            )

        assert ok is True
        assert captured["to"] == "visitor@example.com"
        assert "68" in captured["subject"]
        assert "Cuantificá logros con métricas" in captured["html_body"]

    async def test_provider_failure_returns_false(self):
        with patch(
            "app.services.email_service.send_email_async",
            AsyncMock(return_value=False),
        ):
            ok = await audit_email.send_audit_result_email(
                "visitor@example.com", _JD_RESULT
            )
        assert ok is False
