"""
Test migrations can be applied and reverted.

Uses a test database to verify alembic migrations work correctly.
"""
import os

import pytest
from sqlalchemy import text

# Test database URL - uses a separate database for testing.
# Fallback chain: TEST_DATABASE_URL -> DATABASE_URL (set in CI) -> local default (5433).
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://asistcv:asistcv@localhost:5433/asistcv_test",
)


def _to_async_driver_url(url: str) -> str:
    """Return url with an async driver (asyncpg) for SQLAlchemy async engines."""
    scheme, _, rest = url.partition("://")
    if "+" not in scheme:
        return f"{scheme}+asyncpg://{rest}"
    return url


@pytest.fixture(scope="module")
def setup_test_db():
    """Set up test database and run migrations."""
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    # Set the DATABASE_URL environment variable for alembic
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

    # Run migrations using alembic command
    from alembic.config import Config

    from alembic import command

    alembic_cfg = Config("alembic.ini")

    # Apply migrations
    command.upgrade(alembic_cfg, "head")

    # Create test engine
    engine = create_async_engine(
        _to_async_driver_url(TEST_DATABASE_URL),
        poolclass=NullPool,
        echo=False,
    )

    yield engine

    # After tests, revert migrations
    command.downgrade(alembic_cfg, "base")

    # Restore original DATABASE_URL
    if original_db_url:
        os.environ["DATABASE_URL"] = original_db_url
    elif "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]

    asyncio.run(engine.dispose())


@pytest.mark.asyncio
async def test_migrations_create_tables(setup_test_db):
    """Verify tables are created after migration."""
    engine = setup_test_db

    async with engine.connect() as conn:
        # Check tables exist
        result = await conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('profiles', 'job_descriptions', 'analyses')
        """))
        tables = {row[0] for row in result.fetchall()}

        assert "profiles" in tables, "profiles table should exist"
        assert "job_descriptions" in tables, "job_descriptions table should exist"
        assert "analyses" in tables, "analyses table should exist"


@pytest.mark.asyncio
async def test_migrations_foreign_keys(setup_test_db):
    """Verify foreign key constraints are created."""
    engine = setup_test_db

    async with engine.connect() as conn:
        # Check foreign key exists
        result = await conn.execute(text("""
            SELECT
                tc.constraint_name,
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_name = 'analyses'
        """))

        fks = result.fetchall()
        assert len(fks) > 0, "analyses should have foreign key constraints"

        # Check the specific foreign key to job_descriptions
        fk_columns = [f[2] for f in fks]
        assert "job_description_id" in fk_columns


@pytest.mark.asyncio
async def test_migrations_vector_extension(setup_test_db):
    """Verify vector extension is enabled."""
    engine = setup_test_db

    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT extname FROM pg_extension WHERE extname = 'vector'
        """))

        extension = result.scalar()
        assert extension == "vector", "vector extension should be enabled"


def test_alembic_config_exists():
    """Verify alembic.ini exists and is valid."""
    import os

    from alembic.config import Config

    assert os.path.exists("alembic.ini"), "alembic.ini should exist"

    # Verify it's a valid alembic config
    cfg = Config("alembic.ini")
    assert cfg.get_main_option("script_location") == "alembic"


def test_models_registered_with_metadata():
    """Verify all models are registered with SQLModel metadata."""
    from sqlmodel import SQLModel

    # Get all tables from metadata
    tables = SQLModel.metadata.tables

    assert "profiles" in tables, "Profile table should be registered"
    assert "job_descriptions" in tables, "JobDescription table should be registered"
    assert "analyses" in tables, "Analysis table should be registered"


# --- Migration ordering test for Sprint 3 Slice A (PR1: 014-017) ---


