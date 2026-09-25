#!/usr/bin/env python3
"""Diagnóstico de conexión a Neon para `alembic upgrade head`.

Uso:
    DATABASE_URL="postgres://ep-...neon.tech/asistcv?sslmode=require" \\
        uv run python scripts/diagnose_neon.py

NO migra nada. Solo reporta: parseo de URL, normalización para alembic,
y la salida cruda de `alembic current` contra esa URL exacta.

Si pegás el output en el chat, te digo qué línea mirar.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def mask(u: str) -> str:
    """Oculta el password antes de imprimir: postgres://user:***@host/db"""
    try:
        p = urlparse(u)
        netloc = f"{p.username}:***@{p.hostname}" if p.username else p.hostname
        if p.port:
            netloc += f":{p.port}"
        return f"{p.scheme}://{netloc}{p.path}"
    except Exception:
        return u[:60] + "..."


def normalize_for_alembic(u: str) -> str:
    """Alembic usa SQLAlchemy sync; normaliza variantes async."""
    out = u
    for variant in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql+psycopg2://"):
        if out.startswith(variant):
            out = out.replace(variant, "postgresql://", 1)
            break
    if out.startswith("postgres://"):
        out = out.replace("postgres://", "postgresql://", 1)
    return out


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("✗ DATABASE_URL no está seteada en el entorno.")
        print("  Pegame la URL como export antes de correr:")
        print("    export DATABASE_URL='postgres://ep-...neon.tech/asistcv?sslmode=require'")
        return 1

    print(f"URL provista:        {mask(url)}")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    dbname = parsed.path.lstrip("/") or "(vacío)"
    user = parsed.username or "(vacío)"

    print(f"Hostname:            {host}")
    print(f"DB name:             {dbname}")
    print(f"User:                {user}")
    print(f"Es Neon:             {'Sí' if 'neon' in host else 'NO — no parece Neon'}")
    print(f"Es localhost:        {'Sí (ESTO ES LOCAL, no Neon)' if host in ('localhost', '127.0.0.1') else 'No'}")
    print(f"Tiene sslmode:       {'Sí' if 'sslmode' in (parsed.query or '') else 'No (Neon lo requiere)'}")
    print(f"Driver explícito:    {'Sí (' + parsed.scheme + ')' if '+' in parsed.scheme else 'No (default)'}")

    sync_url = normalize_for_alembic(url)
    print(f"\nVersión sync (alembic): {mask(sync_url)}")

    if host in ("localhost", "127.0.0.1", ""):
        print(
            "\n⚠ El hostname es localhost/127.0.0.1 — esta URL apunta a tu DB local,"
            "\n  no a Neon. La migración que corrió antes fue contra el Postgres local."
            "\n  Pegame la URL de Render Dashboard → Environment → DATABASE_URL."
        )
        return 2

    if "neon" not in host:
        print(
            f"\n⚠ El hostname '{host}' no contiene 'neon'. Verificá que copiaste la URL"
            "\n  correcta del dashboard de Render. Neon siempre tiene 'neon.tech' en el host."
        )
        return 2

    # Run `alembic current` against the sync URL
    env = os.environ.copy()
    env["DATABASE_URL"] = sync_url
    backend_dir = str(Path(__file__).resolve().parent.parent)
    print("\n--- Corriendo `alembic current` contra esa URL ---")
    try:
        r = subprocess.run(
            ["uv", "run", "alembic", "current", "--verbose"],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("✗ Timeout (>60s) — Neon no responde. ¿Firewall?")
        return 4

    print("STDOUT:", r.stdout or "(vacío)")
    print("STDERR:", r.stderr or "(vacío)")
    print(f"Exit code: {r.returncode}")

    if r.returncode == 0:
        if r.stdout.strip():
            print("\n→ Neon ESTÁ migrado. Si ves una línea con `012` (head), todo OK.")
            print("  Si dice `001`, `002`, etc., no se aplicó lo de Sprint 2.")
        else:
            print("\n→ Conectó pero `alembic_version` está VACÍO — la BD nunca tuvo migraciones.")
        return 0

    print("\n--- Diagnóstico heurístico del error ---")
    err = (r.stderr or "").lower() + (r.stdout or "").lower()
    if "could not translate host" in err or "name or service not known" in err or "temporary failure in name resolution" in err:
        print("→ DNS: el hostname no resuelve. URL mal copiada.")
    elif "connection refused" in err or "could not connect" in err:
        print("→ Red/port: Neon no acepta conexiones desde esta máquina (firewall/region).")
    elif "authentication failed" in err or "password authentication" in err:
        print("→ Auth: usuario/contraseña incorrectos. Verificá Render → DATABASE_URL.")
    elif "ssl" in err and "sslmode" in err:
        print("→ SSL: agregá `?sslmode=require` a la URL.")
    elif "database" in err and "does not exist" in err:
        print("→ DB name mal en la URL. Confirmá el último segmento del path.")
    elif "permission denied" in err:
        print("→ Permisos: el role de Neon no tiene CREATE. Usá el connection string principal.")
    elif "connection timed out" in err:
        print("→ Timeout de red. Verificá que Neon no esté pausado (serverless suspend).")
    else:
        print("→ Error no reconocido. PEGAME EL OUTPUT COMPLETO (stdout + stderr arriba).")
    return 3


if __name__ == "__main__":
    sys.exit(main())
