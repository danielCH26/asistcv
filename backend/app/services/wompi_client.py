"""
Wompi API client — issue #56, new provider.

Wraps https://checkout.wompi.co/v1 using httpx.
Wompi is the payment gateway of Grupo Bancolombia for Colombia (COP).

Error taxonomy mirrors ``lemon_squeezy_client.py``:
  - ``WompiError`` (base, carries status_code)
  - ``WompiAuthError`` (401)
  - ``WompiRateLimitError`` (429)
  - ``WompiTimeoutError``
  - ``WompiConnectionError``

Supported payment methods:
  - CARD (credit/debit)
  - PSE (ACH bank transfer)
  - NEQUI (digital wallet)
  - BANCOLOMBIA_TRANSFER

Docs: https://docs.wompi.co/docs/colombia/
"""

from __future__ import annotations

import hashlib
from typing import NoReturn

import httpx

# Wompi environments (updated: production uses production.wompi.co)
_WOMPI_PROD_URL = "https://production.wompi.co"
_WOMPI_SANDBOX_URL = "https://sandbox.wompi.co"
_DEFAULT_TIMEOUT = 12.0  # seconds


# === Error taxonomy ===

class WompiError(Exception):
    """Base error from the Wompi API."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class WompiAuthError(WompiError):
    """Private key invalid or missing (401)."""

    def __init__(
        self,
        message: str = "Wompi private key inválido",
        status_code: int = 401,
    ) -> None:
        super().__init__(message, status_code=status_code)


class WompiRateLimitError(WompiError):
    """Rate limit from Wompi (429)."""

    def __init__(
        self,
        message: str = "Límite de llamadas a Wompi alcanzado",
        status_code: int = 429,
        retry_after: int | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, status_code=status_code)


class WompiTimeoutError(WompiError):
    """Timeout communicating with Wompi."""

    def __init__(self) -> None:
        super().__init__("Timeout al comunicarse con Wompi")


class WompiConnectionError(WompiError):
    """Connection error with Wompi."""

    def __init__(self, message: str = "No se pudo conectar con Wompi") -> None:
        super().__init__(message)


# === Client ===

class WompiClient:
    """Async client for the Wompi REST API."""

    def __init__(
        self,
        private_key: str,
        public_key: str,
        acceptance_token: str | None = None,
        test_mode: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._private_key = private_key
        self._public_key = public_key
        self._acceptance_token = acceptance_token
        self._test_mode = test_mode
        self._timeout = timeout
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    @property
    def _base_url(self) -> str:
        return _WOMPI_SANDBOX_URL if self._test_mode else _WOMPI_PROD_URL

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
        if status_code == 401:
            raise WompiAuthError() from None
        if status_code == 429:
            retry_after: int | None = None
            raw = exc.response.headers.get("Retry-After")
            if raw is not None:
                try:
                    retry_after = int(raw)
                except ValueError:
                    retry_after = None
            raise WompiRateLimitError(retry_after=retry_after) from None
        # Try to extract error message from response
        try:
            error_data = exc.response.json()
            error_msg = error_data.get("error", {}).get("message", str(exc))
        except Exception:
            error_msg = str(exc)
        raise WompiError(
            f"Wompi error: {error_msg}",
            status_code=status_code,
        )

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._private_key}",
            "Content-Type": "application/json",
        }

    # --- Public API -----------------------------------------------------------

    async def get_acceptance_tokens(self) -> dict:
        """Fetch current acceptance tokens from Wompi.

        GET /v1/acceptance_tokens

        Returns:
            Dict with acceptance_token, personal_data_auth_token, etc.
        """
        client = await self._get_client()

        try:
            response = await client.get(
                "/v1/acceptance_tokens",
                headers=self._auth_headers(),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e)
        except httpx.TimeoutException:
            raise WompiTimeoutError() from None
        except httpx.ConnectError as e:
            raise WompiConnectionError(str(e)) from None

        data = response.json()
        return data.get("data", {})

    async def create_transaction(
        self,
        *,
        plan_id: str,
        user_id: int,
        user_email: str,
        amount_in_cents: int,  # Amount in COP cents
        currency: str = "COP",
        reference: str | None = None,
        acceptance_token: str | None = None,
        payment_method_type: str = "CARD",
        redirect_url: str | None = None,
        signature: str | None = None,
    ) -> dict:
        """Create a transaction with Wompi.

        POST /v1/transactions

        For CARD payments, include signature from Wompi Widget.
        For PSE/NEQUI, use type with redirect.

        Args:
            plan_id: Plan identifier (e.g., "job_seeker_monthly")
            user_id: Application user ID
            user_email: User email
            amount_in_cents: Amount in COP cents
            currency: Currency (COP)
            reference: Unique reference for idempotency
            acceptance_token: Acceptance token for legal compliance
            payment_method_type: CARD | PSE | NEQUI | BANCOLOMBIA_TRANSFER
            redirect_url: URL to redirect after payment
            signature: Signature from Wompi Widget (for card payments)

        Returns:
            Dict with {"id": ..., "redirect_url": ..., "status": ...}
        """
        client = await self._get_client()

        # Use provided acceptance token or fetch one
        token = acceptance_token or self._acceptance_token
        if not token:
            tokens_data = await self.get_acceptance_tokens()
            token = tokens_data.get("acceptance_token", "")

        # Build reference
        ref = reference or f"{user_id}_{plan_id}"

        body: dict[str, object] = {
            "amount_in_cents": amount_in_cents,
            "currency": currency,
            "signature": signature,  # Required for card payments
            "customer_email": user_email,
            "payment_method": {
                "type": payment_method_type,
            },
            "reference": ref,
            "acceptance_token": token,
        }

        # Add redirect URL for redirect payment methods
        if redirect_url:
            body["redirect_url"] = redirect_url

        try:
            response = await client.post(
                "/v1/transactions",
                json=body,
                headers=self._auth_headers(),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e)
        except httpx.TimeoutException:
            raise WompiTimeoutError() from None
        except httpx.ConnectError as e:
            raise WompiConnectionError(str(e)) from None

        return response.json()

    async def get_transaction(self, transaction_id: str) -> dict:
        """Fetch a transaction by ID.

        GET /v1/transactions/{id}

        Returns:
            Transaction data including status, payment_method, etc.
        """
        client = await self._get_client()

        try:
            response = await client.get(
                f"/v1/transactions/{transaction_id}",
                headers=self._auth_headers(),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e)
        except httpx.TimeoutException:
            raise WompiTimeoutError() from None
        except httpx.ConnectError as e:
            raise WompiConnectionError(str(e)) from None

        return response.json()

    async def get_transaction_by_reference(self, reference: str) -> dict | None:
        """Find a transaction by reference.

        GET /v1/transactions?reference={reference}

        Returns:
            Transaction data if found, None otherwise.
        """
        client = await self._get_client()

        try:
            response = await client.get(
                "/v1/transactions",
                params={"reference": reference},
                headers=self._auth_headers(),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e)
        except httpx.TimeoutException:
            raise WompiTimeoutError() from None
        except httpx.ConnectError as e:
            raise WompiConnectionError(str(e)) from None

        data = response.json()
        results = data.get("data", [])
        return results[0] if results else None

    @staticmethod
    def verify_webhook_signature(
        payload: bytes,
        signature_header: str,
        webhook_secret: str,
    ) -> bool:
        """Verify Wompi webhook signature.

        Wompi sends the checksum in the 'X-Event-Checksum' header.
        The signature is verified by:
        1. Parsing the event to get properties and timestamp
        2. Concatenating: property_values + timestamp + secret
        3. Computing SHA256 and comparing with the checksum

        Args:
            payload: Raw request body (JSON bytes)
            signature_header: Value from X-Event-Checksum header
            webhook_secret: Secret from Wompi Dashboard (events secret)

        Returns:
            True if signature is valid
        """
        if not signature_header:
            return False

        import json

        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            return False

        # Extract signature data
        sig_obj = event.get("signature", {})
        properties = sig_obj.get("properties", [])
        checksum_from_event = sig_obj.get("checksum", "")
        timestamp = event.get("timestamp", "")

        # Build the string to hash: concatenate property values + timestamp + secret
        parts_to_hash = []
        data_obj = event.get("data", {})

        for prop_path in properties:
            # Property paths like "transaction.id", "transaction.status"
            value = data_obj
            for key in prop_path.split("."):
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    value = None
                    break
            if value is not None:
                parts_to_hash.append(str(value))

        # Add timestamp
        parts_to_hash.append(str(timestamp))

        # Concatenate all parts
        string_to_hash = "".join(parts_to_hash) + webhook_secret

        # Calculate SHA256
        calculated_checksum = hashlib.sha256(string_to_hash.encode()).hexdigest()

        return calculated_checksum == checksum_from_event

    @staticmethod
    def calculate_integrity_signature(
        reference: str,
        amount_in_cents: int,
        currency: str,
        integrity_key: str,
    ) -> str:
        """Calculate the integrity signature for a transaction.

        The signature is SHA256(<Reference><AmountInCents><Currency><IntegrityKey>)

        Args:
            reference: Unique transaction reference
            amount_in_cents: Amount in cents
            currency: Currency code (COP)
            integrity_key: Integrity key from Wompi Dashboard (test_integrity_xxx or prod_integrity_xxx)

        Returns:
            Hex-encoded SHA256 signature
        """
        string_to_hash = f"{reference}{amount_in_cents}{currency}{integrity_key}"
        return hashlib.sha256(string_to_hash.encode()).hexdigest()

    @property
    def public_key(self) -> str:
        """Return public key for frontend use (Wompi Widget)."""
        return self._public_key

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> WompiClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
