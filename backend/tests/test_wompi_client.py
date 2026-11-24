"""Tests del cliente HTTP de Wompi.

El cliente no tenia ningun test (40% de cobertura) y por ahi se colaron tres
problemas que solo se ven contra el sandbox real:

1. `GET /v1/acceptance_tokens` ya NO existe (404). El endpoint vigente es
   `GET /v1/merchants/info` con la clave publica en el header
   `x-merchant-public-key`. El viejo `/v1/merchants/{public_key}` quedo
   deshabilitado el 2026-10-31.
2. Crear una transaccion exige DOS acceptance tokens: `acceptance_token` y
   `accept_personal_auth`.
3. Los errores de Wompi vienen como {error: {type, reason}}; el cliente solo
   leia {error: {message}} y perdiaba el motivo real.

Se usa httpx.MockTransport: se verifica el request exacto (URL, headers,
body) sin tocar la red.
"""

import json

import httpx
import pytest

from app.services.wompi_client import (
    WompiClient,
    WompiError,
    WompiRateLimitError,
)

PRIVATE_KEY = "prv_test_abc"
PUBLIC_KEY = "pub_test_abc"
INTEGRITY_KEY = "test_integrity_abc"
SECRET = "events_secret_abc"

MERCHANT_INFO_RESPONSE = {
    "data": {
        "presigned_acceptance": {
            "acceptance_token": "tok-terminos",
            "permalink": "https://wompi.co/terminos.pdf",
            "type": "END_USER_POLICY",
        },
        "presigned_personal_data_auth": {
            "acceptance_token": "tok-datos-personales",
            "permalink": "https://wompi.co/datos.pdf",
            "type": "PERSONAL_DATA_AUTH",
        },
    }
}


def _client(handler) -> tuple[WompiClient, list[httpx.Request]]:
    """Cliente de Wompi con transporte simulado; devuelve los requests vistos."""
    seen: list[httpx.Request] = []

    def _wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = WompiClient(
        private_key=PRIVATE_KEY,
        public_key=PUBLIC_KEY,
        test_mode=True,
        transport=httpx.MockTransport(_wrapped),
    )
    return client, seen


# --- Acceptance tokens ---


async def test_acceptance_tokens_use_the_current_endpoint_and_header() -> None:
    """`/v1/acceptance_tokens` no existe: el vigente es `/v1/merchants/info`."""
    client, seen = _client(lambda request: httpx.Response(200, json=MERCHANT_INFO_RESPONSE))

    tokens = await client.get_acceptance_tokens()

    assert len(seen) == 1
    request = seen[0]
    assert request.url.path == "/v1/merchants/info", (
        "el endpoint de acceptance tokens cambio: /v1/acceptance_tokens devuelve 404"
    )
    assert request.headers["x-merchant-public-key"] == PUBLIC_KEY
    # La clave publica va en el header, no en el Authorization.
    assert request.headers.get("authorization") != f"Bearer {PUBLIC_KEY}"

    assert tokens["acceptance_token"] == "tok-terminos"
    assert tokens["accept_personal_auth"] == "tok-datos-personales"


async def test_acceptance_tokens_raise_on_wompi_error() -> None:
    client, _ = _client(
        lambda request: httpx.Response(
            404, json={"error": {"type": "NOT_FOUND_ERROR", "reason": "La entidad solicitada no existe"}}
        )
    )

    with pytest.raises(WompiError) as excinfo:
        await client.get_acceptance_tokens()

    # El motivo real de Wompi tiene que llegar al operador.
    assert "La entidad solicitada no existe" in str(excinfo.value)


# --- Transacciones ---


async def test_create_transaction_sends_both_acceptance_tokens() -> None:
    """Wompi exige `acceptance_token` Y `accept_personal_auth`."""
    client, seen = _client(
        lambda request: httpx.Response(
            201,
            json={
                "data": {
                    "id": "tx_1",
                    "status": "PENDING",
                    "redirect_url": "https://checkout.wompi.co/pay",
                }
            },
        )
    )

    result = await client.create_transaction(
        plan_id="job_seeker_monthly",
        user_id=7,
        user_email="comprador@example.com",
        amount_in_cents=29000,
        reference="7_job_seeker_monthly_1767225600",
        acceptance_token="tok-terminos",
        accept_personal_auth="tok-datos-personales",
        payment_method_type="PSE",
        redirect_url="https://asistcv.app/ok",
        signature="firma-de-integridad",
    )

    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/transactions"
    assert body["acceptance_token"] == "tok-terminos"
    assert body["accept_personal_auth"] == "tok-datos-personales"
    assert body["signature"] == "firma-de-integridad"
    assert body["reference"] == "7_job_seeker_monthly_1767225600"
    assert body["payment_method"] == {"type": "PSE"}
    assert result["data"]["id"] == "tx_1"


