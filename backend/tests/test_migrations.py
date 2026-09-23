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


# --- Tests de la migración 002 (vectores + HNSW + FK profile_id) ---


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
    assert len(hnsw_indexes) == 3, "3 HNSW indexes should exist after re-upgrade"
