"""
API dependencies (auth).

Centraliza la verificación de API key para que pueda inyectarse a nivel de
router vía `dependencies=[Depends(verify_api_key)]`. Modo abierto (sin key) =
pass-through; modo protegido = exige `Authorization: Bearer <key>` con
comparación constant-time.
"""

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings
from app.core.logging import get_logger

_security = APIKeyHeader(name="Authorization", auto_error=False)
_logger = get_logger("app.api.auth")

_BEARER_PREFIX = "bearer"


def _extract_bearer(header_value: str | None) -> str | None:
    """Extrae el API key del header `Authorization: Bearer <key>`.

    Acepta cualquier casing en el prefijo (`Bearer`, `bearer`, `BEARER`).
    Devuelve `None` si el header falta, no tiene el esquema esperado, o el
    token queda vacío.
    """
    if not header_value:
        return None
    parts = header_value.split(" ", 1)
    if len(parts) != 2:
        return None
    scheme = parts[0].strip().lower()
    key = parts[1].strip()
    if scheme != _BEARER_PREFIX or not key:
        return None
    return key


def verify_api_key(
    api_key_header: str | None = Depends(_security),
) -> str:
    """Verifica la API key presente en `Authorization: Bearer <key>`.

    Modo abierto: si `settings.backend_api_key` es None o está vacía, retorna
    sin check (uso dev/CI). Modo protegido: exige header con token que
    coincida vía `secrets.compare_digest`; si falta o no coincide, responde
    401 sin tocar sesión ni proveedores externos.

    Loggea los 401 con metadata (presencia del header, esquema) sin exponer
    el contenido del key.
    """
    settings = get_settings()
    expected = settings.backend_api_key
    if not expected:
        return ""

    presented = _extract_bearer(api_key_header)
    if presented is None or not secrets.compare_digest(presented, expected):
        scheme = ""
        if api_key_header and " " in api_key_header:
            scheme = api_key_header.split(" ", 1)[0].lower()
        _logger.warning(
            "auth_failed",
            has_header=bool(api_key_header),
            scheme=scheme,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return presented
