"""
Pytest configuration and fixtures.
"""
import asyncio
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.main import app

# URL de la base de datos de test (misma cadena de fallback que test_migrations):
# TEST_DATABASE_URL -> DATABASE_URL (definida en CI) -> default local (5433).
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://asistcv:asistcv@localhost:5433/asistcv_test",
)

# Estado global: el setup de la DB de test corre una sola vez por sesión,
# aunque pytest-asyncio re-instancie fixtures (loop scopes distintos).
_alembic_ready = False
_test_engine = None
_test_factory = None


def _to_sync_url(url: str) -> str:
    """Devuelve la URL sync para tareas admin con psycopg 3.

    psycopg.connect() acepta `postgresql://` (sin driver) — psycopg 3 lo
    interpreta correctamente. NO usar `postgresql+psycopg://` (psycopg 3 lo
    rechaza como connection string, solo acepta esa forma como DSN parseado).
    """
    if "+asyncpg" in url:
        return url.replace("+asyncpg", "")
    return url


def _ensure_database_exists(url: str) -> None:
    """Crea la base de test si no existe (entorno local; en CI ya existe)."""
    from urllib.parse import urlparse, urlunparse

    import psycopg

    parsed = urlparse(url)
    dbname = parsed.path.lstrip("/")
    admin_url = urlunparse(parsed._replace(path="/postgres"))

    try:
        with psycopg.connect(admin_url) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
            ).fetchone()
            if not exists:
                conn.autocommit = True
                conn.execute(f'CREATE DATABASE "{dbname}"')
    except psycopg.OperationalError as exc:
        raise RuntimeError(
            f"No se pudo conectar a Postgres para preparar la base de test "
            f"({admin_url}). Levantá el DB local con 'make db-up' o definí "
            f"TEST_DATABASE_URL/DATABASE_URL."
        ) from exc


def _run_alembic_upgrade() -> None:
    """Corre `alembic upgrade head` de forma síncrona (thread worker)."""
    from alembic.config import Config

    from alembic import command

    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
async def test_db():
    """Base de datos de test aislada con migraciones aplicadas.

    Estado determinista: resetea el schema public y re-aplica migraciones una
    sola vez por sesión. Alembic usa asyncio.run internamente, así que se
    ejecuta en un thread worker para no chocar con el event loop de los tests.
    """
    global _alembic_ready, _test_engine, _test_factory

    if not _alembic_ready:
        original_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = TEST_DATABASE_URL

        _ensure_database_exists(_to_sync_url(TEST_DATABASE_URL))

        reset_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with reset_engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await reset_engine.dispose()

        await asyncio.to_thread(_run_alembic_upgrade)

        if original_db_url:
            os.environ["DATABASE_URL"] = original_db_url
        elif "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

        _test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        _test_factory = async_sessionmaker(
            _test_engine, class_=AsyncSession, expire_on_commit=False
        )
        _alembic_ready = True

    yield SimpleNamespace(engine=_test_engine, session_factory=_test_factory)


@pytest.fixture
async def clean_db(test_db):
    """Trunca las tablas de test al terminar cada test (aislación de datos)."""
    yield test_db
    async with test_db.engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE analyses, job_descriptions, profiles RESTART IDENTITY CASCADE")
        )


@pytest.fixture
def override_get_session(clean_db):
    """Reemplaza la dependency get_session por sesiones del DB de test."""
    from app.db.session import get_session

    async def _override():
        async with clean_db.session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    yield
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def patch_match_db(clean_db, monkeypatch):
    """Apunta get_session_context del flujo match al DB de test."""
    import app.api.v1.match as match_module

    factory = clean_db.session_factory

    @asynccontextmanager
    async def _session_context():
        async with factory() as session:
            yield session

    monkeypatch.setattr(match_module, "get_session_context", _session_context)


@pytest.fixture
async def create_profile(clean_db):
    """Factory para crear perfiles en el DB de test."""
    from app.db.models import Profile

    async def _create(**kwargs) -> Profile:
        async with clean_db.session_factory() as session:
            profile = Profile(**kwargs)
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            return profile

    return _create


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI application."""
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Cliente HTTP asíncrono contra la app (mismo event loop que los tests)."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def settings():
    """Get application settings."""
    from app.core.config import get_settings
    return get_settings()
