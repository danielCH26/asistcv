"""
Tests for LemonSqueezyClient — issue #56, slice 2.

Uses ``httpx.MockTransport`` for deterministic, DB-free HTTP mocking.
"""

import json
from typing import Any

import httpx
import pytest

from app.services.lemon_squeezy_client import (
    LemonSqueezyAuthError,
    LemonSqueezyClient,
    LemonSqueezyError,
    LemonSqueezyRateLimitError,
    LemonSqueezyTimeoutError,
)


def _mock_client(handler: Any) -> LemonSqueezyClient:
    """Build a LemonSqueezyClient wired to a MockTransport."""
    return LemonSqueezyClient(
        api_key="test_api_key",
        transport=httpx.MockTransport(handler),
    )


# ---------------------------------------------------------------------------
# Helper: happy-path response builders
# ---------------------------------------------------------------------------


def _checkout_response(checkout_id: str = "123", checkout_url: str = "https://checkout.lemonsqueezy.com/checkout/hosted/abc") -> dict:
    return {
        "data": {
            "id": checkout_id,
            "type": "checkouts",
            "attributes": {
                "url": checkout_url,
                "status": "active",
            },
        },
    }


def _subscription_response(
    status: str = "active",
    renews_at: str | None = None,
    ends_at: str | None = None,
    created_at: str | None = None,
) -> dict:
    return {
        "data": {
            "id": "sub_abc",
            "type": "subscriptions",
            "attributes": {
                "status": status,
                "renews_at": renews_at,
                "ends_at": ends_at,
                "created_at": created_at,
            },
        },
    }


# ---------------------------------------------------------------------------
# create_checkout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_checkout_happy_path():
    """create_checkout sends JSON:API body and returns normalised url+id."""

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # Verify Authorization header
        assert request.headers.get("Authorization") == "Bearer test_api_key"
        assert request.headers.get("Accept") == "application/vnd.api+json"

        # Verify JSON:API structure
        data = body["data"]
        assert data["type"] == "checkouts"
        attrs = data["attributes"]
        assert attrs["custom"] == {"user_id": "42", "plan_id": "job_seeker_monthly"}
        assert attrs["test_mode"] is True
        assert attrs["checkout_options"]["embed"] is False
        assert attrs["checkout_options"]["redirect_url"] == "https://app.example.com/ok"

        rels = data["relationships"]
        assert rels["store"]["data"]["id"] == "store_1"
        assert rels["variant"]["data"]["id"] == "variant_1"

        return httpx.Response(200, json=_checkout_response())

    client = _mock_client(handler)
    result = await client.create_checkout(
        store_id="store_1",
        variant_id="variant_1",
        custom={"user_id": "42", "plan_id": "job_seeker_monthly"},
        test_mode=True,
        redirect_url="https://app.example.com/ok",
    )

    assert result["checkout_url"] == "https://checkout.lemonsqueezy.com/checkout/hosted/abc"
    assert result["checkout_id"] == "123"


@pytest.mark.asyncio
async def test_create_checkout_without_redirect_url():
    """create_checkout omits redirect_url from checkout_options when not supplied."""

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        attrs = body["data"]["attributes"]
        assert "redirect_url" not in attrs["checkout_options"]
        return httpx.Response(200, json=_checkout_response())

    client = _mock_client(handler)
    await client.create_checkout(
        store_id="store_1",
        variant_id="variant_1",
        custom={},
        test_mode=False,
        redirect_url=None,
    )


