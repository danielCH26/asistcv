"""
Mock billing provider for local development and testing.

No DB, no secrets, no external HTTP. Provides deterministic in-memory state
so the billing adapter contract is exercisable without any provider credentials.

Slice 1 — feat/pasarela-pagos-56.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from app.services.billing_provider import (
    BillingProvider,
    CheckoutSession,
    CheckoutUrls,
    SubStatus,
    WebhookEvent,
)

# Module-level in-memory subscription state (not persisted across restarts).
# Maps user_id → subscription dict.
_MOCK_SUBSCRIPTIONS: dict[int, dict] = {}


class MockProvider(BillingProvider):
    """In-memory billing provider for dev and tests."""

    provider_id: ClassVar[str] = "mock"

    async def create_checkout(
        self,
        plan: dict,
        user: dict,
        return_urls: CheckoutUrls,
        *,
        idempotency_key: str | None = None,
    ) -> CheckoutSession:
        """Return a deterministic mock checkout URL."""
        plan_id = plan.get("plan_id", plan.get("tier", "unknown"))
        user_id = user.get("id", 0)
        session_id = f"mock_cs_{user_id}_{plan_id}_{int(datetime.now(UTC).timestamp())}"
        checkout_url = (
            f"https://checkout.mock/session"
            f"?session_id={session_id}"
            f"&plan={plan_id}"
            f"&user={user_id}"
            f"&success={return_urls.success_url}"
            + (f"&idempotency_key={idempotency_key}" if idempotency_key else "")
        )
        return CheckoutSession(
            checkout_url=checkout_url,
            session_id=session_id,
            provider_id=self.provider_id,
        )

    async def handle_webhook(
        self,
        payload: bytes,
        signature: str,
        headers: dict[str, str],
    ) -> WebhookEvent:
        """Parse a mock webhook payload.

        The mock payload is a JSON dict with at minimum an ``event_type`` field.
        Example::

            {
              "event_type": "subscription_created",
              "user_id": 42,
              "plan_id": "job_seeker_monthly",
              "provider_id": "mock"
            }

        Any other shape is treated as a generic ``webhook_received`` event
        with the raw payload available in ``raw``.

        Raises:
            ValueError: The payload is not valid JSON.
        """
        try:
            data = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Invalid mock webhook payload: {exc}") from exc

        event_type = data.get("event_type", "webhook_received")
        user_id = data.get("user_id")
        plan_id = data.get("plan_id")
        provider_id = data.get("provider_id", self.provider_id)

        # If this is a subscription_created event, update in-memory state
        if event_type == "subscription_created" and user_id is not None:
            _MOCK_SUBSCRIPTIONS[int(user_id)] = {
                "plan_id": plan_id or "free",
                "status": "active",
                "cancel_at_period_end": False,
                "provider_customer_id": f"mock_cus_{user_id}",
                "provider_subscription_id": f"mock_sub_{user_id}",
            }

        return WebhookEvent(
            event_type=event_type,
            user_id=int(user_id) if user_id is not None else None,
            plan_id=plan_id,
            provider_id=provider_id,
            raw=data,
        )

    async def get_subscription_status(self, user_id: int) -> SubStatus:
        """Return the in-memory subscription for the user, or a free-tier default."""
        sub = _MOCK_SUBSCRIPTIONS.get(user_id)
        if sub:
            return SubStatus(
                plan_id=sub["plan_id"],
                status=sub["status"],
                current_period_end=datetime.now(UTC) + timedelta(days=30),
                provider_customer_id=sub.get("provider_customer_id"),
                provider_subscription_id=sub.get("provider_subscription_id"),
                cancel_at_period_end=sub.get("cancel_at_period_end", False),
            )

        return SubStatus(
            plan_id="free",
            status="active",
            current_period_end=None,
            provider_customer_id=None,
            provider_subscription_id=None,
            cancel_at_period_end=False,
        )

    async def cancel_subscription(self, user_id: int) -> None:
        """Mark the user's subscription as canceled (idempotent)."""
        if user_id in _MOCK_SUBSCRIPTIONS:
            _MOCK_SUBSCRIPTIONS[user_id]["status"] = "canceled"
            _MOCK_SUBSCRIPTIONS[user_id]["cancel_at_period_end"] = False
        # No-op for unknown users — idempotent by contract.

    def supports_country(self, country_code: str) -> bool:
        """Mock provider supports every country."""
        return True
