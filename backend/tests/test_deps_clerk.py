"""
Tests for the Clerk auth path in app.api.deps (ODD slice S1+S2).

Covers:
- Valid Clerk token + existing local row → CurrentUser with auth_method "clerk".
- Valid Clerk token + no local row + clerk_secret_key → auto-provisioning.
- Provisioning: maps Clerk user fields correctly (email, role, name, avatar, etc.).
- Provisioning idempotency: concurrent IntegrityError → re-select.
- No clerk_secret_key → USER_NOT_SYNCED 401.
- API key still works → auth_method "api_key".
- Invalid Clerk-format token → 401.
- Clerk token with recruiter role → role "recruiter".
- Clerk token with unverified email → email_verified_at is None.
- optional_auth with Clerk token → same behavior.
- Legacy JWT returns 401 when Clerk is enabled (removed in S2).
"""
from __future__ import annotations

import json
import time
from base64 import urlsafe_b64encode
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.deps import get_current_user, optional_auth
from app.core.config import get_settings
from app.db.models import User

# ---------------------------------------------------------------------------
# RSA helpers (same pattern as test_clerk_auth.py)
# ---------------------------------------------------------------------------

try:
    from cryptography.hazmat.primitives.asymmetric import rsa
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


def _make_pk(fsa: str) -> str:
    payload_bytes = json.dumps({"fsa": fsa}).encode()
    encoded = urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
    return f"pk_test_{encoded}_$"


def _generate_rsa():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    pn = public.public_numbers()

    def _b64url(value: int) -> str:
        byte_len = (value.bit_length() + 7) // 8
        return urlsafe_b64encode(value.to_bytes(byte_len, "big")).rstrip(b"=").decode()

    return private, {
        "kty": "RSA", "alg": "RS256", "kid": "deps-key-1",
        "n": _b64url(pn.n), "e": _b64url(pn.e),
    }


def _sign_token(private_key, payload: dict, **overrides) -> str:
    payload = dict(payload)
    payload.setdefault("iat", int(time.time()))
    payload.setdefault("exp", int(time.time()) + 3600)
    # Real Clerk session tokens carry the issuer WITHOUT a trailing slash
    # (e.g. "https://immense-lamb-7783.clerk.accounts.dev"). QA 2026-10.
    payload.setdefault("iss", "https://frontend.clerk.dev")
    payload.setdefault("sub", "user_test_deps")
    payload.setdefault("sess_id", "sess_deps_xyz")
    payload.update(overrides)
    return jwt.encode(payload, private_key, algorithm="RS256",
                     headers={"kid": "deps-key-1"})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def clerk_test_env(monkeypatch):
    """Enable Clerk with publishable + secret key."""
    fsa = "frontend.clerk.dev"
    pk = _make_pk(fsa)
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", pk)
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_deps_secret")
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", f"https://{fsa}")
    get_settings.cache_clear()
    yield {"pk": pk, "fsa": fsa}
    get_settings.cache_clear()


@pytest.fixture
def rsa_keys_deps():
    private, public_jwk = _generate_rsa()
    return private, public_jwk


@pytest.fixture
def clerk_mock_jwks(rsa_keys_deps):
    _, public_jwk = rsa_keys_deps
    return {"keys": [public_jwk]}


def make_clerk_user_response(
    user_id: str = "user_test_deps",
    email: str = "clerk@example.com",
    primary_email_id: str = "ema_test_primary",
    email_verified: bool = True,
    first_name: str = "Test",
    last_name: str = "User",
    locale: str = "es",
    image_url: str = "https://example.com/avatar.png",
    public_metadata: dict | None = None,
) -> dict:
    verification = {"status": "verified"} if email_verified else {"status": "unverified"}
    return {
        "id": user_id,
        "email_addresses": [{
            "id": primary_email_id,
            "email_address": email,
            "verification": verification,
        }],
        "primary_email_address_id": primary_email_id,
        "first_name": first_name,
        "last_name": last_name,
        "locale": locale,
        "image_url": image_url,
        "public_metadata": public_metadata or {},
    }


