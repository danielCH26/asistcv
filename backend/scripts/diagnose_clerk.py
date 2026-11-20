#!/usr/bin/env python3
"""Diagnóstico del Frontend API de Clerk (y del proxy, si lo hay).

Uso:
    CLERK_PUBLISHABLE_KEY="pk_live_..." uv run python scripts/diagnose_clerk.py

NO cambia nada. Solo reporta si el Frontend API que la app usa realmente
responde, y si el proxy (un Worker que reenvía `/v1/*` y
`/.well-known/jwks.json` a Clerk) está desplegado.

Por qué esto importa: la publishable key ENCODE el dominio del Frontend
API. Con `pk_live_Y2xlcmsuYXNpc3Rjdi1mcm9udGVuZC5wYWdlcy5kZXYk` el
dominio es `clerk.asistcv-frontend.pages.dev`. Si ese host no tiene un
deployment (típico cuando el proxy es un subdominio de un proyecto de Pages
y en realidad falta el Worker), pasa esto:

  · el frontend: `clerk.load()` falla → la pantalla de login muestra el
    cartel "No pudimos cargar el acceso";
  · el backend: el JWKS responde 404 → TODOS los tokens de sesión se
    rechazan, aunque el login llegara a funcionar.

Los dos son la misma causa, y ninguno es "la instancia de desarrollo
llegó al límite de requests".
"""
from __future__ import annotations

import json
import os
import re
import sys
from base64 import urlsafe_b64decode
from urllib.parse import urlparse

import httpx

CLERK_API_VERSION = "2026-08-20"


def decode_fsa(publishable_key: str) -> str:
    """Dominio del Frontend API que la publishable key declara."""
    payload = publishable_key.split("_", 2)[-1]
    payload = payload.strip("$")
    padded = payload + "=" * (-len(payload) % 4)
    decoded = urlsafe_b64decode(padded).decode()

    if decoded.lstrip().startswith("{"):
        data = json.loads(decoded)
        domain = data.get("frontendApi") or data.get("fsa")
        if domain:
            return domain
        raise ValueError("la clave no declara 'frontendApi'")

    # Formato legado: el payload ES el dominio, con un "$" al final.
    return decoded.rstrip("$")


def check(client: httpx.Client, fsa: str, origin: str | None) -> int:
    """Consulta los dos endpoints que la app usa. Devuelve 0 si todo bien."""
    headers = {
        "Accept": "application/json",
        "__clerk_api_version": CLERK_API_VERSION,
        "User-Agent": "eptus-diagnose/1.0",
    }
    if origin:
        headers["Origin"] = origin

    failures = 0
    base = f"https://{fsa}"

    print(f"Frontend API: {base}")
    print(f"Origin:       {origin or '(sin Origin)'}\n")

    # 1. /v1/environment — lo que pide clerk.load()
    r = client.get(f"{base}/v1/environment", headers=headers)
    print(f"GET /v1/environment -> HTTP {r.status_code}")
    if r.status_code == 200 and "client" in r.text:
        print("   OK: la instancia sirvió la configuración del cliente.\n")
    else:
        failures += 1
        print("   FALLA: la instancia no sirvió la configuración del cliente.")
        if "Deployment Not Found" in r.text:
            print(
                "   -> ese host no tiene deployment: falta el proxy de Clerk.\n"
                "      (un subdominio de Pages no puede reenviar /v1/*: hace falta\n"
                "      un Worker, o cambiar la publishable key por la del dominio\n"
                "      nativo de la instancia)."
            )
        else:
            print(f"   -> {r.text[:200]}\n")

    # 2. /.well-known/jwks.json — lo que usa el backend para verificar tokens
    r = client.get(f"{base}/.well-known/jwks.json", headers=headers)
    print(f"GET /.well-known/jwks.json -> HTTP {r.status_code}")
    if r.status_code == 200 and "keys" in r.text:
        print("   OK: el backend puede obtener las llaves de firma.\n")
    else:
        failures += 1
        print("   FALLA: el backend NO puede verificar tokens de sesión.\n")

    return failures


def key_from_deployed_frontend(frontend_url: str) -> str:
    """Lee la publishable key del frontend YA desplegado.

    La app es CSR (ssr=false) y publica sus variables PUBLIC_* en
    `/_app/env.js`. La key es pública por diseño, así que se puede leer
    desde afuera: eso permite vigilar el despliegue sin ningún secreto.
    """
    base = frontend_url.rstrip("/")
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        r = client.get(f"{base}/_app/env.js")
        r.raise_for_status()
        body = r.text

    match = re.search(r'"PUBLIC_CLERK_PUBLISHABLE_KEY"\s*:\s*"([^"]+)"', body)
    if not match:
        raise ValueError(f"PUBLIC_CLERK_PUBLISHABLE_KEY no está en {base}/_app/env.js")
    return match.group(1)


def main() -> int:
    frontend = os.environ.get("DEPLOYED_FRONTEND_URL")
    key = os.environ.get("CLERK_PUBLISHABLE_KEY") or os.environ.get(
        "PUBLIC_CLERK_PUBLISHABLE_KEY"
    )

    if frontend and not key:
        try:
            key = key_from_deployed_frontend(frontend)
        except Exception as exc:
            print(f"No se pudo leer la key del frontend desplegado: {exc}")
            return 2
        print(f"Key tomada del frontend desplegado ({frontend}).\n")

    if not key:
        print(
            "Falta CLERK_PUBLISHABLE_KEY (o PUBLIC_CLERK_PUBLISHABLE_KEY).\n"
            "Para vigilar el despliegue sin secretos: DEPLOYED_FRONTEND_URL=https://…"
        )
        return 2

    try:
        fsa = decode_fsa(key)
    except Exception as exc:
        print(f"No se pudo leer el dominio de la publishable key: {exc}")
        return 2

    origin = os.environ.get("FRONTEND_URL") or frontend
    if origin:
        host = urlparse(origin).hostname or ""
        if host.endswith(".pages.dev"):
            origin = origin.rstrip("/")

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        failures = check(client, fsa, origin)

    if failures:
        print(f"RESULTADO: {failures} endpoint(s) de Clerk no responden.")
        return 1

    print("RESULTADO: Clerk responde en los dos extremos (frontend y backend).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
