"""
Tests de autenticación por API key (PR-B, tasks B1-B4).

Matriz cubierta:
- Modo abierto (sin BACKEND_API_KEY): requests pasan sin header.
- Modo protegido + sin header → 401.
- Modo protegido + header con key incorrecta → 401.
- Modo protegido + header con key correcta → 200.
- Modo protegido: prefijo Bearer case-insensitive (bearer/BEARER).
- Modo protegido: /health y / exentos (200 sin header).
- Modo protegido: /docs, /redoc, /openapi.json → 404.
- Endpoints v1 protegidos (/v1/ping, /v1/analyses, /v1/match).

Los tests de modo protegido construyen una app fresh con `create_app()`
para que las flags de docs y `verify_api_key` lean el env actualizado.
"""

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

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
