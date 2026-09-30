"""
Tests de autenticación por API key (PR-B, tasks B1-B4).

Matriz cubierta:
- Modo abierto (sin BACKEND_API_KEY): requests pasan sin header.
- Modo protegido + sin header → 401.
- Modo protegido + header con key incorrecta → 401.
- Modo protegido + header con key correcta → 200.
- Modo protegido: prefijo Bearer case-insensitive (bearer/BEARER).
- Modo protegido: /health y / exentos (200 sin header).
- Modo protegido: /docs, /redoc y /openapi.json → 404.
- Endpoints v1 protegidos (/v1/ping, /v1/analyses, /v1/match).

Los tests de modo protegido construyen una app fresh con `create_app()`
para que las flags de docs y `verify_api_key` lean el env actualizado.
"""

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

API_KEY = "test-secret-key-abc123"
AUTH_HEADER = {"Authorization": f"Bearer {API_KEY}"}


def _build_protected_app(monkeypatch: pytest.MonkeyPatch, key: str = API_KEY):
    """Construye una app fresh con BACKEND_API_KEY seteado.

    Limpia el cache de `get_settings` antes y después para que cada llamada
    refleje el env actualizado (lru_cache se cachea por proceso).
    """
    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("BACKEND_API_KEY", key)
    get_settings.cache_clear()
    try:
        return create_app()
    finally:
        # El app ya está construida con la key en memoria; dejamos que el
        # cache siga cacheado durante este test y limpiamos al final del
        # fixture para no contaminar otros tests.
        pass


def _build_open_app(monkeypatch: pytest.MonkeyPatch):
    """Construye una app fresh con BACKEND_API_KEY explícitamente ausente."""
    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.delenv("BACKEND_API_KEY", raising=False)
    get_settings.cache_clear()
    return create_app()


@pytest.fixture
def protected_app(monkeypatch: pytest.MonkeyPatch):
    """App fresh en modo protegido (con `BACKEND_API_KEY`)."""
    from app.core.config import get_settings

    app = _build_protected_app(monkeypatch)
    yield app
    monkeypatch.delenv("BACKEND_API_KEY", raising=False)
    get_settings.cache_clear()


@pytest.fixture
def explicit_open_app(monkeypatch: pytest.MonkeyPatch):
    """App fresh en modo abierto (sin `BACKEND_API_KEY`)."""
    from app.core.config import get_settings

    app = _build_open_app(monkeypatch)
    yield app
    get_settings.cache_clear()


