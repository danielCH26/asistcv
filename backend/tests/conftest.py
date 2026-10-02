"""
Pytest configuration and fixtures.
"""
import asyncio
import os
import re
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

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

# ---------------------------------------------------------------------------
# GUARD DE SEGURIDAD DE LA BASE DE TEST (fail-closed)
# ---------------------------------------------------------------------------
# Este suite es DESTRUCTIVO por diseño: `test_db` corre `DROP SCHEMA public
# CASCADE` y `clean_db` trunca ~20 tablas (users, payments, audit_uploads,
# subscriptions, ...). La resolución de arriba hace fallback a DATABASE_URL,
# que es la variable de la APLICACIÓN (backend/app/db/session.py lee el mismo
# nombre), así que exportar la connection string de producción y correr
# `pytest` borra el schema de producción.
#
# Todo lo de abajo decide UNA vez, en tiempo de import, si esta corrida puede
# tocar el destino resuelto. El import es el único lugar hermético:
#   * corre antes de cualquier fixture, o sea antes de `_ensure_database_exists`
#     y antes del DROP SCHEMA;
#   * `tests/test_migrations.py` resuelve su PROPIA TEST_DATABASE_URL y corre
#     `alembic downgrade base` SIN pasar por `test_db`. Un guard adentro de ese
#     fixture no lo cubriría; un error de import del conftest corta la sesión
#     entera, incluido ese módulo.
# El fallo es una excepción, NO un skip: los tests no se saltean, la sesión no
# arranca, y nada puede alcanzar una sentencia destructiva.

#: URL de la APLICACIÓN, capturada ANTES de que la línea de más abajo la
#: sobrescriba con la URL de test. Después de ese assignment es irrecuperable.
_APP_DATABASE_URL = os.environ.get("DATABASE_URL")

#: Opt-in explícito: "afirmo que este destino es una base de test descartable".
#: Cubre el nombre no-disposable y el host remoto. NUNCA cubre el check de
#: "misma base" (ver `_assert_test_database_is_disposable`).
ALLOW_REMOTE_TEST_DATABASE = "ALLOW_REMOTE_TEST_DATABASE"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: Loopback = el path de Docker que el suite ya usa hoy (make db-up -> 5433).
#: No requiere opt-in. El host vacío es un unix socket local, también.
_LOOPBACK_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1", "0.0.0.0"})

#: Una base sólo es descartable si "test" es un token entero. Pasan
#: `asistcv_test`, `asistcv-test`, `test`; NO pasan `latest` ni `asistcv`
#: (los nombres reales de producción: `asistcv`, `neondb`, `postgres`).
_DISPOSABLE_DB_NAME_RE = re.compile(r"(?<![a-z])test(?![a-z])", re.IGNORECASE)


class TestDatabaseSafetyError(RuntimeError):
    """El guard de la base de test rechazó el destino. Aborta la sesión."""


def _db_identity(url: str) -> dict[str, object] | None:
    """Identidad comparable de una URL de Postgres, o None si no es comprobable.

    Descarta el driver (`postgresql+asyncpg` -> `postgresql`, alias `postgres`)
    y la query string (`?sslmode=require`): ninguna de las dos cambia a qué base
    se conecta, y comparar la URL cruda daría falsos negativos (la misma base
    escrita de dos maneras se medirían como distintas). Si la base no se puede
    determinar, devuelve None y el guard falla cerrado: una identidad
    incompleta haría que el check de "misma base" no detecte la coincidencia,
    que es justo la dirección peligrosa del error.
    """
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return None

    host = (parsed.hostname or "").lower()
    database = parsed.path.lstrip("/")
    if not database:
        # Las URLs pooler de Neon pueden llevar la base como query param.
        query = parse_qs(parsed.query)
        database = (query.get("database") or query.get("dbname") or [""])[0]

    scheme = parsed.scheme.split("+", 1)[0].lower()
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql"

    return {
        "scheme": scheme,
        "host": host,
        "port": port,
        "database": database,
        "user": parsed.username or "",
    }