# ---------------------------------------------------------------------------
# Session helper: build an AsyncSession from clean_db fixture
# ---------------------------------------------------------------------------

@pytest.fixture
async def clerk_db_session(clean_db):
    """Yield an AsyncSession from the test DB for use in deps tests."""
    async with clean_db.session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Test: Clerk token + existing local row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clerk_token_existing_user(
    clerk_test_env,
    rsa_keys_deps,
    clerk_mock_jwks,
    clean_db,
):
    """Clerk token + existing local user → CurrentUser auth_method=clerk."""
    private, _ = rsa_keys_deps

    # Seed a local user with clerk_id
    async with clean_db.session_factory() as session:
        user = User(
            email="clerk@example.com",
            password_hash="hash",
            role="job_seeker",
            full_name="Existing User",
            clerk_id="user_test_deps",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    token = _sign_token(private, {"sub": "user_test_deps", "sess_id": "sess_abc"})

    async with clean_db.session_factory() as session:
        from app.services import clerk_auth
        clerk_auth._jwks_cache.clear()

        with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mf:
            mf.return_value = clerk_mock_jwks

            result = await get_current_user(
                api_key_header=f"Bearer {token}",
                db=session,
            )

    assert result.auth_method == "clerk"
    assert result.id == user_id
    assert result.role == "job_seeker"


# ---------------------------------------------------------------------------
# Test: auto-provisioning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clerk_provisioning_creates_local_user(
    clerk_test_env,
    rsa_keys_deps,
    clerk_mock_jwks,
    clean_db,
):
    """No local row + clerk_secret_key → user provisioned via _fetch_clerk_user."""
    private, _ = rsa_keys_deps
    clerk_user = make_clerk_user_response(
        user_id="user_test_deps",
        email="newuser@example.com",
        first_name="New",
        last_name="Provisioned",
        public_metadata={"role": "recruiter"},
    )

    token = _sign_token(private, {"sub": "user_test_deps", "sess_id": "sess_new"})

    async with clean_db.session_factory() as session:
        from app.services import clerk_auth
        clerk_auth._jwks_cache.clear()

        with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mf:
            mf.return_value = clerk_mock_jwks

            with patch("app.api.deps._fetch_clerk_user", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = clerk_user

                result = await get_current_user(
                    api_key_header=f"Bearer {token}",
                    db=session,
                )

    assert result.auth_method == "clerk"
    assert result.role == "recruiter"
    assert result.name == "New Provisioned"

    # Verify DB row
    async with clean_db.session_factory() as session:
        user = (
            await session.execute(
                select(User).where(User.clerk_id == "user_test_deps")
            )
        ).scalar_one_or_none()

    assert user is not None
    assert user.email == "newuser@example.com"
    assert user.role == "recruiter"
    assert user.clerk_id == "user_test_deps"
    assert user.password_hash is None
    assert user.avatar_url == "https://example.com/avatar.png"
    assert user.email_verified_at is not None


# ---------------------------------------------------------------------------
# Test: idempotent provisioning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clerk_provisioning_idempotent(
    clerk_test_env,
    rsa_keys_deps,
    clerk_mock_jwks,
    clean_db,
):
    """Second request with same token → existing row used, provisioning called once."""
    private, _ = rsa_keys_deps
    clerk_user = make_clerk_user_response(
        user_id="user_test_deps",
        email="idempotent@example.com",
        first_name="Idempotent",
        last_name="Test",
    )

    token = _sign_token(private, {"sub": "user_test_deps", "sess_id": "sess_idem"})

    async with clean_db.session_factory() as session:
        from app.services import clerk_auth
        clerk_auth._jwks_cache.clear()

        with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mf:
            mf.return_value = clerk_mock_jwks

            with patch("app.api.deps._fetch_clerk_user", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = clerk_user

                # First call: provisions
                result1 = await get_current_user(
                    api_key_header=f"Bearer {token}",
                    db=session,
                )
                # Second call: uses existing row
                result2 = await get_current_user(
                    api_key_header=f"Bearer {token}",
                    db=session,
                )

    assert mock_fetch.call_count == 1, "Provisioning should be called only once"
    assert result1.id == result2.id
    assert result1.auth_method == "clerk"


# ---------------------------------------------------------------------------
# Test: recruiter role from public_metadata
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clerk_provisioning_recruiter_role(
    clerk_test_env,
    rsa_keys_deps,
    clerk_mock_jwks,
    clean_db,
):
    """public_metadata.role == 'recruiter' → local role is recruiter."""
    private, _ = rsa_keys_deps
    clerk_user = make_clerk_user_response(
        user_id="user_recruiter",
        email="recruiter@example.com",
        first_name="Re",
        last_name="Cruiter",
        public_metadata={"role": "recruiter"},
    )

    token = _sign_token(private, {"sub": "user_recruiter", "sess_id": "sess_rec"})

    async with clean_db.session_factory() as session:
        from app.services import clerk_auth
        clerk_auth._jwks_cache.clear()

        with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mf:
            mf.return_value = clerk_mock_jwks

            with patch("app.api.deps._fetch_clerk_user", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = clerk_user

                result = await get_current_user(
                    api_key_header=f"Bearer {token}",
                    db=session,
                )

    assert result.role == "recruiter"

    async with clean_db.session_factory() as session:
        user = (
            await session.execute(
                select(User).where(User.clerk_id == "user_recruiter")
            )
        ).scalar_one_or_none()
    assert user is not None
    assert user.role == "recruiter"


# ---------------------------------------------------------------------------
# Test: unverified email → email_verified_at is None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clerk_provisioning_unverified_email(
    clerk_test_env,
    rsa_keys_deps,
    clerk_mock_jwks,
    clean_db,
):
    """verification.status != 'verified' → email_verified_at is None."""
    private, _ = rsa_keys_deps
    clerk_user = make_clerk_user_response(
        user_id="user_unverified",
        email="unverified@example.com",
        email_verified=False,
        first_name="Un",
        last_name="Verified",
    )

    token = _sign_token(private, {"sub": "user_unverified", "sess_id": "sess_unv"})

    async with clean_db.session_factory() as session:
        from app.services import clerk_auth
        clerk_auth._jwks_cache.clear()

        with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mf:
            mf.return_value = clerk_mock_jwks

            with patch("app.api.deps._fetch_clerk_user", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = clerk_user

                await get_current_user(
                    api_key_header=f"Bearer {token}",
                    db=session,
                )

    async with clean_db.session_factory() as session:
        user = (
            await session.execute(
                select(User).where(User.clerk_id == "user_unverified")
            )
        ).scalar_one_or_none()
    assert user is not None
    assert user.email_verified_at is None


# ---------------------------------------------------------------------------
# Test: API key still works when Clerk enabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_key_still_works_when_clerk_enabled(
    clerk_test_env,
    clean_db,
    monkeypatch,
):
    """With Clerk enabled, API key authentication still returns auth_method=api_key."""
    monkeypatch.setenv("BACKEND_API_KEY", "test-api-key-abc")
    get_settings.cache_clear()
    try:
        async with clean_db.session_factory() as session:
            result = await get_current_user(
                api_key_header="Bearer test-api-key-abc",
                db=session,
            )
        assert result.auth_method == "api_key"
        assert result.id == 0
        assert result.role == "service"
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Test: invalid Clerk-format token → 401
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_clerk_format_token_raises_401(
    clerk_test_env,
    rsa_keys_deps,
    clerk_mock_jwks,
    clean_db,
):
    """RS256 token with bad signature → 401 (never falls through to legacy JWT)."""
    private, _ = rsa_keys_deps
    other_private, _ = _generate_rsa()
    # Sign with a different key → signature mismatch
    token = _sign_token(other_private, {"sub": "user_test_deps"})

    async with clean_db.session_factory() as session:
        from app.services import clerk_auth
        clerk_auth._jwks_cache.clear()

        with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mf:
            mf.return_value = clerk_mock_jwks

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    api_key_header=f"Bearer {token}",
                    db=session,
                )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid credentials"


