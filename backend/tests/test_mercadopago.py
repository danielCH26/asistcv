"""Tests del proveedor Mercado Pago y de su webhook.

Mercado Pago estaba registrado en el factory pero su provider lanzaba
``NotImplementedError`` al construirse: elegirlo en el checkout devolvía un
500 opaco. Estos tests cubren el camino completo:

1. El provider se construye y pide el token de acceso.
2. El checkout crea una preferencia de Checkout Pro con el precio en PESOS
   (Mercado Pago no usa centavos) y una ``external_reference`` que lleva
   user_id y plan_id.
3. La ruta del webhook está montada (sin esto el pago se cobra y la
   suscripción nunca se activa).
4. La firma HMAC se verifica.
5. E2E: la notificación "pending" seguida de la "approved" activa el plan.

Settings se parchean sobre el singleton cacheado con monkeypatch.setattr,
NUNCA por variables de entorno (Settings es @lru_cache'd).
"""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel import select

from app.services.billing_provider import (
    VALID_PROVIDER_IDS,
    CheckoutUrls,
    ProviderNotConfiguredError,
    get_billing_provider,
)
from app.services.mercadopago_client import MercadoPagoClient
from app.services.providers.mercadopago import MercadoPagoProvider

WEBHOOK_URL = "/api/v1/webhooks/mercadopago"
SECRET = "whsec_mp_test"


# === Fixtures ===


