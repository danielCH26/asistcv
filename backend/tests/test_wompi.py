"""Tests del proveedor Wompi y de su webhook.

Hasta ahora no había NINGÚN test de Wompi, y por eso se colaron tres bugs que
rompían el cobro por completo:

1. ``import time`` había quedado dentro del docstring de
   ``providers/wompi.py`` → ``NameError`` al construir la referencia de la
   transacción (el archivo era sintácticamente válido: era todo un string).
2. El webhook no estaba montado en ``main.py`` → ``POST
   /api/v1/webhooks/wompi`` devolvía 404: el pago se cobra y la suscripción
   nunca se activa.
3. ``"wompi"`` no estaba en ``_PROVIDER_IDS`` ni en el factory → con
   ``BILLING_PROVIDER_ACTIVE=wompi`` el checkout moría con ``ValueError:
   Unknown billing provider``.

Settings se parchean sobre el singleton cacheado con monkeypatch.setattr,
NUNCA por variables de entorno (Settings es @lru_cache'd).
"""

import hashlib
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
from app.services.providers.wompi import WompiProvider

WEBHOOK_URL = "/api/v1/webhooks/wompi"


# === Fixtures ===


@pytest.fixture
def wompi_settings(settings, monkeypatch):
    """Configura las credenciales de Wompi sobre el singleton de settings."""
    monkeypatch.setattr(settings, "wompi_private_key", "priv_test")
    monkeypatch.setattr(settings, "wompi_public_key", "pub_test")
    monkeypatch.setattr(settings, "wompi_webhook_secret", "whsec_test")
    monkeypatch.setattr(settings, "wompi_integrity_key", "integ_test")
    monkeypatch.setattr(settings, "wompi_acceptance_token", "acc_test")
    monkeypatch.setattr(settings, "wompi_test_mode", True)
    monkeypatch.setattr(settings, "billing_provider_active", "wompi")
    return settings


def _fake_client() -> MagicMock:
    """Cliente Wompi falso: no toca la red."""
    client = MagicMock()
    client.calculate_integrity_signature = MagicMock(return_value="sig-abc123")
    client.create_transaction = AsyncMock(
        return_value={
            "data": {
                "id": "tx_123",
                "redirect_url": "https://pay.wompi.co/l/abc123",
            }
        }
    )
    return client


# === Factory ===


def test_wompi_is_a_known_provider_id() -> None:
    """Sin esto, BILLING_PROVIDER_ACTIVE=wompi moría en el checkout."""
    assert "wompi" in VALID_PROVIDER_IDS


def test_factory_builds_the_wompi_provider(wompi_settings) -> None:
    provider = get_billing_provider("wompi")
    assert provider.provider_id == "wompi"


def test_provider_requires_the_keys(settings, monkeypatch) -> None:
    monkeypatch.setattr(settings, "wompi_private_key", None)
    monkeypatch.setattr(settings, "wompi_public_key", None)
    with pytest.raises(ProviderNotConfiguredError):
        WompiProvider()


# === Checkout ===


async def test_create_checkout_builds_the_reference_and_calls_the_client(
    wompi_settings,
) -> None:
    """Regresión del NameError: la referencia se arma con time.time()."""
    provider = WompiProvider()
    client = _fake_client()
    provider._client = client

    session = await provider.create_checkout(
        plan={"plan_id": "job_seeker_monthly"},
        user={"id": 7, "email": "comprador@example.com"},
        return_urls=CheckoutUrls(
            success_url="https://asistcv.app/ok", cancel_url="https://asistcv.app/cancel"
        ),
    )

    assert session.provider_id == "wompi"
    assert session.session_id == "tx_123"
    assert session.checkout_url == "https://pay.wompi.co/l/abc123"

    # La referencia tiene que existir y llevar user + plan.
    client.create_transaction.assert_awaited_once()
    kwargs = client.create_transaction.await_args.kwargs
    assert kwargs["reference"].startswith("7_job_seeker_monthly_")
    assert kwargs["amount_in_cents"] == 29000
    assert kwargs["currency"] == "COP"