def _redact(url: str) -> str:
    """La URL como la ve el operador, con el password oculto.

    El mensaje viaja a logs de CI: la password no va, aunque el resto sí.
    """
    identity = _db_identity(url)
    if identity is None:
        return url
    user = str(identity["user"])
    port = identity["port"]
    host = identity["host"] or "<socket local>"
    netloc = f"{user}:***@{host}" if user else f"***@{host}"
    if port:
        netloc = f"{netloc}:{port}"
    return (
        f"{identity['scheme']}://{netloc}/{identity['database'] or '<sin base>'}"
    )


def _refuse(
    reason: str,
    variable: str,
    value: str,
    remedy: str,
    *,
    value_label: str = "Valor rechazado",
    redact: bool = True,
) -> None:
    """Aborta la sesión con un mensaje que nombra variable, valor y arreglo.

    El texto sale ASCII a propósito: este mensaje se lee apurado en un log de
    CI, y una consola Windows en cp1252 (el default de `chcp` en many boxes)
    vuelve mojibake cualquier tilde y lo vuelve ilegible justo cuando hay que
    actuar rápido. Los comentarios del source sí llevan tildes.
    """
    shown = _redact(value) if redact else value
    raise TestDatabaseSafetyError(
        "\n"
        + "=" * 78
        + "\n"
        "BLOQUEADO: fallo el guard de seguridad de la base de test.\n"
        "BLOCKED: the test database safety guard tripped.\n"
        + "=" * 78
        + "\n"
        f"  Motivo / reason   : {reason}\n"
        f"  Variable          : {variable}\n"
        f"  {value_label:<18}: {shown}\n"
        "\n"
        "Este suite es DESTRUCTIVO por diseno: corre `DROP SCHEMA public CASCADE`\n"
        "y `TRUNCATE ... CASCADE` sobre ~20 tablas (users, payments, audit_uploads,\n"
        "subscriptions, ...). Solo puede correr contra una base DESCARTABLE.\n"
        "\n"
        f"  Para destrabarlo / to unblock:\n    {remedy}\n"
        "\n"
        "Los tests NO se saltean: la sesion aborta en collection, antes de\n"
        "cualquier fixture, asi que nada puede alcanzar el DROP SCHEMA.\n" + "=" * 78
    )


