"""
Tests de autenticaciÃ³n por API key (PR-B, tasks B1-B4).

Matriz cubierta:
- Modo abierto (sin BACKEND_API_KEY): requests pasan sin header.
- Modo protegido + sin header â†’ 401.
- Modo protegido + header con key incorrecta â†’ 401.
- Modo protegido + header con key correcta â†’ 200.
- Modo protegido: prefijo Bearer case-insensitive (bearer/BEARER).
- Modo protegido: /health y / exentos (200 sin header).
- Modo protegido: /docs, /redoc y /openapi.json â†’ 404.
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

    Limpia el cache de `get_settings` antes y despuÃ©s para que cada llamada
    refleje el env actualizado (lru_cache se cachea por proceso).
    """
    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("BACKEND_API_KEY", key)
    get_settings.cache_clear()
    try:
        return create_app()
    finally:
        # El app ya estÃ¡ construida con la key en memoria; dejamos que el
        # cache siga cacheado durante este test y limpiamos al final del
        # fixture para no contaminar otros tests.
        pass


def _build_open_app(monkeypatch: pytest.MonkeyPatch):
    """Construye una app fresh con BACKEND_API_KEY explÃ­citamente ausente."""
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
    """Sin key configurada, /docs y /redoc estÃ¡n disponibles."""
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
    """Sin header `Authorization` â†’ 401."""
    response = await protected_async_client.get("/v1/ping")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