@pytest.mark.asyncio
async def test_slice_a_migrations_chain_ordering(setup_test_db):
    """Slice A migrations 014-017 apply and revert in order.

    Asserts the SPRINT-3 chain:

    * 014 — users_cvs.content_version
    * 015 — cv_adaptations table + indexes + partial UNIQUE
    * 016 — cv_adaptations RLS policies
    * 017 — usage_counters.adaptations_used

    Reusable behavior pattern: alembic upgrade head reaches the new head
    (017), and alembic downgrade -1 (×4) walks back through 017 -> 016
    -> 015 -> 014 with the corresponding columns and indexes disappearing
    at each step.
    """
    import asyncio

    from alembic.config import Config

    from alembic import command

    alembic_cfg = Config("alembic.ini")
    engine = setup_test_db

    async def _column_exists(conn, table: str, column: str) -> bool:
        result = await conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :t
                  AND column_name = :c
                """
            ),
            {"t": table, "c": column},
        )
        return result.fetchone() is not None

    async def _table_exists(conn, table: str) -> bool:
        result = await conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :t
                """
            ),
            {"t": table},
        )
        return result.fetchone() is not None

    async def _index_exists(conn, index: str) -> bool:
        result = await conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE schemaname='public' AND indexname=:i"
            ),
            {"i": index},
        )
        return result.fetchone() is not None

    # --- upgrade head (014-017 already applied in the module fixture) ---
    # The module fixture calls command.upgrade(..., "head"); confirm
    # both new columns, the new table and the partial UNIQUE are
    # present post-upgrade.
    async with engine.connect() as conn:
        assert await _column_exists(conn, "users_cvs", "content_version")
        assert await _column_exists(conn, "usage_counters", "adaptations_used")
        assert await _table_exists(conn, "cv_adaptations")
        # PR1 partial UNIQUE index on completed adaptations.
        assert await _index_exists(conn, "uq_cv_adapt_parent_jd_hash_completed")

    # --- downgrade 017: drops adaptations_used ---
    await asyncio.to_thread(command.downgrade, alembic_cfg, "016_rls_cv_adaptations")
    async with engine.connect() as conn:
        assert not await _column_exists(
            conn, "usage_counters", "adaptations_used"
        ), "017 downgrade should drop adaptations_used"

    # --- downgrade 016: drops RLS policies + DISABLE/FORCE ---
    await asyncio.to_thread(command.downgrade, alembic_cfg, "015_cv_adaptations")
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT count(*) FROM pg_policies "
                "WHERE schemaname='public' AND tablename='cv_adaptations'"
            )
        )
        row = result.fetchone()
        assert row is not None and row[0] == 0, (
            f"016 downgrade should drop all cv_adaptations policies, got {row[0]}"
        )

    # --- downgrade 015: drops cv_adaptations table + indexes ---
    await asyncio.to_thread(command.downgrade, alembic_cfg, "014_users_cvs_content_version")
    async with engine.connect() as conn:
        assert not await _table_exists(
            conn, "cv_adaptations"
        ), "015 downgrade should drop cv_adaptations"
        # content_version (migration 014) must still be in place after 015
        # downgrade — the chain is 017 -> 014, not "everything from 014".
        assert await _column_exists(
            conn, "users_cvs", "content_version"
        ), "015 downgrade should NOT drop content_version (still at 014)"

    # --- downgrade 014: drops content_version ---
    await asyncio.to_thread(command.downgrade, alembic_cfg, "013_tz_aware_timestamps")
    async with engine.connect() as conn:
        assert not await _column_exists(
            conn, "users_cvs", "content_version"
        ), "014 downgrade should drop content_version"

    # Re-apply to leave the module fixture in the same state it started in.
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")


@pytest.mark.asyncio
async def test_migration_019_renames_jd_text_column(setup_test_db):
    """019 renombra ``jd_text_encrypted`` -> ``jd_text`` y es reversible.

    La columna se llamaba ``encrypted`` pero guardaba UTF-8 crudo: el
    nombre afirmaba una protección que no existía. Este test congela las
    dos mitas del contrato:

    * upgrade: existe ``jd_text`` (BYTEA), NO existe ``jd_text_encrypted``;
    * downgrade: se restaura el nombre viejo y desaparece el nuevo.

    No se edita la 015 (historia ya aplicada); sólo se verifica el estado
    final del schema.
    """
    import asyncio

    from alembic.config import Config

    from alembic import command

    alembic_cfg = Config("alembic.ini")
    engine = setup_test_db

    async def _column(conn, name: str):
        result = await conn.execute(
            text(
                """
                SELECT data_type FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'cv_adaptations'
                  AND column_name = :c
                """
            ),
            {"c": name},
        )
        row = result.fetchone()
        return None if row is None else row[0]

    # --- upgrade head (019 applied by the module fixture) ---
    async with engine.connect() as conn:
        assert await _column(conn, "jd_text") == "bytea", (
            "019 should leave a BYTEA column named jd_text"
        )
        assert await _column(conn, "jd_text_encrypted") is None, (
            "019 should remove the jd_text_encrypted name"
        )
        # The neighbouring columns must be untouched by the rename.
        assert await _column(conn, "jd_text_hash") == "character varying"

    # --- downgrade to 018: the old name comes back ---
    await asyncio.to_thread(
        command.downgrade, alembic_cfg, "018_audit_claim_policy"
    )
    async with engine.connect() as conn:
        assert await _column(conn, "jd_text_encrypted") == "bytea", (
            "019 downgrade should restore jd_text_encrypted as BYTEA"
        )
        assert await _column(conn, "jd_text") is None, (
            "019 downgrade should remove the jd_text name"
        )

    # --- re-apply: idempotent, leaves the fixture at head ---
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    async with engine.connect() as conn:
        assert await _column(conn, "jd_text") == "bytea"


async def _fetch_vector_columns(engine) -> dict[str, set[str]]:
    """Devuelve {tabla: {columnas de embedding/modelo presentes}} post-migración."""
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name IN ('profiles', 'job_descriptions', 'analyses')
            AND column_name IN ('embedding', 'embedding_model')
        """))
        columns: dict[str, set[str]] = {}
        for table_name, column_name in result.fetchall():
            columns.setdefault(table_name, set()).add(column_name)
    return columns


async def _fetch_hnsw_indexes(engine) -> set[str]:
    """Devuelve los nombres de índices HNSW presentes en el DB."""
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT i.relname
            FROM pg_index ix
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_class t ON t.oid = ix.indrelid
            JOIN pg_am am ON am.oid = i.relam
            WHERE am.amname = 'hnsw'
        """))
        return {row[0] for row in result.fetchall()}