def _assert_test_database_is_disposable() -> None:
    """Único check autoritativo. Corre en import y se re-chequea en `test_db`.

    Refusa (fail-closed) cuando:
      1. la URL no es parseable o no identifica una base;
      2. la URL de test y la de la app apuntan a la MISMA base;
      3. el nombre de la base no es demostrablemente descartable;
      4. el host no es loopback y no hubo opt-in explícito.
    """
    raw_test_url = os.environ.get("TEST_DATABASE_URL")
    value = TEST_DATABASE_URL
    identity = _db_identity(value)

    # (1) ¿Se puede probar siquiera a qué base se va a conectar? Se exige un
    # scheme de Postgres real y un nombre de base. El host vacío es un unix
    # socket local y es válido; la base vacía no lo es.
    if (
        identity is None
        or identity["scheme"] != "postgresql"
        or not identity["database"]
    ):
        _refuse(
            reason=("la URL de test no es parseable como URL de Postgres o no "
                    "nombra una base, asi que no se puede probar que sea "
                    "descartable"),
            variable="TEST_DATABASE_URL",
            value=value,
            remedy=("export TEST_DATABASE_URL='postgresql+asyncpg://USUARIO:PASS@"
                    "HOST:PUERTO/asistcv_test'"),
        )
    assert identity is not None  # para mypy; el _refuse de arriba no retorna

    allowed = (os.environ.get(ALLOW_REMOTE_TEST_DATABASE) or "").strip().lower() in _TRUTHY

    # (2) Misma base que la app. Se compara la identidad completa
    # (host + puerto + base + usuario), NO el host solo — ver el comentario
    # largo de `_same_database_as_app` abajo.
    if _same_database_as_app(identity, raw_test_url):
        _refuse(
            reason=("la URL de test y la DATABASE_URL de la app apuntan a la "
                    "MISMA base (host + puerto + base + usuario identicos)"),
            variable="TEST_DATABASE_URL",
            value=value,
            remedy=("apunta TEST_DATABASE_URL a una base separada y descartable "
                    "(ej. un branch de Neon con su propia base, o "
                    "asistcv_test en localhost:5433). No hay flag para saltear "
                    "este check."),
        )

    # (3) Nombre descartable. `neondb` / `asistcv` no lo son.
    if not _DISPOSABLE_DB_NAME_RE.search(str(identity["database"])):
        if not allowed:
            _refuse(
                reason=(f"el nombre de la base '{identity['database']}' no es "
                        "demostrablemente descartable (no contiene 'test' como token)"),
                variable="TEST_DATABASE_URL",
                value=value,
                remedy=("renombra la base a algo con 'test' (asistcv_test, "
                        "asistcv-test) o, si de verdad es descartable, exporta "
                        f"{ALLOW_REMOTE_TEST_DATABASE}=1"),
            )

    # (4) Host remoto sin opt-in.
    if str(identity["host"]) not in _LOOPBACK_HOSTS and not allowed:
        _refuse(
            reason=(f"el host '{identity['host']}' no es loopback: la suite no "
                    "toca bases remotas sin opt-in explicito"),
            variable=f"{ALLOW_REMOTE_TEST_DATABASE} (no seteado)",
            value=TEST_DATABASE_URL,
            remedy=(f"export {ALLOW_REMOTE_TEST_DATABASE}=1 si ese destino es "
                    "una base/branch de test descartable (p. ej. un branch de "
                    "Neon aislado). Ver docs/CI_SETUP.md."),
            value_label="Destino a proteger",
        )


def _same_database_as_app(identity: dict[str, object], raw_test_url: str | None) -> bool:
    """¿La base de test ES la base de la app?

    Semántica (importante, y NO es "mismo host"):

    * Se compara la identidad COMPLETA: host + puerto + base + usuario. Sólo la
      igualdad exacta es "la misma base". Un host igual NO alcanza, en ninguna
      de las dos direcciones:
        - si dijera "mismo host ⇒ misma base", una branch de Neon (mismo host,
          base distinta) quedaría bloqueada: falso positivo, pierde el path
          que el maintainer quiere usar;
        - si dijera "mismo host ⇒ base distinta", una base de producción que
          convive con otra base en el mismo endpoint pasaría: falso negativo,
          exactamente el agujero que este guard existe para cerrar.
      La base es el discriminante; el host es necesario pero no suficiente.
    * El check sólo aplica si TEST_DATABASE_URL fue seteado EXPLÍCITAMENTE. Sin
      él, el destino de test ES la DATABASE_URL por declaración propia (que es
      justo lo que hace CI: exporta `DATABASE_URL` al Postgres descartable del
      service container, ver docs/CI_SETUP.md). Comparar contra sí mismo ahí no
      preuve nada y sólo rompería un workflow seguro y documentado. Ese caso lo
      cubren los checks (3) y (4): una DATABASE_URL de producción es remota y
      no se llama `*_test`, así que cae igual.
    """
    if not raw_test_url or not _APP_DATABASE_URL:
        return False
    app = _db_identity(_APP_DATABASE_URL)
    if app is None or not app["database"]:
        return False
    return all(identity[key] == app[key] for key in ("scheme", "host", "port", "database", "user"))


# Se evalúa al IMPORT del conftest, antes de que exista cualquier fixture y
# antes de que `test_db` pueda llegar al DROP SCHEMA.
_assert_test_database_is_disposable()