async def test_create_checkout_prefers_the_idempotency_key(wompi_settings) -> None:
    """El idempotency key NO puede ser la reference cruda.

    Si lo fuera, el reference perdería user_id y plan_id — y el webhook no
    podría activar la suscripcion. Se hashea para que la referencia siga
    siendo determinista (misma key → misma transaccion) sin perder datos.
    """
    provider = WompiProvider()
    client = _fake_client()
    provider._client = client

    await provider.create_checkout(
        plan={"plan_id": "job_seeker_monthly"},
        user={"id": 7, "email": "comprador@example.com"},
        return_urls=CheckoutUrls(
            success_url="https://asistcv.app/ok", cancel_url="https://asistcv.app/cancel"
        ),
        idempotency_key="idem-123",
    )

    kwargs = client.create_transaction.await_args.kwargs
    reference = kwargs["reference"]
    assert reference.startswith("7_job_seeker_monthly_")
    assert reference != "idem-123"

    # Misma key → misma referencia (idempotencia).
    await provider.create_checkout(
        plan={"plan_id": "job_seeker_monthly"},
        user={"id": 7, "email": "comprador@example.com"},
        return_urls=CheckoutUrls(
            success_url="https://asistcv.app/ok", cancel_url="https://asistcv.app/cancel"
        ),
        idempotency_key="idem-123",
    )
    assert client.create_transaction.await_args.kwargs["reference"] == reference


# === Webhook ===


async def test_webhook_route_is_mounted(async_client) -> None:
    """Regresión del 404: sin este include_router el pago no se confirma.

    Si la ruta no está montada, el panel de Wompi recibe un 404 al disparar
    el evento: el pago se cobra y la suscripción nunca se activa. La prueba
    es conductual a propósito — ``app.routes`` expone los routers incluidos
    como objetos sin ``path``, así que mirar la lista no dice nada.
    """
    response = await async_client.post(
        WEBHOOK_URL,
        content=b"{}",
        headers={"X-Event-Checksum": "checksum-invalido"},
    )

    assert response.status_code != 404, (
        f"{WEBHOOK_URL} no está montado: el pago se cobraría pero la "
        "suscripción nunca se activaría."
    )
    # Reaching the handler at all (400/500/503) — not a routing 404.
    assert response.status_code in (400, 500, 503), response.text


async def test_webhook_rejects_an_invalid_signature(async_client, wompi_settings) -> None:
    payload = json.dumps(
        {"event": "transaction.approved", "data": {"transaction": {"id": "tx_1"}}}
    ).encode()

    response = await async_client.post(
        WEBHOOK_URL,
        content=payload,
        headers={"X-Event-Checksum": "checksum-invalido"},
    )

    assert response.status_code == 400


# === E2E de compra: webhook valido -> suscripcion activa ===


def _signed_event(
    *,
    user_id: int,
    plan_id: str = "job_seeker_monthly",
    transaction_id: str = "tx_abc",
    status: str = "APPROVED",
    secret: str = "whsec_test",
    timestamp: int = 1767225600,
) -> bytes:
    """Evento de Wompi con el checksum valido.

    Wompi manda el checksum DENTRO del evento (``signature.checksum``): es el
    SHA-256 de los valores de ``signature.properties`` + ``timestamp`` +
    el secret del panel. El header ``X-Event-Checksum`` es una copia.
    """
    transaction = {
        "id": transaction_id,
        "status": status,
        # Formato de reference del provider: {user_id}_{plan_id}_{uniq}.
        "reference": f"{user_id}_{plan_id}_{timestamp}",
        "amount": 29000,
        "currency": "COP",
    }
    properties = ["transaction.id", "transaction.status"]
    string_to_hash = f"{transaction_id}{status}{timestamp}{secret}"
    checksum = hashlib.sha256(string_to_hash.encode()).hexdigest()

    event = {
        "event": f"transaction.{status.lower()}",
        "timestamp": timestamp,
        "signature": {"properties": properties, "checksum": checksum},
        "data": {"transaction": transaction},
    }
    return json.dumps(event).encode()


async def test_valid_webhook_activates_the_subscription(
    async_client, clean_db, wompi_settings
) -> None:
    """E2E de compra: el pago aprobado activa el plan del usuario.

    Es el camino que hace falta para cobrar: sin esto, el usuario paga y su
    plan no cambia.
    """
    from app.db.models import Subscription, User

    async with clean_db.session_factory() as session:
        user = User(
            id=55,
            email="comprador-wompi@example.com",
            password_hash="hashed",
            role="job_seeker",
            full_name="Comprador Wompi",
        )
        session.add(user)
        await session.commit()

    payload = _signed_event(user_id=55)

    response = await async_client.post(
        WEBHOOK_URL,
        content=payload,
        headers={"X-Event-Checksum": "cualquier-cosa-el-checksum-va-en-el-evento"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "processed"

    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == 55)
        )
        sub = result.scalars().one()
        assert sub.plan == "job_seeker_monthly"
        assert sub.status == "active"
        # La fecha de renovacion sale de la normalizacion del provider.
        assert sub.current_period_end is not None, (
            "la suscripcion quedo sin current_period_end: el payload de Wompi "
            "no viene en la forma que lee el handler compartido"
        )