# ---------------------------------------------------------------------------
# get_subscription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_subscription_happy_path():
    """get_subscription returns normalised status/renews_at/ends_at/created_at."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer test_api_key"
        assert request.headers.get("Accept") == "application/vnd.api+json"
        assert request.url.path == "/v1/subscriptions/sub_abc"
        return httpx.Response(
            200,
            json=_subscription_response(
                status="active",
                renews_at="2025-07-01T00:00:00Z",
                ends_at=None,
                created_at="2025-06-01T00:00:00Z",
            ),
        )

    client = _mock_client(handler)
    result = await client.get_subscription("sub_abc")

    assert result["status"] == "active"
    assert result["renews_at"] == "2025-07-01T00:00:00Z"
    assert result["ends_at"] is None
    assert result["created_at"] == "2025-06-01T00:00:00Z"


@pytest.mark.asyncio
async def test_get_subscription_canceled():
    """get_subscription returns ends_at for a canceled subscription."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_subscription_response(
                status="canceled",
                renews_at="2025-07-01T00:00:00Z",
                ends_at="2025-07-01T00:00:00Z",
                created_at="2025-06-01T00:00:00Z",
            ),
        )

    client = _mock_client(handler)
    result = await client.get_subscription("sub_abc")
    assert result["status"] == "canceled"
    assert result["ends_at"] == "2025-07-01T00:00:00Z"


# ---------------------------------------------------------------------------
# cancel_subscription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_subscription_happy_path():
    """cancel_subscription PATCHes with cancelled=True and returns normalised attrs."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert request.headers.get("Authorization") == "Bearer test_api_key"
        assert request.headers.get("Content-Type") == "application/vnd.api+json"
        body = json.loads(request.content)
        assert body["data"]["attributes"]["cancelled"] is True
        return httpx.Response(
            200,
            json=_subscription_response(
                status="canceled",
                ends_at="2025-07-01T00:00:00Z",
            ),
        )

    client = _mock_client(handler)
    result = await client.cancel_subscription("sub_abc")

    assert result["status"] == "canceled"
    assert result["ends_at"] == "2025-07-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_raises_auth_error():
    """401 response raises LemonSqueezyAuthError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    client = _mock_client(handler)
    with pytest.raises(LemonSqueezyAuthError) as exc_info:
        await client.create_checkout(
            store_id="s", variant_id="v", custom={}, test_mode=True
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_429_with_retry_after_header_raises_rate_limit_error():
    """429 with Retry-After header carries the parsed retry_after value."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": "rate limited"},
            headers={"Retry-After": "42"},
        )

    client = _mock_client(handler)
    with pytest.raises(LemonSqueezyRateLimitError) as exc_info:
        await client.create_checkout(
            store_id="s", variant_id="v", custom={}, test_mode=True
        )
    assert exc_info.value.retry_after == 42
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_429_without_retry_after_header():
    """429 without Retry-After header carries None for retry_after."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    client = _mock_client(handler)
    with pytest.raises(LemonSqueezyRateLimitError) as exc_info:
        await client.create_checkout(
            store_id="s", variant_id="v", custom={}, test_mode=True
        )
    assert exc_info.value.retry_after is None


@pytest.mark.asyncio
async def test_500_raises_generic_error_with_status_code():
    """500 response raises LemonSqueezyError with status_code=500 (no body leak)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal server error details"})

    client = _mock_client(handler)
    with pytest.raises(LemonSqueezyError) as exc_info:
        await client.create_checkout(
            store_id="s", variant_id="v", custom={}, test_mode=True
        )
    assert exc_info.value.status_code == 500
    # Do NOT include the response body
    assert "500" in exc_info.value.message
    assert "internal server error details" not in exc_info.value.message


@pytest.mark.asyncio
async def test_timeout_raises_timeout_error():
    """Transport-level timeout raises LemonSqueezyTimeoutError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection timeout")

    client = _mock_client(handler)
    with pytest.raises(LemonSqueezyTimeoutError):
        await client.create_checkout(
            store_id="s", variant_id="v", custom={}, test_mode=True
        )


# ---------------------------------------------------------------------------
# Context manager / close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_manager_enter_exit():
    """Client supports async context manager protocol."""
    async with _mock_client(lambda r: httpx.Response(200, json={})) as client:
        assert isinstance(client, LemonSqueezyClient)

    # close() is called on __aexit__; verify it doesn't raise
