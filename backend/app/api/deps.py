"""
API dependencies (auth).

Centralizes authentication with dual auth support:
1. JWT first (for user sessions)
2. API key fallback (for MCP adapter / service mode)

The system returns a synthetic "system" user when API key is used.

When BACKEND_API_KEY is NOT defined (open mode), some endpoints remain accessible
without authentication to allow testing and anonymous usage.
"""
import secrets
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.db.session import get_session
from app.services.rls_context import bind_rls_context

_security = APIKeyHeader(name="Authorization", auto_error=False)
_logger = get_logger("app.api.auth")

_BEARER_PREFIX = "bearer"
_JWT_HEURISTIC_PREFIX = "ey"  # JWT tokens start with this in base64


def is_auth_required() -> bool:
    """Check if authentication is required based on whether API key is configured.

    In "open mode" (no BACKEND_API_KEY), some endpoints are accessible without auth.
    In "protected mode" (BACKEND_API_KEY defined), all endpoints require auth.
    """
    settings = get_settings()
    return bool(settings.backend_api_key)


@dataclass
class CurrentUser:
    """Represents the authenticated user (either JWT or API key)."""
    id: int
    name: str
    role: str
    auth_method: str  # "jwt" or "api_key"


def _extract_bearer(header_value: str | None) -> str | None:
    """Extract the token from `Authorization: Bearer <token>`.

    Accepts any casing for the scheme.
    Returns None if header is missing, doesn't have expected scheme, or token is empty.
    """
    if not header_value:
        return None
    parts = header_value.split(" ", 1)
    if len(parts) != 2:
        return None
    scheme = parts[0].strip().lower()
    token = parts[1].strip()
    if scheme != _BEARER_PREFIX or not token:
        return None
    return token


def _try_jwt(token: str) -> CurrentUser | None:
    """Attempt to authenticate with JWT. Returns user if valid, None otherwise."""
    try:
        # Quick heuristic: JWT tokens start with "ey" (base64 encoded header)
        if not token.startswith(_JWT_HEURISTIC_PREFIX):
            return None

        payload = decode_access_token(token)
        user_id = int(payload.get("sub", 0))
        role = payload.get("role", "job_seeker")

        return CurrentUser(
            id=user_id,
            name=f"user_{user_id}",
            role=role,
            auth_method="jwt"
        )
    except jwt.ExpiredSignatureError:
        _logger.debug("jwt_expired")
        return None
    except jwt.InvalidTokenError as e:
        _logger.debug("jwt_invalid", error=str(e))
        return None
    except (ValueError, TypeError):
        return None


def _try_api_key(token: str) -> CurrentUser | None:
    """Attempt to authenticate with API key. Returns synthetic user if valid."""
    settings = get_settings()
    expected = settings.backend_api_key

    if not expected:
        return None

    if secrets.compare_digest(token, expected):
        return CurrentUser(
            id=0,
            name="system",
            role="service",
            auth_method="api_key"
        )
    return None


async def get_current_user(
    api_key_header: str | None = Depends(_security),
) -> CurrentUser:
    """Dual authentication: try JWT first, then API key fallback.

    Returns:
        CurrentUser with JWT data if valid JWT provided
        CurrentUser(id=0, role="service") if valid API key provided
        401 if neither is valid

    This preserves backward compatibility with MCP adapter while adding JWT support.
    """
    token = _extract_bearer(api_key_header)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Try JWT first
    user = _try_jwt(token)
    if user:
        return user

    # Fall back to API key
    user = _try_api_key(token)
    if user:
        return user

    # Neither JWT nor API key is valid
    _logger.warning("auth_failed", has_header=bool(token))
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def optional_auth(
    api_key_header: str | None = Depends(_security),
) -> CurrentUser:
    """Optional authentication - returns user if valid credentials provided.

    In open mode (no BACKEND_API_KEY), this always returns a service user (no auth required).
    In protected mode (BACKEND_API_KEY defined), this requires valid credentials:
    - Valid JWT or API key → returns user
    - No credentials or invalid credentials → raises 401
    """
    # In open mode, skip auth entirely - return service user
    if not is_auth_required():
        return CurrentUser(
            id=0,
            name="service",
            role="service",
            auth_method="api_key"
        )

    # In protected mode, require valid credentials
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = _extract_bearer(api_key_header)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Try JWT first
    user = _try_jwt(token)
    if user:
        return user

    # Fall back to API key
    user = _try_api_key(token)
    if user:
        return user

    # Invalid credentials
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(*allowed_roles: str):
    """Dependency factory that restricts access to specific roles.

    Usage:
        @router.get("/endpoint", dependencies=[Depends(require_role("recruiter"))])
    """
    def role_checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ROLE_FORBIDDEN"
            )
        return current_user
    return role_checker


# Keep the old verify_api_key for backward compatibility with specific routes
async def verify_api_key(
    api_key_header: str | None = Depends(_security),
) -> CurrentUser:
    """Legacy API key verification for routes that need it.

    Prefer get_current_user for new endpoints.
    """
    return await get_current_user(api_key_header)


# Type alias for dependency injection
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_db(
    user: CurrentUser = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession, None]:
    """DB session with the RLS GUC bound to the authenticated principal.

    JWT users get their own id (owner policies apply); API-key/service
    principals get id 0 (service bypass policy). Isolation is enforced
    at the database level by migration 011, in addition to the service
    level ``owner_user_id`` WHERE clauses (defense in depth).
    """
    async for session in get_session():
        await bind_rls_context(session, user.id, user.role)
        yield session


async def get_db_optional(
    user: CurrentUser = Depends(optional_auth),
) -> AsyncGenerator[AsyncSession, None]:
    """Like get_db but tolerant of open-mode anonymous access.

    ``optional_auth`` returns the service user (id 0) when no
    BACKEND_API_KEY is configured, so these sessions run under the
    service RLS context in open mode — same rows visible as before RLS.
    """
    async for session in get_session():
        await bind_rls_context(session, user.id, user.role)
        yield session
