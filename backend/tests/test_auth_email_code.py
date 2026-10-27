"""
End-to-end tests for the passwordless email-code auth flow (S1b).

Covers: request → cooldown, verify (wrong/replay/expired/max-attempts),
account find-or-create, refresh rotation + reuse detection, logout.
Email delivery is captured in-memory (no provider needed).
"""

import jwt as pyjwt
import pytest
from sqlmodel import select

from app.core.config import get_settings
from app.core.security import decode_access_token, hash_email_code
from app.db.models import AuthEmailCode, User
from app.services import email_service
from app.api.v1 import auth as auth_module

CODE = "123456"
EMAIL = "NewUser@Example.com"  # normalized to lowercase by the endpoints


@pytest.fixture
def captured_emails(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Capture outgoing emails instead of hitting a provider."""
    sent: list[dict] = []

    async def _fake_send(to, subject, html_body, text_body=None):
        sent.append(
            {"to": to, "subject": subject, "html": html_body, "text": text_body}
        )
        return True

    monkeypatch.setattr(email_service, "send_email_async", _fake_send)
    return sent


@pytest.fixture
def fixed_code(monkeypatch: pytest.MonkeyPatch) -> str:
    """Make the generated code deterministic."""
    monkeypatch.setattr(auth_module, "_generate_code", lambda length: CODE)
    return CODE


def _request_code(client, email: str = EMAIL):
    return client.post("/v1/auth/email-code/request", json={"email": email})


def _verify_code(client, email: str = EMAIL, code: str = CODE):
    return client.post("/v1/auth/email-code/verify", json={"email": email, "code": code})


async def _latest_code_row(clean_db, email: str = EMAIL) -> AuthEmailCode | None:
    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(AuthEmailCode)
            .where(AuthEmailCode.email == email.lower())
            .order_by(AuthEmailCode.created_at.desc(), AuthEmailCode.id.desc())
        )
        return result.scalars().first()


async def _user_count(clean_db, email: str = EMAIL) -> int:
    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == email.lower())
        )
        return len(result.scalars().all())


# ---------------------------------------------------------------------------
# request
# ---------------------------------------------------------------------------


def test_request_code_returns_202_persists_hash_and_sends(
    client, override_get_session, clean_db, captured_emails, fixed_code
):
    response = _request_code(client)

    assert response.status_code == 202
    assert response.json() == {"detail": "CODE_SENT"}

    # Email captured, addressed to the normalized address, carries the code.
    assert len(captured_emails) == 1
    assert captured_emails[0]["to"] == EMAIL.lower()
    assert CODE in captured_emails[0]["html"]

    # Row persisted: normalized email + peppered hash, still live.
    import asyncio

    row = asyncio.run(_latest_code_row(clean_db))
    assert row is not None
    assert row.code_hash == hash_email_code(CODE)
    assert row.used_at is None
    assert row.attempts == 0


def test_request_code_cooldown_blocks_immediate_second_request(
    client, override_get_session, clean_db, captured_emails, fixed_code
):
    assert _request_code(client).status_code == 202

    second = _request_code(client)

    assert second.status_code == 429
    assert second.json()["detail"] == "CODE_COOLDOWN"
    assert len(captured_emails) == 1  # no second email


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def test_verify_wrong_code_returns_400_and_counts_attempt(
    client, override_get_session, clean_db, captured_emails, fixed_code
):
    assert _request_code(client).status_code == 202

    response = _verify_code(client, code="999999")

    assert response.status_code == 400
    assert response.json()["detail"] == "INVALID_CODE"

    import asyncio

    row = asyncio.run(_latest_code_row(clean_db))
    assert row.attempts == 1
    assert row.used_at is None


def test_verify_correct_code_creates_user_and_issues_tokens(
    client, override_get_session, clean_db, captured_emails, fixed_code
):
    assert _request_code(client).status_code == 202

    response = _verify_code(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]

    # The access token resolves to the freshly created user.
    payload = decode_access_token(body["access_token"])
    import asyncio

    async def _load():
        async with clean_db.session_factory() as session:
            result = await session.execute(
                select(User).where(User.email == EMAIL.lower())
            )
            return result.scalars().all()

    users = asyncio.run(_load())
    assert len(users) == 1
    user = users[0]
    assert payload["sub"] == str(user.id)
    assert user.password_hash is None  # passwordless account
    assert user.email_verified_at is not None  # proven by the code


def test_verify_is_single_use(client, override_get_session, clean_db, captured_emails, fixed_code):
    assert _request_code(client).status_code == 202
    assert _verify_code(client).status_code == 200

    replay = _verify_code(client)

    assert replay.status_code == 400
    assert replay.json()["detail"] == "INVALID_CODE"


def test_verify_expired_code_returns_code_expired(
    client, override_get_session, clean_db, captured_emails, fixed_code
):
    from datetime import UTC, datetime, timedelta

    assert _request_code(client).status_code == 202

    async def _expire():
        async with clean_db.session_factory() as session:
            row = await _latest_code_row(clean_db)
            merged = await session.get(AuthEmailCode, row.id)
            merged.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    import asyncio

    asyncio.run(_expire())

    response = _verify_code(client)

    assert response.status_code == 400
    assert response.json()["detail"] == "CODE_EXPIRED"


def test_verify_stops_after_max_attempts(
    client, override_get_session, clean_db, captured_emails, fixed_code
):
    settings = get_settings()
    assert _request_code(client).status_code == 202

    async def _set_attempts():
        async with clean_db.session_factory() as session:
            row = await _latest_code_row(clean_db)
            merged = await session.get(AuthEmailCode, row.id)
            merged.attempts = settings.email_code_max_attempts
            await session.commit()

    import asyncio

    asyncio.run(_set_attempts())

    response = _verify_code(client)  # even with the CORRECT code

    assert response.status_code == 400
    assert response.json()["detail"] == "CODE_MAX_ATTEMPTS"


def test_failed_verifies_trip_the_brute_force_window(
    client, override_get_session, clean_db, captured_emails, fixed_code
):
    assert _request_code(client).status_code == 202

    for _ in range(5):
        assert _verify_code(client, code="999999").status_code == 400

    # The shared brute-force window now rejects everything for this email.
    response = _verify_code(client)

    assert response.status_code == 429
    assert response.json()["detail"] == "RATE_LIMITED"


def test_verify_existing_unverified_user_marks_verified_without_duplicating(
    client, override_get_session, clean_db, captured_emails, fixed_code
):
    async def _seed():
        async with clean_db.session_factory() as session:
            session.add(
                User(
                    email=EMAIL.lower(),
                    password_hash=None,
                    role="job_seeker",
                    full_name="Pre-existing",
                    locale="es",
                    email_verified_at=None,
                )
            )
            await session.commit()

    import asyncio

    asyncio.run(_seed())

    assert _request_code(client).status_code == 202
    assert _verify_code(client).status_code == 200

    async def _load():
        async with clean_db.session_factory() as session:
            result = await session.execute(
                select(User).where(User.email == EMAIL.lower())
            )
            return result.scalars().all()

    users = asyncio.run(_load())
    assert len(users) == 1
    assert users[0].email_verified_at is not None


# ---------------------------------------------------------------------------
# refresh + logout
# ---------------------------------------------------------------------------


def _login_tokens(client, **kwargs) -> dict:
    assert _request_code(client, **kwargs).status_code == 202
    response = _verify_code(client, **kwargs)
    assert response.status_code == 200
    return response.json()


def test_refresh_rotates_and_reuse_is_detected(
    client, override_get_session, clean_db, captured_emails, fixed_code
):
    tokens = _login_tokens(client)

    rotated = client.post(
        "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    new_tokens = rotated.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # Replaying the consumed token revokes the whole family.
    reuse = client.post(
        "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reuse.status_code == 401
    assert reuse.json()["detail"] == "TOKEN_REUSED"

    # Even the freshly rotated token is dead now.
    after = client.post(
        "/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert after.status_code == 401


def test_logout_revokes_the_refresh_token(
    client, override_get_session, clean_db, captured_emails, fixed_code
):
    settings = get_settings()
    tokens = _login_tokens(client)
    access = pyjwt.decode(
        tokens["access_token"], options={"verify_signature": False}
    )

    response = client.post(
        "/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 204

    after = client.post(
        "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert after.status_code == 401
    assert after.json()["detail"] == "TOKEN_INVALID"
