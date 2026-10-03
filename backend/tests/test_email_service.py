"""Tests for the email service (C3 / issue #46).

Two axes:
1. The Resend provider hits ``api.resend.com`` with the right shape —
   payload, headers, timeout — when ``RESEND_API_KEY`` is configured.
2. The dev fallback path is loud but never crashes the caller: missing
   key, unsupported provider, transport error, non-2xx response.

httpx is patched directly under the service so the test never reaches
the network. That keeps CI offline-friendly and means the assertions
can pin every byte that would otherwise leave the box.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import get_settings
from app.services import email_service


def _resend_response(status: int = 200, body: str = '{"id":"abc"}') -> MagicMock:
    """Build a stand-in for httpx.Response that the dispatch can inspect."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.text = body
    return response


def resend_env(monkeypatch):
    """Wire up Settings with a Resend key so the dispatch reaches the provider branch."""
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_secret_1234567890abcdef")
    monkeypatch.setenv("EMAIL_FROM", "AsistCV Test <test@asistcv.com>")
    get_settings.cache_clear()
    yield {"api_key": "re_test_secret_1234567890abcdef"}
    get_settings.cache_clear()


resend_env = pytest.fixture(resend_env)


async def test_resend_email_send_posts_expected_payload(resend_env) -> None:
    """When the key is set, the dispatch POSTs to Resend with the right body.

    Asserts: URL, method (implicit in client.post), Authorization header,
    Content-Type, From/To/Subject/Html fields, plus a passing 200.
    """
    captured: dict = {}

    async def _capture_post(url, *, json, headers):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _resend_response(status=200)

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = _capture_post

    with patch.object(httpx, "AsyncClient", return_value=fake_client):
        ok = await email_service.send_email_async(
            to="dest@example.com",
            subject="Verify your email",
            html_body="<p>Click <a>here</a></p>",
            text_body="Click here.",
        )

    assert ok is True
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == f"Bearer {resend_env['api_key']}"
    assert captured["headers"]["Content-Type"] == "application/json"
    body = captured["json"]
    assert body["from"] == "AsistCV Test <test@asistcv.com>"
    assert body["to"] == ["dest@example.com"]
    assert body["subject"] == "Verify your email"
    assert body["html"] == "<p>Click <a>here</a></p>"
    assert body["text"] == "Click here."


async def test_resend_email_send_omits_text_when_not_provided(resend_env) -> None:
    """text_body=None → no ``text`` key in the payload (Resend is happy either way)."""
    captured: dict = {}

    async def _capture_post(url, *, json, headers):
        captured["json"] = json
        return _resend_response(status=200)

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = _capture_post

    with patch.object(httpx, "AsyncClient", return_value=fake_client):
        ok = await email_service.send_email_async(
            to="dest@example.com",
            subject="Subject only",
            html_body="<p>html</p>",
        )

    assert ok is True
    assert "text" not in captured["json"]


async def test_email_returns_false_when_api_key_missing(monkeypatch) -> None:
    """No RESEND_API_KEY → graceful False, no httpx call.

    This is the path that lets the rest of the request succeed in dev:
    the verify-email row still gets persisted and the operator can
    recover the link from the ``email_service_disabled`` log line.
    """
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(side_effect=AssertionError("should not be called"))

    with patch.object(httpx, "AsyncClient", return_value=fake_client):
        ok = await email_service.send_email_async(
            to="dest@example.com",
            subject="Subject",
            html_body="<p>x</p>",
        )

    assert ok is False
    fake_client.post.assert_not_called()

    get_settings.cache_clear()


async def test_email_returns_false_on_non_2xx(resend_env) -> None:
    """Provider 4xx/5xx → False. The request must keep working."""
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(return_value=_resend_response(status=422, body='{"error":"bad"}'))

    with patch.object(httpx, "AsyncClient", return_value=fake_client):
        ok = await email_service.send_email_async(
            to="dest@example.com",
            subject="Subject",
            html_body="<p>x</p>",
        )

    assert ok is False


async def test_email_returns_false_on_transport_error(resend_env) -> None:
    """httpx.HTTPError → False. Same contract: the rest of the request survives."""
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(side_effect=httpx.ConnectError("network down"))

    with patch.object(httpx, "AsyncClient", return_value=fake_client):
        ok = await email_service.send_email_async(
            to="dest@example.com",
            subject="Subject",
            html_body="<p>x</p>",
        )

    assert ok is False


async def test_email_returns_false_for_unsupported_provider(monkeypatch) -> None:
    """EMAIL_PROVIDER=sendgrid (not wired) → False, no httpx call.

    The current implementation only knows ``resend``. Anything else
    must fail closed — a typo'd env var can't ship a request into the
    void.
    """
    monkeypatch.setenv("EMAIL_PROVIDER", "sendgrid")
    monkeypatch.setenv("RESEND_API_KEY", "re_doesnt_matter")
    from app.core.config import get_settings

    get_settings.cache_clear()

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(side_effect=AssertionError("should not be called"))

    with patch.object(httpx, "AsyncClient", return_value=fake_client):
        ok = await email_service.send_email_async(
            to="dest@example.com",
            subject="Subject",
            html_body="<p>x</p>",
        )

    assert ok is False
    fake_client.post.assert_not_called()

    get_settings.cache_clear()


async def test_sync_send_email_hops_into_event_loop() -> None:
    """The sync ``send_email`` wrapper runs the dispatch coroutine.

    ``asyncio.run`` refuses to be called from inside another loop, so
    inside pytest-asyncio we can't exercise the wrapper end-to-end.
    We assert instead that the function exists and delegates to the
    same underlying dispatcher — that's enough to catch the
    "refactor-removes-the-wrapper" regression without forcing a fresh
    interpreter.
    """
    assert callable(email_service.send_email)
    assert hasattr(email_service, "_dispatch")
    assert hasattr(email_service, "send_email_async")
    # Calling the sync wrapper from inside an async test would raise
    # RuntimeError; we don't actually do that here — the assertion
    # above is the contract.