@pytest.fixture
def mp_settings(settings, monkeypatch):
    """Configura las credenciales de Mercado Pago sobre el singleton."""
    monkeypatch.setattr(settings, "mercadopago_access_token", "APP_USR-mp-test")
    monkeypatch.setattr(settings, "mercadopago_public_key", "APP_USR-mp-pub")
    monkeypatch.setattr(settings, "mercadopago_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "mercadopago_notification_url", None)
    monkeypatch.setattr(settings, "mercadopago_test_mode", True)
    monkeypatch.setattr(settings, "billing_provider_active", "mercadopago")
    return settings


def _fake_client() -> MagicMock:
    """Cliente de Mercado Pago falso: no toca la red."""
    client = MagicMock()
    client.create_preference = AsyncMock(
        return_value={
            "id": "pref_123",
            "init_point": "https://www.mercadopago.com.co/checkout/v1/redirect?pref_id=1",
            "sandbox_init_point": "https://sandbox.mercadopago.com.co/checkout/v1/redirect?pref_id=1",
        }
    )
    client.get_payment = AsyncMock(
        return_value={
            "id": "pay_1",
            "status": "approved",
            "external_reference": "55_job_seeker_monthly_abc123",
            "payer": {"id": 999},
        }
    )
    return client


def _signature(data_id: str, request_id: str, ts: str, secret: str = SECRET) -> str:
    """Arma el header ``x-signature`` como lo manda Mercado Pago."""
    manifest = f"id:{data_id.lower()};request-id:{request_id};ts:{ts};"
    digest = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={digest}"


def _notification(payment_id: str = "pay_1") -> bytes:
    """Notificación de Mercado Pago: solo lleva el id del pago."""
    return json.dumps(
        {"type": "payment", "action": "payment.updated", "data": {"id": payment_id}}
    ).encode()


# === Factory ===


def test_mercadopago_is_a_known_provider_id() -> None:
    assert "mercadopago" in VALID_PROVIDER_IDS


def test_factory_builds_the_mercadopago_provider(mp_settings) -> None:
    provider = get_billing_provider("mercadopago")
    assert provider.provider_id == "mercadopago"


def test_provider_requires_the_access_token(settings, monkeypatch) -> None:
    monkeypatch.setattr(settings, "mercadopago_access_token", None)
    with pytest.raises(ProviderNotConfiguredError):
        MercadoPagoProvider()


# === Checkout ===


async def test_create_checkout_builds_the_preference(mp_settings) -> None:
    """La preferencia lleva el precio en pesos y la referencia con user+plan."""
    provider = MercadoPagoProvider()
    client = _fake_client()
    provider._client = client

    session = await provider.create_checkout(
        plan={"plan_id": "job_seeker_monthly"},
        user={"id": 7, "email": "comprador@example.com"},
        return_urls=CheckoutUrls(
            success_url="https://eptus.app/ok", cancel_url="https://eptus.app/cancel"
        ),
    )

    assert session.provider_id == "mercadopago"
    assert session.session_id == "pref_123"
    assert session.checkout_url.startswith("https://sandbox.mercadopago.com.co")

    client.create_preference.assert_awaited_once()
    payload = client.create_preference.await_args.args[0]

    # Mercado Pago cobra en la unidad mayor de la moneda: pesos, no centavos.
    assert payload["items"][0]["unit_price"] == 29_000
    assert payload["items"][0]["currency_id"] == "COP"
    assert payload["items"][0]["quantity"] == 1

    # La referencia es lo único que vuelve verbatim en el webhook.
    assert payload["external_reference"].startswith("7_job_seeker_monthly_")
    assert payload["payer"]["email"] == "comprador@example.com"
    assert payload["back_urls"]["success"] == "https://eptus.app/ok"
    assert payload["metadata"]["user_id"] == "7"
    assert payload["metadata"]["plan_id"] == "job_seeker_monthly"


async def test_create_checkout_prefers_the_idempotency_key(mp_settings) -> None:
    """La reference no puede ser el idempotency key crudo: perdería user+plan."""
    provider = MercadoPagoProvider()
    client = _fake_client()
    provider._client = client

    await provider.create_checkout(
        plan={"plan_id": "job_seeker_monthly"},
        user={"id": 7, "email": "comprador@example.com"},
        return_urls=CheckoutUrls(success_url="https://eptus.app/ok", cancel_url="x"),
        idempotency_key="idem-123",
    )

    payload = client.create_preference.await_args.args[0]
    reference = payload["external_reference"]
    assert reference.startswith("7_job_seeker_monthly_")
    assert reference != "idem-123"


# === Webhook ===


async def test_webhook_route_is_mounted(async_client) -> None:
    """Regresión del 404: sin este include_router el pago no se confirma."""
    response = await async_client.post(
        WEBHOOK_URL,
        content=b"{}",
        headers={"x-signature": "ts=1,v1=abc"},
    )

    assert response.status_code != 404, (
        f"{WEBHOOK_URL} no está montado: el pago se cobraría pero la "
        "suscripción nunca se activaría."
    )
    assert response.status_code in (400, 500, 503), response.text


async def test_webhook_rejects_an_invalid_signature(async_client, mp_settings) -> None:
    payload = _notification()

    response = await async_client.post(
        WEBHOOK_URL,
        content=payload,
        headers={
            "x-signature": "ts=1767225600,v1=deadbeef",
            "x-request-id": "req-1",
        },
    )

    assert response.status_code == 400


async def test_webhook_rejects_a_missing_signature(async_client, mp_settings) -> None:
    response = await async_client.post(WEBHOOK_URL, content=_notification())

    assert response.status_code == 400


# === E2E de compra: webhook valido -> suscripcion activa ===


async def test_valid_webhook_activates_the_subscription(
    async_client, clean_db, mp_settings, monkeypatch
) -> None:
    """E2E de compra: el pago aprobado activa el plan del usuario."""
    from app.db.models import Subscription, User

    async with clean_db.session_factory() as session:
        user = User(
            id=55,
            email="comprador-mp@example.com",
            password_hash="hashed",
            role="job_seeker",
            full_name="Comprador MP",
        )
        session.add(user)
        await session.commit()

    # Mercado Pago notifica "pending" y después "approved" con el MISMO
    # cuerpo (solo cambia el estado del pago). Si la clave de idempotencia
    # fuera solo el id del pago, la segunda notificación se deduplicaba
    # como repetida y el plan nunca se activaba.
    estado = {"status": "pending"}

    async def _get_payment(self, payment_id: str) -> dict:
        return {
            "id": payment_id,
            "status": estado["status"],
            "external_reference": "55_job_seeker_monthly_abc123",
            "payer": {"id": 999},
        }

    monkeypatch.setattr(MercadoPagoClient, "get_payment", _get_payment)

    ts = "1767225600"
    headers = {
        "x-signature": _signature("pay_1", "req-1", ts),
        "x-request-id": "req-1",
    }

    pending = await async_client.post(WEBHOOK_URL, content=_notification(), headers=headers)
    assert pending.status_code == 200, pending.text
    assert pending.json()["status"] == "processed"

    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == 55)
        )
        sub = result.scalars().one_or_none()
        assert sub is None or sub.status != "active", (
            "la notificación 'pending' no debe activar el plan todavía"
        )

    estado["status"] = "approved"

    approved = await async_client.post(WEBHOOK_URL, content=_notification(), headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "processed"

    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == 55)
        )
        sub = result.scalars().one()
        assert sub.plan == "job_seeker_monthly"
        assert sub.status == "active"
        assert sub.current_period_end is not None, (
            "la suscripción quedó sin current_period_end: el payload de Mercado "
            "Pago no viene en la forma que lee el handler compartido"
        )


async def test_webhook_is_idempotent_for_the_same_event(
    async_client, clean_db, mp_settings, monkeypatch
) -> None:
    """La misma notificación repetida no debe procesar dos veces."""

    async def _get_payment(self, payment_id: str) -> dict:
        return {
            "id": payment_id,
            "status": "approved",
            "external_reference": "56_job_seeker_monthly_abc123",
            "payer": {"id": 999},
        }

    monkeypatch.setattr(MercadoPagoClient, "get_payment", _get_payment)

    ts = "1767225600"
    headers = {
        "x-signature": _signature("pay_2", "req-2", ts),
        "x-request-id": "req-2",
    }

    first = await async_client.post(
        WEBHOOK_URL, content=_notification("pay_2"), headers=headers
    )
    second = await async_client.post(
        WEBHOOK_URL, content=_notification("pay_2"), headers=headers
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "already_processed"