async def test_protected_mode_ping_with_wrong_key_returns_401(
    protected_async_client: AsyncClient,
) -> None:
    """Header con key incorrecta â†’ 401."""
    response = await protected_async_client.get(
        "/v1/ping", headers={"Authorization": "Bearer wrong-key"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


async def test_protected_mode_ping_with_bearer_wrong_scheme_returns_401(
    protected_async_client: AsyncClient,
) -> None:
    """Esquema distinto a Bearer (e.g. Basic) â†’ 401."""
    response = await protected_async_client.get(
        "/v1/ping", headers={"Authorization": f"Basic {API_KEY}"}
    )
    assert response.status_code == 401


async def test_protected_mode_ping_with_bearer_no_token_returns_401(
    protected_async_client: AsyncClient,
) -> None:
    """`Bearer` sin token â†’ 401."""
    response = await protected_async_client.get("/v1/ping", headers={"Authorization": "Bearer "})
    assert response.status_code == 401


async def test_protected_mode_ping_with_correct_key_returns_200(
    protected_async_client: AsyncClient,
) -> None:
    """Header correcto â†’ 200."""
    response = await protected_async_client.get("/v1/ping", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json()["pong"] is True


async def test_protected_mode_ping_with_lowercase_bearer_returns_200(
    protected_async_client: AsyncClient,
) -> None:
    """Prefijo `bearer` (lowercase) con key correcta â†’ 200."""
    response = await protected_async_client.get(
        "/v1/ping", headers={"Authorization": f"bearer {API_KEY}"}
    )
    assert response.status_code == 200


async def test_protected_mode_ping_with_uppercase_bearer_returns_200(
    protected_async_client: AsyncClient,
) -> None:
    """Prefijo `BEARER` (uppercase) con key correcta â†’ 200."""
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
        raise AssertionError("LLM provider no deberÃ­a ser llamado en 401")

    monkeypatch.setattr(match_module, "get_llm_provider", _spy_get_llm_provider)

    response = await protected_async_client.post(
        "/v1/match",
        json={"jd_text": "x" * 60, "profile_id": 1},
    )
    assert response.status_code == 401
    assert called["value"] is False


# --- RegresiÃ³n TZ-mismatch: signup no debe dejar orphan user ---


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
    nothing â€” no token row, no email â€” and just returned 200/202. This
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
        return False  # pretend the key is missing â€” endpoint still 202

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
    """Expired token â†’ 400 TOKEN_EXPIRED, no user mutation."""
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
    """Replaying a used token â†’ 400 TOKEN_USED, second attempt fails.

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

    # User is verified exactly once â€” verify email_verified_at doesn't get re-stamped.
    async with clean_db.session_factory() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one()
        assert user.email_verified_at is not None


async def test_verify_email_confirm_unknown_token_returns_400(
    async_client, clean_db
):
    """Token that doesn't exist in the table â†’ 400 INVALID_TOKEN."""
    response = await async_client.post(
        "/v1/auth/verify-email/confirm",
        json={"token": "no-such-token-anywhere"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "INVALID_TOKEN"

# --- Absolute session lifetime: la rotaci├│n hereda el expiry original ---


async def _register_user(async_client, email: str) -> dict:
    """Registra un usuario v├¡a el endpoint real y devuelve el body del token pair."""
    response = await async_client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPass123",
            "role": "job_seeker",
            "full_name": "Session Lifetime",
            "locale": "es",
        },
    )
    assert response.status_code == 201, f"register failed: {response.text}"
    return response.json()


async def _refresh_rows(clean_db, email: str) -> list[dict]:
    """Filas de ``users_refresh_tokens`` del usuario, de la m├ís antigua a la m├ís nueva.

    Se devuelven como dicts planos (no instancias de ORM) para que los
    valores sobrevivan al cierre de la sesi├│n de test.
    """
    from sqlalchemy import select

    from app.db.models import RefreshToken, User

    async with clean_db.session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        rows = (
            await session.execute(
                select(RefreshToken)
                .where(RefreshToken.user_id == user.id)
                .order_by(RefreshToken.id)
            )
        ).scalars().all()
        return [
            {
                "id": row.id,
                "expires_at": row.expires_at,
                "consumed_at": row.consumed_at,
                "revoked_at": row.revoked_at,
            }
            for row in rows
        ]


async def test_rotation_inherits_seeded_expiry_not_fresh_ttl(
    async_client, clean_db
) -> None:
    """Una rotaci├│n hereda el expiry ORIGINAL; no recalcula now + JWT_REFRESH_TTL.

    La fila se siembra con un expiry distintivo (7 d├¡as) en lugar de dejar que
    ``register`` lo fije, para que la diferencia contra el TTL por defecto
    (30 d├¡as) sea inequ├¡voca en el assert.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.core.security import create_refresh_token, hash_token
    from app.db.models import RefreshToken, User

    email = "rotation.seeded@example.com"
    await _register_user(async_client, email)

    raw_token = create_refresh_token()
    seeded_expiry = datetime.now(UTC) + timedelta(days=7)

    async with clean_db.session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=seeded_expiry,
            )
        )
        await session.commit()

    response = await async_client.post(
        "/v1/auth/refresh", json={"refresh_token": raw_token}
    )
    assert response.status_code == 200, response.text

    rows = await _refresh_rows(clean_db, email)
    # _refresh_rows orders by id, so the last row is the newly minted one.
    # The invariant under test: rotation carries the presented token's
    # expiry forward untouched rather than recomputing now + jwt_refresh_ttl.
    # The absolute row count is irrelevant here (register() mints one row
    # and the seed adds another), so it is not asserted.
    rotated = rows[-1]
    assert rotated["expires_at"] == seeded_expiry, (
        "rotation must inherit the presented token's expiry (absolute lifetime); "
        f"original={seeded_expiry.isoformat()} "
        f"rotated={rotated['expires_at'].isoformat()}"
    )


async def test_rotation_inherits_expiry_end_to_end(async_client, clean_db) -> None:
    """Flujo real register ΓåÆ refresh: la fila rotada conserva el expiry de register."""
    from datetime import UTC, datetime

    email = "rotation.e2e@example.com"
    body = await _register_user(async_client, email)

    before = await _refresh_rows(clean_db, email)
    assert len(before) == 1
    original_expires_at = before[0]["expires_at"]
    assert original_expires_at > datetime.now(UTC)

    response = await async_client.post(
        "/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}
    )
    assert response.status_code == 200, response.text

    after = await _refresh_rows(clean_db, email)
    assert len(after) == 2
    assert after[-1]["expires_at"] == original_expires_at, (
        "rotation must inherit the original absolute expiry; "
        f"original={original_expires_at.isoformat()} "
        f"rotated={after[-1]['expires_at'].isoformat()}"
    )
    # The presented token is retired, not deleted: it stays as evidence.
    assert after[0]["consumed_at"] is not None


async def test_repeated_rotation_never_extends_lifetime(
    async_client, clean_db
) -> None:
    """Rotar N veces NO extiende la vida de la sesi├│n.

    Este es el test que falla con el TTL deslizante: cada rotaci├│n empujaba
    el expiry 30 d├¡as hacia adelante, as├¡ que el l├¡mite era inalcanzable.
    """
    from datetime import UTC, datetime, timedelta

    email = "rotation.chain@example.com"
    body = await _register_user(async_client, email)
    original_expires_at = (await _refresh_rows(clean_db, email))[0]["expires_at"]

    rotations = 5
    token = body["refresh_token"]
    for attempt in range(1, rotations + 1):
        response = await async_client.post(
            "/v1/auth/refresh", json={"refresh_token": token}
        )
        assert response.status_code == 200, (
            f"rotation {attempt} failed: {response.status_code} {response.text}"
        )
        token = response.json()["refresh_token"]

    rows = await _refresh_rows(clean_db, email)
    assert len(rows) == rotations + 1, (
        f"expected 1 initial + {rotations} rotated rows, got {len(rows)}"
    )

    for row in rows:
        assert row["expires_at"] == original_expires_at, (
            f"row {row['id']} drifted: expected {original_expires_at.isoformat()}, "
            f"got {row['expires_at'].isoformat()}"
        )

    # The absolute window is still the original one, not 30 days from now.
    remaining = rows[-1]["expires_at"] - datetime.now(UTC)
    assert timedelta(days=29) < remaining <= timedelta(days=30), (
        f"absolute window should still be the original ~30 days, got {remaining}"
    )


async def test_expired_absolute_token_rejected_even_if_otherwise_valid(
    async_client, clean_db
) -> None:
    """Un token pasado su expiry absoluto se rechaza aunque la fila sea v├ílida.

    ``consumed_at`` y ``revoked_at`` quedan en NULL a prop├│sito: el rechazo
    tiene que venir del expiry, no de un flag de revocaci├│n.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.db.models import RefreshToken, User

    email = "rotation.expired@example.com"
    body = await _register_user(async_client, email)

    expired_expiry = datetime.now(UTC) - timedelta(seconds=1)
    async with clean_db.session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        token = (
            await session.execute(
                select(RefreshToken).where(RefreshToken.user_id == user.id)
            )
        ).scalar_one()
        token.expires_at = expired_expiry
        token.consumed_at = None
        token.revoked_at = None
        await session.commit()

    response = await async_client.post(
        "/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}
    )
    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "TOKEN_INVALID"

    # No new row minted, and the presented one was not consumed.
    rows = await _refresh_rows(clean_db, email)
    assert len(rows) == 1
    assert rows[0]["consumed_at"] is None
    assert rows[0]["revoked_at"] is None


# --- POST /internal/auth/refresh-tokens/cleanup ---


def _pin_sweeper_settings(monkeypatch: pytest.MonkeyPatch, key: str | None) -> None:
    """Fija BACKEND_API_KEY (o la borra) para el sweeper y refresca el cache.

    Se ejercita el auth REAL (hmac.compare_digest contra settings) en vez de
    monkeypatchear ``_verify_api_key``: este endpoint borra filas, y un test
    que se saltee la verificaci├│n no prueba nada sobre el auth.
    """
    from app.core.config import get_settings

    if key is None:
        monkeypatch.delenv("BACKEND_API_KEY", raising=False)
    else:
        monkeypatch.setenv("BACKEND_API_KEY", key)
    get_settings.cache_clear()


async def test_refresh_token_cleanup_401_without_api_key(
    async_client, clean_db, monkeypatch
) -> None:
    """Sin ``X-Backend-API-Key`` ΓåÆ 401 y NO se borra ninguna fila."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.core.security import create_refresh_token, hash_token
    from app.db.models import RefreshToken, User

    email = "cleanup.401@example.com"
    await _register_user(async_client, email)

    async with clean_db.session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_token(create_refresh_token()),
                expires_at=datetime.now(UTC) - timedelta(days=1),
                consumed_at=datetime.now(UTC) - timedelta(days=100),
            )
        )
        await session.commit()

    _pin_sweeper_settings(monkeypatch, "sweeper-test-key")
    try:
        response = await async_client.post("/internal/auth/refresh-tokens/cleanup")
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "UNAUTHORIZED"

        assert len(await _refresh_rows(clean_db, email)) == 2, (
            "an unauthorized sweep must not delete anything"
        )
    finally:
        from app.core.config import get_settings

        get_settings.cache_clear()


async def test_refresh_token_cleanup_fails_closed_when_key_unset(
    async_client, clean_db, monkeypatch
) -> None:
    """Sin BACKEND_API_KEY configurada el endpoint es 401, no un delete abierto."""
    _pin_sweeper_settings(monkeypatch, None)
    try:
        response = await async_client.post(
            "/internal/auth/refresh-tokens/cleanup",
            headers={"X-Backend-API-Key": "anything-goes"},
        )
        assert response.status_code == 401, response.text
    finally:
        from app.core.config import get_settings

        get_settings.cache_clear()


async def test_refresh_token_cleanup_deletes_old_terminal_rows_only(
    async_client, clean_db, monkeypatch
) -> None:
    """El sweep borra consumidas/revocadas fuera de ventana y deja el resto.

    La ventana se ancla en el timestamp TERMINAL (``consumed_at`` /
    ``revoked_at``), no en ``created_at``: una fila creada hace 200 d├¡as y
    rotada ayer sigue siendo evidencia y se conserva.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.core.security import create_refresh_token, hash_token
    from app.db.models import RefreshToken, User

    email = "cleanup.sweep@example.com"
    await _register_user(async_client, email)
    now = datetime.now(UTC)

    async with clean_db.session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        uid = user.id

        def _row(**kwargs) -> RefreshToken:
            return RefreshToken(
                user_id=uid,
                token_hash=hash_token(create_refresh_token()),
                **kwargs,
            )

        # Elegibles: terminales y fuera de la ventana de 90 d├¡as.
        old_consumed = _row(
            expires_at=now - timedelta(days=5),
            created_at=now - timedelta(days=200),
            consumed_at=now - timedelta(days=100),
        )
        old_revoked = _row(
            expires_at=now - timedelta(days=3),
            created_at=now - timedelta(days=200),
            revoked_at=now - timedelta(days=95),
        )
        # Conservadas: terminales pero recientes.
        recent_consumed = _row(
            expires_at=now + timedelta(days=10),
            created_at=now - timedelta(days=20),
            consumed_at=now - timedelta(days=2),
        )
        recent_revoked = _row(
            expires_at=now - timedelta(days=1),
            created_at=now - timedelta(days=20),
            revoked_at=now - timedelta(days=3),
        )
        # Conservada: activa (nunca consumida ni revocada) y vencida de
        # todos modos. Borrarla cortar├¡a el ├║nico hilo de una sesi├│n viva.
        active = _row(
            expires_at=now + timedelta(days=20),
            created_at=now - timedelta(days=200),
        )
        # Conservada: creada hace mucho, terminalizada hace poco.
        old_created_recent_terminal = _row(
            expires_at=now + timedelta(days=5),
            created_at=now - timedelta(days=200),
            consumed_at=now - timedelta(days=1),
        )

        session.add_all(
            [
                old_consumed,
                old_revoked,
                recent_consumed,
                recent_revoked,
                active,
                old_created_recent_terminal,
            ]
        )
        await session.commit()
        kept_ids = {
            recent_consumed.id,
            recent_revoked.id,
            active.id,
            old_created_recent_terminal.id,
        }

    _pin_sweeper_settings(monkeypatch, "sweeper-test-key")
    try:
        response = await async_client.post(
            "/internal/auth/refresh-tokens/cleanup",
            headers={"X-Backend-API-Key": "sweeper-test-key"},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"deleted": 2}

        rows = await _refresh_rows(clean_db, email)
        # La fila de register sobrevive + las 4 conservadas.
        assert {row["id"] for row in rows if row["id"] in kept_ids} == kept_ids
        assert len(rows) == 5
    finally:
        from app.core.config import get_settings

        get_settings.cache_clear()


async def test_refresh_token_cleanup_keeps_everything_inside_window(
    async_client, clean_db, monkeypatch
) -> None:
    """Un sweep sobre datos recientes devuelve deleted=0 (sweep vac├¡o Γëá error)."""
    email = "cleanup.empty@example.com"
    await _register_user(async_client, email)

    _pin_sweeper_settings(monkeypatch, "sweeper-test-key")
    try:
        response = await async_client.post(
            "/internal/auth/refresh-tokens/cleanup",
            headers={"X-Backend-API-Key": "sweeper-test-key"},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"deleted": 0}
        assert len(await _refresh_rows(clean_db, email)) == 1
    finally:
        from app.core.config import get_settings

        get_settings.cache_clear()

