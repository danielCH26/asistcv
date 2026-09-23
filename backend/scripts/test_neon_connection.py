"""
Script one-off para verificar la conexión a Neon Postgres.

Checks que realiza:
1. DATABASE_URL definida en el entorno.
2. Conexión con asyncpg y SELECT 1.
3. Extensión `vector` (pgvector) habilitada en la base.

Usage:
    cd backend
    export DATABASE_URL="postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require"
    uv run python scripts/test_neon_connection.py
"""

import asyncio
import os
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _masked_url(database_url: str) -> str:
    """Devuelve la URL con la contraseña enmascarada (para logging seguro)."""
    parts = urlsplit(database_url)
    netloc = parts.netloc
    if "@" in netloc:
        userinfo, host_part = netloc.rsplit("@", 1)
        user = userinfo.split(":", 1)[0]
        netloc = f"{user}:***@{host_part}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _prepare_dsn(database_url: str) -> str:
    """
    Normaliza el DSN para asyncpg.

    Neon solo acepta conexiones TLS: fuerza `sslmode=require` para hosts remotos.
    Para hosts locales (docker-compose) deja el DSN como esté, sin SSL forzado.
    """
    parts = urlsplit(database_url)
    host = parts.hostname or ""
    query_pairs = [
        (key, value) for key, value in parse_qsl(parts.query) if key.lower() != "sslmode"
    ]
    if host not in LOCAL_HOSTS:
        query_pairs.append(("sslmode", "require"))
    parts = parts._replace(query=urlencode(query_pairs))
    return urlunsplit(parts)


async def run_checks(database_url: str) -> bool:
    """Ejecuta los checks contra la base y devuelve True si todos pasan."""
    dsn = _prepare_dsn(database_url)

    try:
        conn = await asyncpg.connect(dsn)
    except Exception as exc:
        print(f"FAIL: no se pudo conectar a la base: {exc!r}")
        return False

    try:
        value = await conn.fetchval("SELECT 1")
        ok_select = value == 1
        print(f"[{'OK' if ok_select else 'FAIL'}] SELECT 1 -> {value}")

        extname = await conn.fetchval(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        )
        ok_vector = extname == "vector"
        print(f"[{'OK' if ok_vector else 'FAIL'}] extensión 'vector' habilitada")

        server_version = await conn.fetchval("SELECT version()")
        print(f"Servidor: {server_version}")
    except Exception as exc:
        print(f"FAIL: error ejecutando los checks: {exc!r}")
        return False
    finally:
        await conn.close()

    if ok_select and not ok_vector:
        print()
        print("HINT: habilitá pgvector con: CREATE EXTENSION IF NOT EXISTS vector;")

    return ok_select and ok_vector


async def main() -> int:
    """Punto de entrada del script."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("FAIL: DATABASE_URL no está definida en el entorno")
        return 1

    print(f"DATABASE_URL: {_masked_url(database_url)}")
    ok = await run_checks(database_url)
    print()
    print(f"RESULT: {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
