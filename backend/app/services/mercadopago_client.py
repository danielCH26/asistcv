"""
Mercado Pago API client — issue #56, slice 3.

Wraps https://api.mercadopago.com using httpx.
Mercado Pago is the payment gateway of Mercado Libre for Latin America; for
Colombia it settles in COP through PSE / Nequi / Bancolombia / card.

Error taxonomy mirrors ``wompi_client.py``:
  - ``MercadoPagoError`` (base, carries status_code)
  - ``MercadoPagoAuthError`` (401/403)
  - ``MercadoPagoRateLimitError`` (429)
  - ``MercadoPagoTimeoutError``
  - ``MercadoPagoConnectionError``

Docs: https://www.mercadopago.com.co/developers/es/docs
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, NoReturn

import httpx

_MP_API_URL = "https://api.mercadopago.com"
_DEFAULT_TIMEOUT = 12.0  # seconds


# === Error taxonomy ===


class MercadoPagoError(Exception):
    """Base error from the Mercado Pago API."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class MercadoPagoAuthError(MercadoPagoError):
    """Access token invalid or missing (401/403)."""

    def __init__(
        self,
        message: str = "Token de Mercado Pago inválido",
        status_code: int = 401,
    ) -> None:
        super().__init__(message, status_code=status_code)


class MercadoPagoRateLimitError(MercadoPagoError):
    """Rate limit from Mercado Pago (429)."""

    def __init__(
        self,
        message: str = "Límite de llamadas a Mercado Pago alcanzado",
        status_code: int = 429,
        retry_after: int | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, status_code=status_code)


class MercadoPagoTimeoutError(MercadoPagoError):
    """Timeout communicating with Mercado Pago."""

    def __init__(self) -> None:
        super().__init__("Timeout al comunicarse con Mercado Pago")


class MercadoPagoConnectionError(MercadoPagoError):
    """Connection error with Mercado Pago."""

    def __init__(self, message: str = "No se pudo conectar con Mercado Pago") -> None:
        super().__init__(message)


# === Client ===


class MercadoPagoClient:
    """Async client for the Mercado Pago REST API."""

    def __init__(
        self,
        access_token: str,
        test_mode: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = _MP_API_URL,
    ) -> None:
        self._access_token = access_token
        self._test_mode = test_mode
        self._timeout = timeout
        self._transport = transport
        self._base_url = base_url
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            )
        return self._client

    @staticmethod
    def _raise_for_status_error(exc: httpx.HTTPStatusError) -> NoReturn:
        status_code = exc.response.status_code
        if status_code in (401, 403):
            raise MercadoPagoAuthError(status_code=status_code) from None
        if status_code == 429:
            retry_after: int | None = None
            raw = exc.response.headers.get("Retry-After")
            if raw is not None:
                try:
                    retry_after = int(raw)
                except ValueError:
                    retry_after = None
            raise MercadoPagoRateLimitError(retry_after=retry_after) from None
        try:
            error_data = exc.response.json()
            error_msg = (
                error_data.get("message")
                or (error_data.get("error") or {}).get("message")
                or str(exc)
            )
        except Exception:
            error_msg = str(exc)
        raise MercadoPagoError(
            f"MercadoPago error: {error_msg}",
            status_code=status_code,
        )

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # --- Webhook signature ---------------------------------------------------

    @staticmethod
    def verify_webhook_signature(
        *,
        data_id: str,
        request_id: str,
        timestamp: str,
        signature: str,
        secret: str,
    ) -> bool:
        """Verify the ``x-signature`` header of a Mercado Pago notification.

        Mercado Pago sends two headers:
          - ``x-signature``: ``ts=<unix>,v1=<hex hmac>``
          - ``x-request-id``: the request id echoed in the manifest

        The manifest is ``id:<data.id>;request-id:<x-request-id>;ts:<ts>;`` and
        the signature is the HMAC-SHA256 of that manifest with the webhook
        secret. When ``data.id`` is alphanumeric it must be lowercased, which
        is why the id is normalised here and not at the call site.
        """
        if not secret or not signature:
            return False

        # The id is lowercased when it is alphanumeric (MP's own rule).
        lowered = data_id.lower()
        manifest = f"id:{lowered};request-id:{request_id};ts:{timestamp};"

        expected = hmac.new(
            secret.encode(),
            manifest.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature.strip().lower())

    # --- Public API -----------------------------------------------------------

    async def create_preference(self, payload: dict[str, Any]) -> dict:
        """Create a Checkout Pro preference.

        POST /checkout/preferences

        Returns the preference dict with ``id``, ``init_point`` and
        ``sandbox_init_point`` (the test-mode checkout URL).
        """
        client = await self._get_client()

        try:
            response = await client.post(
                "/checkout/preferences",
                json=payload,
                headers=self._auth_headers(),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e)
        except httpx.TimeoutException:
            raise MercadoPagoTimeoutError() from None
        except httpx.ConnectError as e:
            raise MercadoPagoConnectionError(str(e)) from None

        return response.json()

    async def get_payment(self, payment_id: str) -> dict:
        """Fetch a payment by id.

        GET /v1/payments/{payment_id}

        Mercado Pago's notification body only carries the payment id, so the
        full payment (status, external_reference, metadata) has to be fetched.
        """
        client = await self._get_client()

        try:
            response = await client.get(
                f"/v1/payments/{payment_id}",
                headers=self._auth_headers(),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e)
        except httpx.TimeoutException:
            raise MercadoPagoTimeoutError() from None
        except httpx.ConnectError as e:
            raise MercadoPagoConnectionError(str(e)) from None

        return response.json()