@pytest.mark.asyncio
async def test_migration_002_vector_columns(setup_test_db):
    """002 agrega embedding vector(1024) y embedding_model varchar(100) en 3 tablas."""
    engine = setup_test_db

    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT table_name, column_name, udt_name,
                   character_maximum_length, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name IN ('profiles', 'job_descriptions', 'analyses')
            AND column_name IN ('embedding', 'embedding_model')
        """))
        rows = result.fetchall()

    found = {(r[0], r[1]): (r[2], r[3], r[4]) for r in rows}
    for table in ("job_descriptions", "analyses", "profiles"):
        embedding = found.get((table, "embedding"))
        assert embedding is not None, f"{table}.embedding should exist"
        assert embedding[0] == "vector", f"{table}.embedding should be a vector column"
        assert embedding[2] == "YES", f"{table}.embedding should be nullable"

        model = found.get((table, "embedding_model"))
        assert model is not None, f"{table}.embedding_model should exist"
        assert model[0] == "varchar", (
            f"{table}.embedding_model should be varchar"
        )
        assert model[1] == 100, f"{table}.embedding_model should be varchar(100)"
        assert model[2] == "YES", f"{table}.embedding_model should be nullable"


@pytest.mark.asyncio
async def test_migration_002_hnsw_indexes(setup_test_db):
    """002 crea los 3 índices HNSW con operator class vector_cosine_ops."""
    engine = setup_test_db

    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT i.relname AS index_name, t.relname AS table_name,
                   opc.opcname AS opclass
            FROM pg_index ix
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_class t ON t.oid = ix.indrelid
            JOIN pg_am am ON am.oid = i.relam
            JOIN pg_opclass opc ON opc.oid = ix.indclass[0]
            WHERE am.amname = 'hnsw'
        """))
        rows = result.fetchall()

    indexes = {r[0]: (r[1], r[2]) for r in rows}
    expected = {
        "idx_jd_embedding_hnsw": "job_descriptions",
        "idx_analyses_embedding_hnsw": "analyses",
        "idx_profiles_embedding_hnsw": "profiles",
    }
    for index_name, table_name in expected.items():
        assert index_name in indexes, f"HNSW index {index_name} should exist"
        assert indexes[index_name][0] == table_name
        assert indexes[index_name][1] == "vector_cosine_ops", (
            f"{index_name} should use vector_cosine_ops"
        )


@pytest.mark.asyncio
async def test_migration_002_profile_foreign_key(setup_test_db):
    """002 agrega la FK faltante analyses.profile_id -> profiles.id."""
    engine = setup_test_db

    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT kcu.column_name, ccu.table_name AS foreign_table,
                   ccu.column_name AS foreign_column
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_name = 'analyses'
                AND kcu.column_name = 'profile_id'
        """))
        fk = result.fetchone()

    assert fk is not None, "analyses.profile_id should have a foreign key"
    assert fk[1] == "profiles", "FK should reference profiles"
    assert fk[2] == "id", "FK should reference profiles.id"


@pytest.mark.asyncio
async def test_migration_002_downgrade_upgrade_reversible(setup_test_db):
    """002 es reversible: down a 001 elimina columnas/índices/FK; up los restaura."""
    engine = setup_test_db

    import asyncio

    from alembic.config import Config

    from alembic import command

    alembic_cfg = Config("alembic.ini")

    # Downgrade: 002 -> 001 (en thread worker: alembic usa asyncio.run interno)
    await asyncio.to_thread(command.downgrade, alembic_cfg, "001_initial_tables")

    columns = await _fetch_vector_columns(engine)
    assert columns == {}, "vector columns should be dropped after downgrade"

    hnsw_indexes = await _fetch_hnsw_indexes(engine)
    assert hnsw_indexes == set(), "HNSW indexes should be dropped after downgrade"

    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'analyses'
            AND column_name = 'profile_id'
        """))
        assert result.fetchone() is None, "profile_id should be dropped"

    # Upgrade: 001 -> 002 (re-aplicación idempotente)
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    columns = await _fetch_vector_columns(engine)
    for table in ("job_descriptions", "analyses", "profiles"):
        assert columns.get(table) == {"embedding", "embedding_model"}, (
            f"{table} should have embedding columns again after re-upgrade"
        )

    hnsw_indexes = await _fetch_hnsw_indexes(engine)
    # Migration 002 creates 3 (profiles, job_descriptions, analyses), migration 004 adds 1 (users_cvs)
    assert len(hnsw_indexes) == 4, f"4 HNSW indexes should exist after re-upgrade, got {hnsw_indexes}"