async def test_create_transaction_fetches_the_tokens_when_missing() -> None:
    """Si no le pasan tokens, los pide y manda los dos."""
    client, seen = _client(
        lambda request: (
            httpx.Response(200, json=MERCHANT_INFO_RESPONSE)
            if request.url.path == "/v1/merchants/info"
            else httpx.Response(201, json={"data": {"id": "tx_2"}})
        )
    )

    await client.create_transaction(
        plan_id="job_seeker_monthly",
        user_id=7,
        user_email="comprador@example.com",
        amount_in_cents=29000,
    )

    assert [r.url.path for r in seen] == ["/v1/merchants/info", "/v1/transactions"]
    body = json.loads(seen[1].content)
    assert body["acceptance_token"] == "tok-terminos"
    assert body["accept_personal_auth"] == "tok-datos-personales"


async def test_rate_limit_is_typed() -> None:
    client, _ = _client(
        lambda request: httpx.Response(429, headers={"Retry-After": "30"}, json={})
    )

    with pytest.raises(WompiRateLimitError) as excinfo:
        await client.create_transaction(
            plan_id="job_seeker_monthly",
            user_id=7,
            user_email="comprador@example.com",
            amount_in_cents=29000,
            acceptance_token="t",
            accept_personal_auth="p",
        )

    assert excinfo.value.retry_after == 30


# --- Integridad y firma de eventos ---


def test_integrity_signature_matches_the_documented_scheme() -> None:
    """Wompi: sha256(reference + amount + currency + integrity_key)."""
    signature = WompiClient.calculate_integrity_signature(
        reference="7_job_seeker_monthly_1",
        amount_in_cents=29000,
        currency="COP",
        integrity_key=INTEGRITY_KEY,
    )

    import hashlib

    expected = hashlib.sha256(
        f"7_job_seeker_monthly_1{"29000"}COP{INTEGRITY_KEY}".encode()
    ).hexdigest()
    assert signature == expected


def test_web_checkout_url_carries_the_integrity_signature() -> None:
    """El checkout se abre en la pagina alojada de Wompi.

    Por API no se puede crear una transaccion de TARJETA sin el `token` de
    la tarjeta tokenizada (Wompi responde 422 INPUT_VALIDATION_ERROR con
    "payment_method.token: No esta presente"). El camino soportado es el Web
    Checkout: un formulario GET contra checkout.wompi.co/p/ con la llave
    publica, el monto, la referencia y la firma de integridad.
    """
    import hashlib
    from urllib.parse import parse_qs, urlparse

    client = WompiClient(
        private_key=PRIVATE_KEY,
        public_key=PUBLIC_KEY,
        test_mode=True,
    )
    url = client.build_web_checkout_url(
        reference="7_job_seeker_monthly_1",
        amount_in_cents=2_900_000,
        customer_email="comprador@example.com",
        redirect_url="https://asistcv.app/ok",
        integrity_key=INTEGRITY_KEY,
    )

    parsed = urlparse(url)
    assert parsed.netloc == "checkout.wompi.co"
    assert parsed.path == "/p/"

    params = parse_qs(parsed.query)
    assert params["public-key"] == [PUBLIC_KEY]
    assert params["currency"] == ["COP"]
    assert params["amount-in-cents"] == ["2900000"]
    assert params["reference"] == ["7_job_seeker_monthly_1"]
    assert params["redirect-url"] == ["https://asistcv.app/ok"]
    assert params["customer-data:email"] == ["comprador@example.com"]

    expected = hashlib.sha256(
        f"7_job_seeker_monthly_12900000COP{INTEGRITY_KEY}".encode()
    ).hexdigest()
    assert params["signature:integrity"] == [expected]


def test_webhook_signature_is_validated_against_the_event_body() -> None:
    """La firma se compara contra el checksum del BODY, no contra el header.

    Asi lo documenta Wompi: el checksum viaja en el body (signature.checksum)
    y el header X-Event-Checksum es solo una copia. Por eso el valor del
    header no cambia el resultado — lo que se verifica es el cuerpo.
    """
    import hashlib

    def _event(checksum: str) -> bytes:
        return json.dumps(
            {
                "event": "transaction.approved",
                "timestamp": 1767225600,
                "signature": {"properties": ["transaction.id"], "checksum": checksum},
                "data": {"transaction": {"id": "tx_abc"}},
            }
        ).encode()

    good = hashlib.sha256(f"tx_abc1767225600{SECRET}".encode()).hexdigest()

    # Checksum valido en el body -> aceptado, sea cual sea el header.
    assert WompiClient.verify_webhook_signature(_event(good), good, SECRET) is True
    assert WompiClient.verify_webhook_signature(_event(good), "otro", SECRET) is True

    # Checksum manipulado en el body -> rechazado.
    assert WompiClient.verify_webhook_signature(_event("0" * 64), good, SECRET) is False

    # Secret distinto -> el checksum calculado no coincide.
    assert WompiClient.verify_webhook_signature(_event(good), good, "otro-secret") is False
