"""
Lemon Squeezy API client — issue #56, slice 2.

Wraps https://api.lemonsqueezy.com/v1 using httpx.
Error taxonomy mirrors ``offer_search_client.py`` (Tavily):
  - ``LemonSqueezyError`` (base, carries status_code)
  - ``LemonSqueezyAuthError`` (401)
  - ``LemonSqueezyRateLimitError`` (429, carries retry_after from Retry-After header)
  - ``LemonSqueezyTimeoutError``
  - ``LemonSqueezyConnectionError``

The client is a plain httpx wrapper; it does not import or depend on any
billing-provider layer. The provider layer (``LemonSqueezyProvider``) is
responsible for mapping plan IDs → variant IDs and normalising the
JSON:API response shape to the ``CheckoutSession`` dataclass.
"""

from __future__ import annotations

from typing import NoReturn

import httpx

_LS_BASE_URL = "https://api.lemonsqueezy.com/v1"
_DEFAULT_TIMEOUT = 12.0  # seconds


# === Error taxonomy ===

class LemonSqueezyError(Exception):
    """Base error from the Lemon Squeezy API."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class LemonSqueezyAuthError(LemonSqueezyError):
    """API key invalid or missing (401)."""

    def __init__(
        self,
        message: str = "Lemon Squeezy API key inválida",
        status_code: int = 401,
    ) -> None:
        super().__init__(message, status_code=status_code)


class LemonSqueezyRateLimitError(LemonSqueezyError):
    """Rate limit from Lemon Squeezy (429)."""

    def __init__(
        self,
        message: str = "Límite de llamadas a Lemon Squeezy alcanzado",
        status_code: int = 429,
        retry_after: int | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, status_code=status_code)


class LemonSqueezyTimeoutError(LemonSqueezyError):
    """Timeout communicating with Lemon Squeezy."""

    def __init__(self) -> None:
        super().__init__("Timeout al comunicarse con Lemon Squeezy")


class LemonSqueezyConnectionError(LemonSqueezyError):
    """Connection error with Lemon Squeezy."""

    def __init__(self, message: str = "No se pudo conectar con Lemon Squeezy") -> None:
        super().__init__(message)


# === Client ===

class LemonSqueezyClient:
    """Async client for the Lemon Squeezy REST API (v1)."""

    def __init__(
        self,
        api_key: str,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=_LS_BASE_URL,
                timeout=self._timeout,
                transport=self._transport,
            )
        return self._client

    @staticmethod
    def _raise_for_status_error(exc: httpx.HTTPStatusError) -> NoReturn:
        status_code = exc.response.status_code
        if status_code == 401:
            raise LemonSqueezyAuthError() from None
        if status_code == 429:
            retry_after: int | None = None
            raw = exc.response.headers.get("Retry-After")
            if raw is not None:
                try:
                    retry_after = int(raw)
                except ValueError:
                    retry_after = None
            raise LemonSqueezyRateLimitError(retry_after=retry_after) from None
        raise LemonSqueezyError(
            f"Lemon Squeezy error: {status_code}",
            status_code=status_code,
        )

    # --- Public API -----------------------------------------------------------

    async def create_checkout(
        self,
        *,
        store_id: str,
        variant_id: str,
        custom: dict[str, str],
        test_mode: bool,
        redirect_url: str | None = None,
    ) -> dict:
        """Create a hosted checkout session.

        POST /checkouts  (JSON:API body)

        Returns:
            ``{"checkout_url": ..., "checkout_id": ...}``
        """
        client = await self._get_client()

        checkout_options: dict[str, object] = {"embed": False}
        if redirect_url:
            checkout_options["redirect_url"] = redirect_url

        body: dict[str, object] = {
            "data": {
                "type": "checkouts",
                "attributes": {
                    "custom": custom,
                    "checkout_options": checkout_options,
                    "test_mode": test_mode,
                    "preview": False,
                },
                "relationships": {
                    "store": {"data": {"type": "stores", "id": store_id}},
                    "variant": {"data": {"type": "variants", "id": variant_id}},
                },
            }
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
        }

        try:
            response = await client.post("/checkouts", json=body, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e)
        except httpx.TimeoutException:
            raise LemonSqueezyTimeoutError() from None
        except httpx.ConnectError as e:
            raise LemonSqueezyConnectionError(str(e)) from None

        data = response.json()
        return {
            "checkout_url": data["data"]["attributes"]["url"],
            "checkout_id": data["data"]["id"],
        }

    async def get_subscription(self, subscription_id: str) -> dict:
        """Fetch a subscription's attributes.

        GET /subscriptions/{id}

        Returns:
            ``{"status": ..., "renews_at": ..., "ends_at": ..., "created_at": ...}``
        """
        client = await self._get_client()

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/vnd.api+json",
        }

        try:
            response = await client.get(
                f"/subscriptions/{subscription_id}",
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e)
        except httpx.TimeoutException:
            raise LemonSqueezyTimeoutError() from None
        except httpx.ConnectError as e:
            raise LemonSqueezyConnectionError(str(e)) from None

        data = response.json()
        attrs = data["data"]["attributes"]
        return {
            "status": attrs.get("status"),
            "renews_at": attrs.get("renews_at"),
            "ends_at": attrs.get("ends_at"),
            "created_at": attrs.get("created_at"),
        }

    async def cancel_subscription(self, subscription_id: str) -> dict:
        """Cancel a subscription.

        PATCH /subscriptions/{id}

        Returns:
            Same normalised attributes shape as ``get_subscription``.
        """
        client = await self._get_client()

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
        }

        body: dict[str, object] = {
            "data": {
                "type": "subscriptions",
                "id": subscription_id,
                "attributes": {"cancelled": True},
            }
        }

        try:
            response = await client.patch(
                f"/subscriptions/{subscription_id}",
                json=body,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e)
        except httpx.TimeoutException:
            raise LemonSqueezyTimeoutError() from None
        except httpx.ConnectError as e:
            raise LemonSqueezyConnectionError(str(e)) from None

        data = response.json()
        attrs = data["data"]["attributes"]
        return {
            "status": attrs.get("status"),
            "renews_at": attrs.get("renews_at"),
            "ends_at": attrs.get("ends_at"),
            "created_at": attrs.get("created_at"),
        }

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> LemonSqueezyClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
