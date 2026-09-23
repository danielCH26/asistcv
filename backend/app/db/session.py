"""
Database session management using SQLAlchemy async with SQLModel.
"""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from app.core.config import get_settings

# Module-level engine cache
_engine = None
_session_factory = None


def get_engine():
    """Get or create the async SQLAlchemy engine with caching."""
    global _engine
    if _engine is None:
        settings = get_settings()
        database_url = settings.database_url

        if not database_url:
            database_url = "postgresql://asistcv:asistcv@localhost:5433/asistcv"

        # Normalize: ensure async driver for the async engine.
        # If URL is postgresql:// or postgresql+psycopg://, convert to postgresql+asyncpg://.
        # If URL is already postgresql+asyncpg://, leave as is.
        if database_url.startswith("postgresql://") and "+psycopg" not in database_url and "+asyncpg" not in database_url:
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif database_url.startswith("postgresql+psycopg://"):
            database_url = database_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)

        # asyncpg does not accept libpq-only parameters (`sslmode`,
        # `channel_binding`, etc.). Managed providers like Neon include them
        # in their connection strings. Strip the whole query string unless
        # every parameter is one asyncpg understands.
        import urllib.parse as _urlparse

        _parsed = _urlparse.urlparse(database_url)
        _query = _urlparse.parse_qs(_parsed.query)
        asyncpg_known_params = {"service", "ssl", "timeout", "command_timeout", "application_name", "server_settings"}
        if _query and not set(_query.keys()).issubset(asyncpg_known_params):
            database_url = _urlparse.urlunparse(_parsed._replace(query=""))

        # asyncpg needs `ssl=true` for remote managed providers; local doesn't.
        is_local = "localhost" in database_url or "127.0.0.1" in database_url
        connect_args = {} if is_local else {"ssl": True}

        _engine = create_async_engine(
            database_url,
            echo=False,
            poolclass=NullPool,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory():
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session.
    Use this as: async for session in get_session(): ...
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session


@asynccontextmanager
async def get_session_context():
    """Context manager for getting a session outside of FastAPI dependency injection."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db():
    """Initialize database tables (for development only)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def close_db():
    """Close database connections (for graceful shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None
