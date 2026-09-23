"""
Alembic environment configuration for AsistCV migrations.

Supports both online (connected to DB) and offline (generates SQL) modes.
"""
import os
import urllib.parse as _urlparse
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel

from alembic import context

# Import SQLModel and all models to register them with the metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Get database URL from environment variable
database_url = os.environ.get("DATABASE_URL", "postgresql://asistcv:asistcv@localhost:5433/asistcv")

# Normalize: ensure async driver for the async engine (same logic as app/db/session.py)
if database_url.startswith("postgresql://") and "+psycopg" not in database_url and "+asyncpg" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif database_url.startswith("postgresql+psycopg://"):
    database_url = database_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)

# asyncpg does not accept libpq-only parameters (`sslmode`, `channel_binding`,
# etc.). Managed providers like Neon include them in their connection strings.
# Strip everything from the query string except parameters asyncpg understands.
_parsed = _urlparse.urlparse(database_url)
_query = _urlparse.parse_qs(_parsed.query)
_ASYNCPG_KNOWN_PARAMS = {"service", "ssl", "timeout", "command_timeout", "application_name", "server_settings"}
if _query and not set(_query.keys()).issubset(_ASYNCPG_KNOWN_PARAMS):
    database_url = _urlparse.urlunparse(_parsed._replace(query=""))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with a connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    # asyncpg needs `ssl=true` for managed providers (Neon, RDS, etc.).
    # Local connections (localhost/127.0.0.1) don't need TLS.
    is_local = "localhost" in database_url or "127.0.0.1" in database_url
    connect_args = {} if is_local else {"ssl": True}

    # Create async engine directly with the database URL
    connectable: AsyncEngine = create_async_engine(
        database_url,
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    import asyncio
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
