"""
Tests for the Clerk webhook handler (ODD slice S2).

Covers:
- Valid Svix signature + user.updated → local row fields updated.
- Invalid signature → 400.
- Missing svix-id header → 400.
- Stale timestamp → 400.
- user.deleted → 200, local row preserved.
- user.created → 200, local row upserted.
- Unknown clerk_id on updated → 200 (best-effort sync).
- Other event types → 200 + no side effects.
- Missing CLERK_WEBHOOK_SIGNING_SECRET → 503.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.db.models import User

WEBHOOK_URL = "/api/v1/webhooks/clerk"

# Test signing secret: 32 zero bytes, base64-encoded, with whsec_ prefix.
_WH_SEC_TEST_KEY = "whsec_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
_WH_SEC_RAW = base64.b64decode("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")


# === Svix signature helpers (must match app/api/webhooks/clerk.py) ===

def _svix_sign(raw_body: bytes, svix_id: str, svix_ts: int, secret: str) -> str:
    """Build a Svix v1 signature for the given payload.

    Signed content: "{id}.{timestamp}.{raw_body}"
    HMAC-SHA256 with the raw (non-base64) secret.
    """
    signed_content = f"{svix_id}.{svix_ts}.{raw_body.decode()}".encode()
    mac = hmac.new(secret.encode(), signed_content, hashlib.sha256).digest()
    return f"v1,{base64.b64encode(mac).decode()}"


def _svix_headers(
    raw_body: bytes,
    svix_id: str = "evt_test_123",
    svix_ts: int | None = None,
    secret: str = _WH_SEC_RAW.decode(),
) -> dict[str, str]:
    """Return headers dict for a valid Svix-signed request."""
    ts = svix_ts if svix_ts is not None else int(time.time())
    return {
        "svix-id": svix_id,
        "svix-timestamp": str(ts),
        "svix-signature": _svix_sign(raw_body, svix_id, ts, secret),
    }


def _clerk_payload(event_type: str, user_id: str = "user_clerk_test") -> bytes:
    """Build a minimal Clerk webhook payload."""
    payload = {
        "type": event_type,
        "data": {
            "id": user_id,
            "email_addresses": [{
                "id": "ema_test_1",
                "email_address": f"clerk_{user_id}@example.com",
                "verification": {"status": "verified"},
            }],
            "primary_email_address_id": "ema_test_1",
            "first_name": "Clerk",
            "last_name": "Test",
            "locale": "es",
            "image_url": "https://example.com/avatar.png",
            "public_metadata": {},
        },
    }
    return json.dumps(payload).encode()


# === Fixtures ===

@pytest.fixture
def clerk_webhook_secret():
    """Return the raw bytes of the test signing secret."""
    return _WH_SEC_RAW


# === Tests ===

async def test_webhook_valid_signature_updates_user(
    clean_db,
    clerk_webhook_secret,
):
    """user.updated with valid signature → local user row fields are updated."""
    user_id = "user_clerk_test"

    # Seed a local user with clerk_id.
    async with clean_db.session_factory() as session:
        user = User(
            email="old@example.com",
            password_hash="hash",
            role="job_seeker",
            full_name="Old Name",
            clerk_id=user_id,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        original_id = user.id

    payload = _clerk_payload("user.updated", user_id=user_id)
    headers = _svix_headers(payload)

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    # Patch _get_signing_secret to return the test key.
    with patch("app.api.webhooks.clerk._get_signing_secret", return_value=clerk_webhook_secret):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(WEBHOOK_URL, content=payload, headers=headers)

    assert response.status_code == 200, response.text

    # Verify the DB row was updated.
    async with clean_db.session_factory() as session:
        user = (
            await session.execute(select(User).where(User.id == original_id))
        ).scalar_one_or_none()

    assert user is not None
    assert user.email == f"clerk_{user_id}@example.com"
    assert user.full_name == "Clerk Test"
    assert user.avatar_url == "https://example.com/avatar.png"
    assert user.email_verified_at is not None
    assert user.locale == "es"


async def test_webhook_invalid_signature_returns_400(
    clean_db,
    clerk_webhook_secret,
):
    """Invalid Svix signature → 400."""
    payload = _clerk_payload("user.updated", user_id="user_bad_sig")
    # Sign with a different key.
    headers = _svix_headers(payload, secret="wrong_secret_key_that_is_32bytes!!")

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    with patch("app.api.webhooks.clerk._get_signing_secret", return_value=clerk_webhook_secret):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(WEBHOOK_URL, content=payload, headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "INVALID_SIGNATURE"


async def test_webhook_missing_svix_id_returns_400(
    clean_db,
    clerk_webhook_secret,
):
    """Missing svix-id header → 400 MISSING_SVIX_HEADERS."""
    payload = _clerk_payload("user.updated", user_id="user_no_id")
    headers = {
        "svix-timestamp": str(int(time.time())),
        "svix-signature": "v1,somesig",
    }

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    with patch("app.api.webhooks.clerk._get_signing_secret", return_value=clerk_webhook_secret):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(WEBHOOK_URL, content=payload, headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "MISSING_SVIX_HEADERS"


async def test_webhook_missing_svix_timestamp_returns_400(
    clean_db,
    clerk_webhook_secret,
):
    """Missing svix-timestamp header → 400 MISSING_SVIX_HEADERS."""
    payload = _clerk_payload("user.updated", user_id="user_no_ts")
    headers = {
        "svix-id": "evt_test_123",
        "svix-signature": "v1,somesig",
    }

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    with patch("app.api.webhooks.clerk._get_signing_secret", return_value=clerk_webhook_secret):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(WEBHOOK_URL, content=payload, headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "MISSING_SVIX_HEADERS"


async def test_webhook_stale_timestamp_returns_400(
    clean_db,
    clerk_webhook_secret,
):
    """Timestamp older than ±5 minutes → 400."""
    payload = _clerk_payload("user.updated", user_id="user_stale")
    # 10 minutes in the past.
    stale_ts = int(time.time()) - 600
    headers = _svix_headers(payload, svix_ts=stale_ts)

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    with patch("app.api.webhooks.clerk._get_signing_secret", return_value=clerk_webhook_secret):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(WEBHOOK_URL, content=payload, headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "INVALID_SIGNATURE"


async def test_webhook_future_timestamp_returns_400(
    clean_db,
    clerk_webhook_secret,
):
    """Timestamp in the future beyond tolerance → 400."""
    payload = _clerk_payload("user.updated", user_id="user_future")
    # 10 minutes in the future.
    future_ts = int(time.time()) + 600
    headers = _svix_headers(payload, svix_ts=future_ts)

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    with patch("app.api.webhooks.clerk._get_signing_secret", return_value=clerk_webhook_secret):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(WEBHOOK_URL, content=payload, headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "INVALID_SIGNATURE"


async def test_webhook_user_deleted_keeps_local_row(
    clean_db,
    clerk_webhook_secret,
):
    """user.deleted → 200, local row is preserved."""
    user_id = "user_deleted_test"

    async with clean_db.session_factory() as session:
        user = User(
            email=f"deleted_{user_id}@example.com",
            password_hash="hash",
            role="job_seeker",
            full_name="Delete Test",
            clerk_id=user_id,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        original_id = user.id

    payload = _clerk_payload("user.deleted", user_id=user_id)
    headers = _svix_headers(payload)

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    with patch("app.api.webhooks.clerk._get_signing_secret", return_value=clerk_webhook_secret):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(WEBHOOK_URL, content=payload, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # Row still exists (FK integrity).
    async with clean_db.session_factory() as session:
        user = (
            await session.execute(select(User).where(User.id == original_id))
        ).scalar_one_or_none()

    assert user is not None


async def test_webhook_user_created_upserts_local_row(
    clean_db,
    clerk_webhook_secret,
):
    """user.created → 200, new local row created."""
    user_id = "user_created_test"

    payload = _clerk_payload("user.created", user_id=user_id)
    headers = _svix_headers(payload)

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    with patch("app.api.webhooks.clerk._get_signing_secret", return_value=clerk_webhook_secret):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(WEBHOOK_URL, content=payload, headers=headers)

    assert response.status_code == 200

    # Verify the DB row was created.
    async with clean_db.session_factory() as session:
        user = (
            await session.execute(
                select(User).where(User.clerk_id == user_id)
            )
        ).scalar_one_or_none()

    assert user is not None
    assert user.email == f"clerk_{user_id}@example.com"
    assert user.full_name == "Clerk Test"
    assert user.clerk_id == user_id
    assert user.password_hash is None


async def test_webhook_unknown_clerk_id_on_updated_returns_200(
    clean_db,
    clerk_webhook_secret,
):
    """user.updated for unknown clerk_id → 200 (best-effort sync)."""
    user_id = "user_unknown_clerk_id"

    payload = _clerk_payload("user.updated", user_id=user_id)
    headers = _svix_headers(payload)

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    with patch("app.api.webhooks.clerk._get_signing_secret", return_value=clerk_webhook_secret):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(WEBHOOK_URL, content=payload, headers=headers)

    # Must return 200 even for unknown clerk_id.
    assert response.status_code == 200

    # No row should be created.
    async with clean_db.session_factory() as session:
        user = (
            await session.execute(
                select(User).where(User.clerk_id == user_id)
            )
        ).scalar_one_or_none()

    assert user is None


async def test_webhook_other_event_type_returns_200(
    clean_db,
    clerk_webhook_secret,
):
    """Unknown event type → 200 + no side effects."""
    payload = {
        "type": "session.created",
        "data": {"id": "sess_xyz"},
    }
    raw = json.dumps(payload).encode()
    headers = _svix_headers(raw, svix_id="evt_session_123")

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    with patch("app.api.webhooks.clerk._get_signing_secret", return_value=clerk_webhook_secret):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(WEBHOOK_URL, content=raw, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_webhook_missing_secret_returns_503(
    clean_db,
):
    """_get_signing_secret returns None → 503."""
    payload = _clerk_payload("user.updated", user_id="user_nosecret")
    headers = _svix_headers(payload)

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    # Patch _get_signing_secret to return None (simulating missing env var).
    with patch("app.api.webhooks.clerk._get_signing_secret", return_value=None):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(WEBHOOK_URL, content=payload, headers=headers)

    assert response.status_code == 503
    assert response.json()["detail"] == "CLERK_WEBHOOK_SECRET_NOT_CONFIGURED"
