"""
Pytest configuration and fixtures.
"""
import asyncio
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session as SyncSession
from sqlalchemy.pool import NullPool

# URL de la base de datos de test. Prioriza URLs con driver (+asyncpg) — las
# sin driver (como la del CI: postgresql://) hay que normalizarlas.
TEST_DATABASE_URL = (
    os.environ.get("TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql+asyncpg://asistcv:asistcv@localhost:5433/asistcv_test"
)

# Normalizar: si la URL viene sin driver (ej. CI exporta postgresql://), le
# agregamos +asyncpg para que SQLAlchemy no caiga en psycopg2 fallback.
if TEST_DATABASE_URL.startswith("postgresql://") and "+" not in TEST_DATABASE_URL.split("/", 1)[0]:
    TEST_DATABASE_URL = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Rol NO-superuser y NOBYPASSRLS para los tests de RLS. Los superusers
# BYPASEAN Row Level Security siempre (incluso con FORCE), así que los
# tests de aislamiento deben correr como un rol equivalente al usuario de
# app en producción (Neon: owner sin superuser). Ver tests/test_rls.py.
RLS_TEST_ROLE = "asistcv_rls"

# CRITICAL: Set DATABASE_URL to test DB BEFORE importing app modules
# This ensures the module-level engine cache in session.py uses the test DB
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.main import app  # noqa: E402

# Estado global: el setup de la DB de test corre una sola vez por sesión,
# aunque pytest-asyncio re-instancie fixtures (loop scopes distintos).
_alembic_ready = False
_test_engine = None
_test_factory = None


@event.listens_for(SyncSession, "after_begin")
def _bind_service_rls(session, transaction, connection):
    """Contexto RLS de servicio ('0') en cada transacción de test.

    La migración 011 activa FORCE ROW LEVEL SECURITY: sin GUC, cualquier
    SELECT/INSERT sobre tablas protegidas no devuelve filas / falla. Los
    tests que escriben directo vía session_factory (y los endpoints en
    modo abierto) corren como servicio, igual que el MCP en producción.
    ``SET LOCAL`` es transaccional: se re-aplica solo en cada BEGIN, así
    que los re-reads posteriores a un commit siguen viendo filas. Los
    tests de RLS (tests/test_rls.py) bindan contextos de usuario
    explícitos con conexiones crudas, sin pasar por este listener.
    """
    connection.execute(text("SET LOCAL app.current_user_id = '0'"))
    connection.execute(text("SET LOCAL app.user_role = 'service'"))


def _to_sync_url(url: str) -> str:
    """Devuelve la URL como dict de kwargs para psycopg.connect().

    psycopg.connect() con un string de URL cae en psycopg2 como fallback.
    La forma correcta es pasar los componentes como kwargs (host, port,
    user, password, dbname) — eso fuerza psycopg 3.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return {
        "host": parsed.hostname,
        "port": parsed.port,
        "user": parsed.username,
        "password": parsed.password,
        "dbname": parsed.path.lstrip("/"),
    }


def _ensure_database_exists(url: str) -> None:
    """Crea la base de test si no existe (entorno local; en CI ya existe).

    Espera un string; internamente lo parsea a kwargs para psycopg 3.
    """
    import psycopg

    conninfo = _to_sync_url(url)

    # Para crear la DB, conectamos primero a la DB postgres default
    admin_conninfo = dict(conninfo)
    admin_conninfo["dbname"] = "postgres"

    try:
        with psycopg.connect(**admin_conninfo) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (conninfo["dbname"],)
            ).fetchone()
            if not exists:
                conn.autocommit = True
                conn.execute(f'CREATE DATABASE "{conninfo["dbname"]}"')
    except psycopg.OperationalError as exc:
        raise RuntimeError(
            f"No se pudo conectar a Postgres para preparar la base de test. "
            f"Levantá el DB local con 'make db-up' o definí TEST_DATABASE_URL/DATABASE_URL. "
            f"Detail: {exc}"
        ) from exc


def _run_alembic_upgrade() -> None:
    """Corre `alembic upgrade head` de forma síncrona (thread worker)."""
    from alembic.config import Config

    from alembic import command

    command.upgrade(Config("alembic.ini"), "head")


def _ensure_rls_role_and_ownership() -> None:
    """Crea el rol NOBYPASSRLS de test y le transfiere los objetos.

    El usuario que levanta el docker local (y el de CI) suele ser
    superuser: con RLS activo, un superuser bypasea las policies aunque
    la tabla use FORCE. REASSIGN OWNED deja el esquema en manos de un rol
    equivalente al usuario de app en producción (owner no-superuser), que
    es exactamente el escenario que las policies de la migración 011
    deben cubrir. Best-effort: si el usuario de test no puede reasignar,
    cae a GRANTs explícitos (el rol igual queda sujeto a RLS por no ser
    owner ni superuser).
    """
    import psycopg

    conninfo = _to_sync_url(TEST_DATABASE_URL)
    db_user = conninfo["user"] or "asistcv"

    with psycopg.connect(**conninfo) as conn:
        conn.autocommit = True
        conn.execute(
            f"DO $do$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RLS_TEST_ROLE}') THEN "
            f"CREATE ROLE {RLS_TEST_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS; "
            f"END IF; END $do$"
        )
        conn.execute(f"GRANT USAGE ON SCHEMA public TO {RLS_TEST_ROLE}")
        try:
            conn.execute(f"REASSIGN OWNED BY {db_user} TO {RLS_TEST_ROLE}")
        except psycopg.Error:
            conn.execute(
                f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {RLS_TEST_ROLE}"
            )
            conn.execute(
                f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {RLS_TEST_ROLE}"
            )


@pytest.fixture
async def test_db():
    """Base de datos de test aislada con migraciones aplicadas.

    Estado determinista: resetea el schema public y re-aplica migraciones
    una sola vez por sesión, y re-aplica si otro módulo las bajó (e.g.
    `tests/test_migrations.py` hace `downgrade base` al final). Alembic
    usa asyncio.run internamente, así que se ejecuta en un thread worker
    para no chocar con el event loop de los tests.
    """
    global _alembic_ready, _test_engine, _test_factory

    needs_setup = not _alembic_ready

    if _alembic_ready:
        probe = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with probe.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name='profiles'"
                )
            )
            needs_setup = result.scalar() is None
        await probe.dispose()

    if needs_setup:
        os.environ["DATABASE_URL"] = TEST_DATABASE_URL

        _ensure_database_exists(TEST_DATABASE_URL)

        reset_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with reset_engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await reset_engine.dispose()

        await asyncio.to_thread(_run_alembic_upgrade)
        await asyncio.to_thread(_ensure_rls_role_and_ownership)

        # Keep DATABASE_URL set to TEST_DATABASE_URL so that get_session_context() uses test DB
        # The original_db_url is kept only for reference if needed later
        # Don't restore DATABASE_URL - tests depend on it pointing to test DB

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
        # Truncate core tables that always exist plus user-related tables
        # (incluye las tablas protegidas por RLS agregadas en Sprint 2;
        # TRUNCATE no está sujeto a RLS, corre como el user de test).
        # Use CASCADE to handle dependent tables
        await conn.execute(
            text("TRUNCATE analyses, job_descriptions, profiles, audit_uploads, audit_funnel_events, users, users_refresh_tokens, token_revocation, auth_login_attempts, auth_security_events, subscriptions, payments, stripe_webhook_events, usage_counters, users_cvs, recruiter_candidates, recruiter_candidates_cvs, recruiter_analyses, recruiter_consents, recruiter_audit_log CASCADE")
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