# Rol NO-superuser y NOBYPASSRLS para los tests de RLS. Los superusers
# BYPASEAN Row Level Security siempre (incluso con FORCE), así que los
# tests de aislamiento deben correr como un rol equivalente al usuario de
# app en producción (Neon: owner sin superuser). Ver tests/test_rls.py.
RLS_TEST_ROLE = "asistcv_rls"

# CRITICAL: Set DATABASE_URL to test DB BEFORE importing app modules
# This ensures the module-level engine cache in session.py uses the test DB
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# The JWT signing key is fail-closed (see app/core/config.py): Settings refuses
# to validate while jwt_secret is the published default. The guard must NOT be
# weakened for tests, so the suite supplies its own explicit, non-default secret
# before any app module is imported -- same ordering contract as DATABASE_URL
# above. setdefault() (not assignment) keeps an explicitly exported JWT_SECRET
# winning, and the value is >= 32 bytes so PyJWT stops warning about short HMAC
# keys.
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-not-a-production-key")

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

    ALCANCE DE `CREATE ROLE` (decisión explícita, no implícita): los roles en
    Postgres son de CLUSTER, no de base — `pg_roles` es compartido por todas
    las bases del endpoint. De las tres sentencias de esta función, sólo el
    CREATE ROLE escapa de la base de test: `GRANT USAGE ON SCHEMA public` y
    `REASSIGN OWNED` son database-scoped y sólo tocan la base ya guardada.

    Decisión: SE MANTIENE, también en una base de test remota. El aislamiento
    de branch alcanza: una branch de Neon es un cluster distinto, así que el
    rol no puede caer en la branch de producción. Y donde el endpoint se
    comparte, la sentencia no es destructiva de datos —NOLOGIN, NOSUPERUSER,
    NOBYPASSRLS no otorgan ningún acceso— sólo agrega un nombre al namespace.
    Bloquearlo en remoto rompería `tests/test_rls.py` en el path de Neon que
    el maintainer quiere usar, que sería un peor fallo que un rol inerte. A
    cambio se avisa explícitamente (ver `_warn_cluster_role_scope`), para que
    el costo de namespace sea visible y no una sorpresa.
    """
    import psycopg

    _warn_cluster_role_scope()

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


def _warn_cluster_role_scope() -> None:
    """Avisa que `CREATE ROLE asistcv_rls` escribe en el CLUSTER, no en la base.

    Sólo cuando el destino no es loopback: en local el cluster es un contenedor
    desechable y no hay nada que avisar.
    """
    identity = _db_identity(TEST_DATABASE_URL)
    if identity is None or str(identity["host"]) in _LOOPBACK_HOSTS:
        return
    print(
        "\n"
        + "!" * 78
        + "\n"
        "AVISO / WARNING: la suite va a correr `CREATE ROLE asistcv_rls`.\n"
        f"Destino: {_redact(TEST_DATABASE_URL)}\n"
        "Los roles son de CLUSTER en Postgres: este CREATE toca el namespace de\n"
        "roles del endpoint entero, no solo esta base. Es inocuo (NOLOGIN,\n"
        "NOSUPERUSER, NOBYPASSRLS no otorgan acceso) y en una branch de Neon el\n"
        "cluster ya esta aislado de produccion, pero queda un rol `asistcv_rls`\n"
        f"en el cluster. Si ese endpoint NO es un branch aislado, quitalo a\n"
        f"mano: DROP ROLE {RLS_TEST_ROLE};\n" + "!" * 78,
        file=sys.stderr,
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
        # SEGUNDA puerta, deliberadamente redundante con el check de import.
        # El de import es el autoritativo y frena la sesión entera; este
        # re-evalúa desde el entorno justo antes de la sentencia, así que un
        # test que repuntee TEST_DATABASE_URL en runtime tampoco lo esquiva.
        # Si esta línea se borra, el DROP SCHEMA sigue protegido.
        _assert_test_database_is_disposable()

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
