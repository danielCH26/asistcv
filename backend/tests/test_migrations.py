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