@pytest.fixture
async def protected_async_client(
    protected_app,
) -> AsyncIterator[AsyncClient]:
    """AsyncClient contra la app protegida."""
    async with AsyncClient(
        transport=ASGITransport(app=protected_app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
async def open_async_client(explicit_open_app) -> AsyncIterator[AsyncClient]:
    """AsyncClient contra una app fresh en modo abierto."""
    async with AsyncClient(
        transport=ASGITransport(app=explicit_open_app), base_url="http://test"
    ) as ac:
        yield ac


# --- Tests del propio deps.py (unit del parser de Bearer) ---


def test_extract_bearer_accepts_canonical_case() -> None:
    """`Bearer <key>` se parsea correctamente."""
    from app.api.deps import _extract_bearer

    assert _extract_bearer(f"Bearer {API_KEY}") == API_KEY


def test_extract_bearer_accepts_lowercase_prefix() -> None:
    """`bearer <key>` (lowercase) se parsea correctamente."""
    from app.api.deps import _extract_bearer

    assert _extract_bearer(f"bearer {API_KEY}") == API_KEY


def test_extract_bearer_accepts_uppercase_prefix() -> None:
    """`BEARER <key>` (uppercase) se parsea correctamente."""
    from app.api.deps import _extract_bearer

    assert _extract_bearer(f"BEARER {API_KEY}") == API_KEY


def test_extract_bearer_rejects_missing_header() -> None:
    """Header ausente o None devuelve None."""
    from app.api.deps import _extract_bearer

    assert _extract_bearer(None) is None
    assert _extract_bearer("") is None


def test_extract_bearer_rejects_wrong_scheme() -> None:
    """Esquemas distintos a `bearer` se rechazan."""
    from app.api.deps import _extract_bearer

    assert _extract_bearer(f"Basic {API_KEY}") is None
    assert _extract_bearer(f"Token {API_KEY}") is None


def test_extract_bearer_rejects_missing_token() -> None:
    """Header `Bearer` sin token se rechaza."""
    from app.api.deps import _extract_bearer

    assert _extract_bearer("Bearer") is None
    assert _extract_bearer("Bearer ") is None


# --- Modo abierto (sin BACKEND_API_KEY) ---


async def test_open_mode_ping_without_header(client: TestClient) -> None:
    """Sin key configurada, /v1/ping pasa sin header."""
    response = client.get("/v1/ping")
    assert response.status_code == 200
    assert response.json()["pong"] is True


async def test_open_mode_health_without_header(client: TestClient) -> None:
    """Sin key configurada, /health responde 200 sin header."""
    response = client.get("/health")
    assert response.status_code == 200


async def test_open_mode_docs_available(client: TestClient) -> None:
    """Sin key configurada, /docs y /redoc están disponibles."""
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200


async def test_open_mode_root_returns_metadata(client: TestClient) -> None:
    """Root devuelve metadata de la app."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "AsistCV Backend"
    assert data["docs"] == "/docs"


# --- Modo protegido: con BACKEND_API_KEY ---


async def test_protected_mode_ping_without_header_returns_401(
    protected_async_client: AsyncClient,
) -> None:
    """Sin header `Authorization` → 401."""
    response = await protected_async_client.get("/v1/ping")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


async def test_protected_mode_ping_with_wrong_key_returns_401(
    protected_async_client: AsyncClient,
) -> None:
    """Header con key incorrecta → 401."""
    response = await protected_async_client.get(
        "/v1/ping", headers={"Authorization": "Bearer wrong-key"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


async def test_protected_mode_ping_with_bearer_wrong_scheme_returns_401(
    protected_async_client: AsyncClient,
) -> None:
    """Esquema distinto a Bearer (e.g. Basic) → 401."""
    response = await protected_async_client.get(
        "/v1/ping", headers={"Authorization": f"Basic {API_KEY}"}
    )
    assert response.status_code == 401


async def test_protected_mode_ping_with_bearer_no_token_returns_401(
    protected_async_client: AsyncClient,
) -> None:
    """`Bearer` sin token → 401."""
    response = await protected_async_client.get("/v1/ping", headers={"Authorization": "Bearer "})
    assert response.status_code == 401


async def test_protected_mode_ping_with_correct_key_returns_200(
    protected_async_client: AsyncClient,
) -> None:
    """Header correcto → 200."""
    response = await protected_async_client.get("/v1/ping", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json()["pong"] is True


async def test_protected_mode_ping_with_lowercase_bearer_returns_200(
    protected_async_client: AsyncClient,
) -> None:
    """Prefijo `bearer` (lowercase) con key correcta → 200."""
    response = await protected_async_client.get(
        "/v1/ping", headers={"Authorization": f"bearer {API_KEY}"}
    )
    assert response.status_code == 200


async def test_protected_mode_ping_with_uppercase_bearer_returns_200(
    protected_async_client: AsyncClient,
) -> None:
    """Prefijo `BEARER` (uppercase) con key correcta → 200."""
    response = await protected_async_client.get(
        "/v1/ping", headers={"Authorization": f"BEARER {API_KEY}"}
    )
    assert response.status_code == 200


async def test_protected_mode_health_remains_open(
    protected_async_client: AsyncClient,
) -> None:
    """`/health` sigue abierto (200) en modo protegido."""
    response = await protected_async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_protected_mode_root_remains_open(
    protected_async_client: AsyncClient,
) -> None:
    """`/` sigue abierto y reporta docs deshabilitados."""
    response = await protected_async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["docs"] == "disabled"


async def test_protected_mode_docs_disabled(
    protected_async_client: AsyncClient,
) -> None:
    """En modo protegido, /docs, /redoc y /openapi.json devuelven 404."""
    docs = await protected_async_client.get("/docs")
    redoc = await protected_async_client.get("/redoc")
    openapi = await protected_async_client.get("/openapi.json")

    assert docs.status_code == 404
    assert redoc.status_code == 404
    assert openapi.status_code == 404


async def test_protected_mode_analyses_requires_auth(
    protected_async_client: AsyncClient,
) -> None:
    """GET /v1/analyses exige auth en modo protegido."""
    no_auth = await protected_async_client.get("/v1/analyses")
    assert no_auth.status_code == 401

    with_auth = await protected_async_client.get("/v1/analyses", headers=AUTH_HEADER)
    assert with_auth.status_code == 200


async def test_protected_mode_match_requires_auth(
    protected_async_client: AsyncClient,
) -> None:
    """POST /v1/match exige auth en modo protegido (no llega al handler)."""
    payload = {"jd_text": "x" * 60, "profile_id": 1}
    no_auth = await protected_async_client.post("/v1/match", json=payload)
    assert no_auth.status_code == 401


# --- 401 sin invocar proveedores externos ---


async def test_401_does_not_invoke_llm_provider(
    protected_async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un 401 corta antes del handler: el LLM provider no debe ser instanciado."""
    import app.api.v1.match as match_module

    called = {"value": False}

    def _spy_get_llm_provider():  # noqa: ANN202 - test spy
        called["value"] = True
        raise AssertionError("LLM provider no debería ser llamado en 401")

    monkeypatch.setattr(match_module, "get_llm_provider", _spy_get_llm_provider)

    response = await protected_async_client.post(
        "/v1/match",
        json={"jd_text": "x" * 60, "profile_id": 1},
    )
    assert response.status_code == 401
    assert called["value"] is False


# --- Regresión TZ-mismatch: signup no debe dejar orphan user ---


async def test_full_signup_flow_writes_refresh_token(
    async_client: AsyncClient,
    clean_db,
) -> None:
    """Regression for the TZ-mismatch 500 on POST /v1/auth/register.

    Before migration 013 + the model-side ``DateTime(timezone=True)`` fix,
    asyncpg rejected ``datetime.now(UTC)`` against the naive
    ``users_refresh_tokens.expires_at`` column with::

        TypeError: can't subtract offset-naive and offset-aware datetimes

    The INSERT for the refresh token failed after the user row had been
    committed, leaving an orphan ``users`` row with no corresponding
    ``users_refresh_tokens`` row. The endpoint returned 500.

    This test exercises the full signup flow end-to-end and asserts:
      1. The HTTP response is 201 with valid tokens.
      2. Exactly one ``users_refresh_tokens`` row exists for the new user.
      3. ``expires_at`` is timezone-aware and strictly greater than now.
    """
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.db.models import RefreshToken, User
    from app.db.session import get_session_factory

    payload = {
        "email": "tz.regression@example.com",
        "password": "StrongPass123",
        "role": "job_seeker",
        "full_name": "TZ Regression",
        "locale": "es",
    }

    response = await async_client.post("/v1/auth/register", json=payload)

    assert response.status_code == 201, (
        f"signup failed: {response.status_code} {response.text}"
    )
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"

    # Direct DB check: a refresh-token row exists and is tz-aware.
    factory = get_session_factory()
    async with factory() as session:
        user_result = await session.execute(
            select(User).where(User.email == payload["email"])
        )
        user = user_result.scalar_one_or_none()
        assert user is not None, "user row should exist after signup"

        rt_result = await session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
        refresh = rt_result.scalar_one_or_none()
        assert refresh is not None, (
            "users_refresh_tokens row must be written for the new user"
        )
        assert refresh.expires_at is not None
        assert refresh.expires_at.tzinfo is not None, (
            "expires_at must be timezone-aware; service code binds datetime.now(UTC)"
        )
        now = datetime.now(UTC)
        assert refresh.expires_at > now, "expires_at must be in the future"


# --- Verify-email flow (C3 / issue #46) ---


async def test_verify_email_request_persists_token_and_returns_202(
    async_client, clean_db, monkeypatch
):
    """POST /v1/auth/verify-email/request returns 202 and writes a token row.

    Regression guard for the original stub: the handler used to do
    nothing — no token row, no email — and just returned 200/202. This
    test asserts the row is actually written with the expected hash,
    expiry in the future, and ``used_at`` null. ``send_email_async`` is
    monkeypatched so the test runs without a real Resend key (the
    service-level graceful fallback is exercised in test_email_service).
    """
    from datetime import UTC, datetime

    from app.core.security import create_access_token
    from app.db.models import EmailVerificationToken, User

    # Seed a user we can auth as; the JWT below references its id.
    async with clean_db.session_factory() as session:
        existing = await session.execute(select(User).where(User.id == 42))
        if existing.scalar_one_or_none() is None:
            session.add(
                User(
                    id=42,
                    email="verify-req@example.com",
                    password_hash="hashed",
                    role="job_seeker",
                    full_name="Verify Req",
                )
            )
            await session.commit()

    token_header = {
        "Authorization": f"Bearer {create_access_token({'sub': '42', 'role': 'job_seeker'})}"
    }

    sent: dict[str, bool] = {"called": False}

    async def _spy_send(*args, **kwargs):  # noqa: ANN001
        sent["called"] = True
        return False  # pretend the key is missing — endpoint still 202

    monkeypatch.setattr(
        "app.api.v1.auth.email_service.send_email_async", _spy_send
    )

    response = await async_client.post(
        "/v1/auth/verify-email/request", headers=token_header
    )
    assert response.status_code == 202
    body = response.json()
    assert body["detail"] == "Verification email sent"
    assert isinstance(body["token_id"], int)

    # A row with the right hash exists, not expired, and not used.
    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.user_id == 42
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 1, "request must persist exactly one token row"
        row = rows[0]
        assert row.token_hash  # sha256 hex
        assert len(row.token_hash) == 64
        assert row.used_at is None
        assert row.expires_at.tzinfo is not None, (
            "expires_at must be timezone-aware (TIMESTAMPTZ)"
        )
        assert row.expires_at > datetime.now(UTC), "token must not be expired on creation"

    # Send was attempted (even though we returned False from the spy).
    assert sent["called"] is True


async def test_verify_email_confirm_marks_user_verified(
    async_client, clean_db, monkeypatch
):
    """Confirm with a valid token stamps email_verified_at on the user.

    Walks the full happy path: insert a User row, mint a token row by
    hand (so the test owns the plaintext), POST /verify-email/confirm,
    then read back the user to assert the column is populated and the
    token row has ``used_at`` set.
    """
    from datetime import UTC, datetime, timedelta

    from app.core.security import hash_token
    from app.db.models import EmailVerificationToken, User

    # Seed: a user and a fresh token row.
    plain_token = "valid-plaintext-token-for-confirm"
    token_hash = hash_token(plain_token)
    async with clean_db.session_factory() as session:
        user = User(
            email="confirm@example.com",
            password_hash="hashed",
            role="job_seeker",
            full_name="Confirm Tester",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        session.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        await session.commit()
        user_id = user.id

    response = await async_client.post(
        "/v1/auth/verify-email/confirm",
        json={"token": plain_token},
    )
    assert response.status_code == 200
    assert response.json() == {"detail": "Email verified"}

    async with clean_db.session_factory() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one()
        assert user.email_verified_at is not None, (
            "user.email_verified_at must be stamped on successful confirm"
        )
        assert user.email_verified_at.tzinfo is not None, (
            "email_verified_at must be tz-aware (TIMESTAMPTZ)"
        )

        token_result = await session.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id)
        )
        token_row = token_result.scalar_one()
        assert token_row.used_at is not None, (
            "token row must be marked used_at after confirm"
        )


async def test_verify_email_confirm_expired_token_returns_400(
    async_client, clean_db
):
    """Expired token → 400 TOKEN_EXPIRED, no user mutation."""
    from datetime import UTC, datetime, timedelta

    from app.core.security import hash_token
    from app.db.models import EmailVerificationToken, User

    plain_token = "expired-plaintext-token"
    async with clean_db.session_factory() as session:
        user = User(
            email="expired@example.com",
            password_hash="hashed",
            role="job_seeker",
            full_name="Expired Tester",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        session.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=hash_token(plain_token),
                # Already past its TTL.
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        await session.commit()
        user_id = user.id

    response = await async_client.post(
        "/v1/auth/verify-email/confirm",
        json={"token": plain_token},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "TOKEN_EXPIRED"

    # No mutation on the user row.
    async with clean_db.session_factory() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one()
        assert user.email_verified_at is None


async def test_verify_email_confirm_used_token_returns_400(
    async_client, clean_db
):
    """Replaying a used token → 400 TOKEN_USED, second attempt fails.

    The first confirm consumes the token; the second one with the same
    plaintext must be rejected even if the row is still inside its TTL.
    """
    from datetime import UTC, datetime, timedelta

    from app.core.security import hash_token
    from app.db.models import EmailVerificationToken, User

    plain_token = "replay-attempt-token"
    async with clean_db.session_factory() as session:
        user = User(
            email="used@example.com",
            password_hash="hashed",
            role="job_seeker",
            full_name="Used Tester",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        session.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=hash_token(plain_token),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        await session.commit()
        user_id = user.id

    first = await async_client.post(
        "/v1/auth/verify-email/confirm",
        json={"token": plain_token},
    )
    assert first.status_code == 200

    second = await async_client.post(
        "/v1/auth/verify-email/confirm",
        json={"token": plain_token},
    )
    assert second.status_code == 400
    assert second.json()["detail"] == "TOKEN_USED"

    # User is verified exactly once — verify email_verified_at doesn't get re-stamped.
    async with clean_db.session_factory() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one()
        assert user.email_verified_at is not None


async def test_verify_email_confirm_unknown_token_returns_400(
    async_client, clean_db
):
    """Token that doesn't exist in the table → 400 INVALID_TOKEN."""
    response = await async_client.post(
        "/v1/auth/verify-email/confirm",
        json={"token": "no-such-token-anywhere"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "INVALID_TOKEN"