# ---------------------------------------------------------------------------
# Test: no clerk_secret_key → USER_NOT_SYNCED
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_secret_key_user_not_synced(
    clerk_test_env,
    rsa_keys_deps,
    clerk_mock_jwks,
    clean_db,
    monkeypatch,
):
    """Valid Clerk token but no local row AND no secret key → 401 USER_NOT_SYNCED."""
    monkeypatch.setenv("CLERK_SECRET_KEY", "")
    get_settings.cache_clear()

    private, _ = rsa_keys_deps
    token = _sign_token(private, {"sub": "user_not_synced", "sess_id": "sess_ns"})

    async with clean_db.session_factory() as session:
        from app.services import clerk_auth
        clerk_auth._jwks_cache.clear()

        with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mf:
            mf.return_value = clerk_mock_jwks

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    api_key_header=f"Bearer {token}",
                    db=session,
                )

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "USER_NOT_SYNCED"

    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Test: optional_auth with Clerk token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_optional_auth_clerk_token(
    clerk_test_env,
    rsa_keys_deps,
    clerk_mock_jwks,
    clean_db,
):
    """optional_auth with valid Clerk token returns CurrentUser."""
    private, _ = rsa_keys_deps
    clerk_user = make_clerk_user_response(
        user_id="user_opt",
        email="opt@example.com",
        first_name="Opt",
        last_name="Auth",
    )

    token = _sign_token(private, {"sub": "user_opt", "sess_id": "sess_opt"})

    async with clean_db.session_factory() as session:
        from app.services import clerk_auth
        clerk_auth._jwks_cache.clear()

        with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mf:
            mf.return_value = clerk_mock_jwks

            with patch("app.api.deps._fetch_clerk_user", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = clerk_user

                result = await optional_auth(
                    api_key_header=f"Bearer {token}",
                    db=session,
                )

    assert result.auth_method == "clerk"
    assert result.name == "Opt Auth"


# ---------------------------------------------------------------------------
# Test: legacy JWT still works when Clerk enabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legacy_jwt_returns_401_when_clerk_enabled(
    clerk_test_env,
    clean_db,
):
    """Legacy HS256 JWT tokens → 401 when Clerk is enabled (legacy auth removed in S2)."""
    import jwt

    from app.core.config import get_settings

    # Seed a user
    async with clean_db.session_factory() as session:
        user = User(
            email="jwt@example.com",
            password_hash="hash",
            role="job_seeker",
            full_name="JWT User",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        uid = user.id

    # Build a legacy HS256 JWT using the same secret as create_access_token used.
    settings = get_settings()
    token = jwt.encode(
        {"sub": str(uid), "role": "job_seeker", "exp": 9999999999},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    async with clean_db.session_factory() as session:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                api_key_header=f"Bearer {token}",
                db=session,
            )

    # Falls through to API key path → no match → 401.
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Test: verify_api_key forwards a real DB session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_api_key_forwards_db_session(
    clerk_test_env,
    rsa_keys_deps,
    clerk_mock_jwks,
    clean_db,
):
    """verify_api_key must forward a real session to get_current_user.

    Regression (QA 2026-10): ``verify_api_key`` called ``get_current_user``
    without the ``db`` argument, so the dependency default (a ``Depends``
    marker) leaked into the Clerk resolution path. Every Clerk-authenticated
    request to the ``/v1/users`` router crashed with
    ``AttributeError: 'Depends' object has no attribute 'execute'`` (HTTP 500).
    """
    from app.api.deps import verify_api_key

    private, _ = rsa_keys_deps

    async with clean_db.session_factory() as session:
        user = User(
            email="legacy@example.com",
            password_hash="hash",
            role="job_seeker",
            full_name="Legacy Route User",
            clerk_id="user_legacy_route",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    token = _sign_token(private, {"sub": "user_legacy_route", "sess_id": "sess_legacy"})

    async with clean_db.session_factory() as session:
        from app.services import clerk_auth
        clerk_auth._jwks_cache.clear()

        with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mf:
            mf.return_value = clerk_mock_jwks

            result = await verify_api_key(f"Bearer {token}", session)

    assert result.auth_method == "clerk"
    assert result.id == user_id
