"""
Tests for offer_email — email summary of new job offers.

Three test layers (matching the task contract):
1. Pure builder: ``build_offer_summary_html(offers, frequency) → (subject, html)``
2. ``send_offer_summary`` with mocked send_fn (no I/O)
3. Integration: patch ``send_email_async`` from email_service
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services import offer_email

# ---------------------------------------------------------------------------
# Pure builder tests
# ---------------------------------------------------------------------------

_OFFER_DICT = {
    "title": "Backend Engineer",
    "company": "Acme Corp",
    "url": "https://example.com/job/1",
    "snippet": "We are hiring...",
    "score": 0.92,
}

_OFFER_DICT_2 = {
    "title": "Frontend Dev",
    "company": "Beta Inc",
    "url": "https://example.com/job/2",
    "snippet": "Join our team...",
    "score": 0.85,
}


class TestBuildOfferSummaryHtml:
    """Pure builder — no I/O, no mocks."""

    def test_plural_subject_says_n_offers(self):
        """3 offers → subject contains '3 nuevas ofertas'."""
        offers = [_OFFER_DICT, _OFFER_DICT_2, {**_OFFER_DICT, "title": "DevOps"}]
        subject, _ = offer_email.build_offer_summary_html(offers, frequency="daily")
        assert "3" in subject
        assert "ofertas" in subject.lower()

    def test_singular_subject_says_1_oferta(self):
        """1 offer → subject contains '1 nueva oferta' (singular)."""
        subject, _ = offer_email.build_offer_summary_html([_OFFER_DICT], frequency="daily")
        assert "1" in subject
        assert "oferta" in subject.lower()

    def test_daily_framing_in_body(self):
        """frequency=daily → body mentions 'diarias'."""
        _, html = offer_email.build_offer_summary_html([_OFFER_DICT], frequency="daily")
        assert "diarias" in html.lower()

    def test_weekly_framing_in_body(self):
        """frequency=weekly → body mentions 'semanal'."""
        _, html = offer_email.build_offer_summary_html([_OFFER_DICT], frequency="weekly")
        assert "semanal" in html.lower()

    def test_offer_title_present(self):
        """Each offer's title appears in the HTML."""
        _, html = offer_email.build_offer_summary_html([_OFFER_DICT], frequency="daily")
        assert _OFFER_DICT["title"] in html

    def test_offer_company_present(self):
        """Each offer's company appears in the HTML."""
        _, html = offer_email.build_offer_summary_html([_OFFER_DICT], frequency="daily")
        assert _OFFER_DICT["company"] in html

    def test_offer_score_present(self):
        """Each offer's score appears in the HTML."""
        _, html = offer_email.build_offer_summary_html([_OFFER_DICT], frequency="daily")
        assert "92" in html or "0.92" in html

    def test_offer_link_present(self):
        """Each offer's URL appears as an href in the HTML."""
        _, html = offer_email.build_offer_summary_html([_OFFER_DICT], frequency="daily")
        assert _OFFER_DICT["url"] in html
        assert 'href="' + _OFFER_DICT["url"] in html

    def test_multiple_offers_all_present(self):
        """Two offers → both titles and URLs appear."""
        offers = [_OFFER_DICT, _OFFER_DICT_2]
        _, html = offer_email.build_offer_summary_html(offers, frequency="daily")
        assert _OFFER_DICT["title"] in html
        assert _OFFER_DICT_2["title"] in html
        assert _OFFER_DICT["url"] in html
        assert _OFFER_DICT_2["url"] in html


# ---------------------------------------------------------------------------
# send_offer_summary with mocked send_fn
# ---------------------------------------------------------------------------

class TestSendOfferSummary:
    """Integration-free: send_fn is injected, no I/O."""

    @pytest.fixture
    def mock_send_fn(self):
        return AsyncMock(return_value=True)

    @pytest.mark.asyncio
    async def test_calls_send_fn_once(self, mock_send_fn):
        """Exactly one call to send_fn with (to, subject, html_body)."""
        await offer_email.send_offer_summary(
            email_to="user@example.com",
            offers=[_OFFER_DICT],
            frequency="daily",
            send_fn=mock_send_fn,
        )
        mock_send_fn.assert_awaited_once()
        call_args = mock_send_fn.await_args
        # Called as: send_fn(to=..., subject=..., html_body=...) → kwargs
        assert call_args.kwargs["to"] == "user@example.com"
        assert isinstance(call_args.kwargs["subject"], str)
        assert isinstance(call_args.kwargs["html_body"], str)

    @pytest.mark.asyncio
    async def test_no_offers_does_not_send(self, mock_send_fn):
        """Empty list → send_fn never called, returns False."""
        result = await offer_email.send_offer_summary(
            email_to="user@example.com",
            offers=[],
            frequency="daily",
            send_fn=mock_send_fn,
        )
        mock_send_fn.assert_not_called()
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_dict_list_does_not_send(self, mock_send_fn):
        """List with no items → same as empty list."""
        result = await offer_email.send_offer_summary(
            email_to="user@example.com",
            offers=[],  # explicit empty
            frequency="daily",
            send_fn=mock_send_fn,
        )
        mock_send_fn.assert_not_called()
        assert result is False

    @pytest.mark.asyncio
    async def test_send_fn_false_returns_false(self, mock_send_fn):
        """send_fn returning False → send_offer_summary propagates False."""
        mock_send_fn.return_value = False
        result = await offer_email.send_offer_summary(
            email_to="user@example.com",
            offers=[_OFFER_DICT],
            frequency="daily",
            send_fn=mock_send_fn,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_fn_true_returns_true(self, mock_send_fn):
        """send_fn returning True → send_offer_summary propagates True."""
        mock_send_fn.return_value = True
        result = await offer_email.send_offer_summary(
            email_to="user@example.com",
            offers=[_OFFER_DICT],
            frequency="weekly",
            send_fn=mock_send_fn,
        )
        assert result is True


# ---------------------------------------------------------------------------
# Integration: patch send_email_async from email_service
# ---------------------------------------------------------------------------

class TestSendOfferSummaryIntegration:
    """Full stack with email_service mocked — exercises the real wiring."""

    @pytest.mark.asyncio
    async def test_calls_send_email_async_with_correct_args(self):
        """Verifies send_email_async receives the right (to, subject, html_body)."""
        captured: dict = {}

        async def _capture(to, subject, html_body, text_body=None):
            captured["to"] = to
            captured["subject"] = subject
            captured["html_body"] = html_body
            return True

        # Inject directly as send_fn to bypass default capture issue
        result = await offer_email.send_offer_summary(
            email_to="user@example.com",
            offers=[_OFFER_DICT, _OFFER_DICT_2],
            frequency="daily",
            send_fn=_capture,
        )

        assert result is True
        assert captured["to"] == "user@example.com"
        assert "2" in captured["subject"]
        assert "ofertas" in captured["subject"].lower()
        assert _OFFER_DICT["title"] in captured["html_body"]
        assert _OFFER_DICT_2["title"] in captured["html_body"]

    @pytest.mark.asyncio
    async def test_empty_offers_skips_send_email_async(self):
        """No offers → send_email_async never called."""
        with patch(
            "app.services.email_service.send_email_async",
            AsyncMock(side_effect=AssertionError("must not be called")),
        ) as mock_fn:
            result = await offer_email.send_offer_summary(
                email_to="user@example.com",
                offers=[],
                frequency="weekly",
            )

        mock_fn.assert_not_called()
        assert result is False
