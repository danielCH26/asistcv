"""
API dependencies (auth).

Centralizes authentication with two-path support:
1. Clerk session token (RS256) — active when CLERK_PUBLISHABLE_KEY is set.
   A Clerk-format token is verified end-to-end and never falls through.
2. API key — for MCP adapter / service mode.

When BACKEND_API_KEY is NOT defined (open mode), some endpoints remain accessible
without authentication to allow testing and anonymous usage.
"""
import secrets
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import User
from app.db.session import get_session
from app.services.clerk_auth import (
    ClerkClaims,
    ClerkTokenInvalidError,
    is_clerk_enabled,
    verify_clerk_session_token,
)
from app.services.rls_context import bind_rls_context

_security = APIKeyHeader(name="Authorization", auto_error=False)
_logger = get_logger("app.api.auth")

_BEARER_PREFIX = "bearer"

# Clerk Backend API base URL for user provisioning
_CLERK_API_BASE = "https://api.clerk.com"


def is_auth_required() -> bool:
    """Check if authentication is required based on whether API key is configured.

    In "open mode" (no BACKEND_API_KEY), some endpoints are accessible without auth.
    In "protected mode" (BACKEND_API_KEY defined), all endpoints require auth.
    """
    settings = get_settings()
    return bool(settings.backend_api_key)


@dataclass
class CurrentUser:
    """Represents the authenticated user (Clerk or API key)."""
    id: int
    name: str
    role: str
    auth_method: str  # "clerk" | "api_key" | "open"


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


# ---------------------------------------------------------------------------
# Clerk user provisioning seam (tests patch this to avoid real HTTP calls).
# Returns a dict with the Clerk user fields or raises ClerkTokenInvalidError.
# ---------------------------------------------------------------------------
async def _fetch_clerk_user(clerk_user_id: str) -> dict:
    """Fetch user profile from Clerk Backend API.

    Raises ClerkTokenInvalidError on network errors or if the user is not found.
    """
    settings = get_settings()
    secret_key = settings.clerk_secret_key

    if not secret_key:
        raise ClerkTokenInvalidError("clerk_secret_key not configured")

    url = f"{_CLERK_API_BASE}/v1/users/{clerk_user_id}"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            _logger.warning("clerk_api_user_fetch_error", clerk_user_id=clerk_user_id, error=str(exc))
            raise ClerkTokenInvalidError(f"Clerk API request failed: {exc}") from exc

        if response.status_code == 404:
            raise ClerkTokenInvalidError(f"Clerk user not found: {clerk_user_id}")
        if response.status_code >= 400:
            _logger.warning(
                "clerk_api_user_fetch_http_error",
                clerk_user_id=clerk_user_id,
                status=response.status_code,
            )
            raise ClerkTokenInvalidError(
                f"Clerk API returned {response.status_code}"
            )

        return response.json()


def _map_clerk_user_to_local(clerk_user: dict) -> dict:
    """Map a Clerk user object to local User fields."""
    from datetime import UTC, datetime

    # Primary email address
    email_addresses: list = clerk_user.get("email_addresses", [])
    primary_email_id = clerk_user.get("primary_email_address_id", "")
    email = ""
    email_verified_at = None

    for entry in email_addresses:
        if entry.get("id") == primary_email_id:
            email = (entry.get("email_address") or "").lower()
            # verification.status == "verified" → stamp email_verified_at
            verification = entry.get("verification") or {}
            if verification.get("status") == "verified":
                email_verified_at = datetime.now(UTC)
            break

    if not email:
        # Fallback: first email address on the account (email is required by
        # the Clerk instance config, so this should always resolve).
        if email_addresses:
            email = (email_addresses[0].get("email_address") or "").lower()
        if not email:
            # primary_email_address_id is an opaque id ("idn_..."), never an
            # address — provisioning without a real email would poison the
            # users.email unique column with garbage.
            raise ClerkTokenInvalidError("Clerk user has no email address")

    # Full name
    first_name = clerk_user.get("first_name") or ""
    last_name = clerk_user.get("last_name") or ""
    full_name = f"{first_name} {last_name}".strip()
    if not full_name:
        # Fallback to email local part
        full_name = email.split("@")[0] if "@" in email else "Clerk User"

    # Role from public_metadata
    public_metadata: dict = clerk_user.get("public_metadata") or {}
    role = public_metadata.get("role")
    if role == "recruiter":
        role = "recruiter"
    else:
        role = "job_seeker"

    # Locale
    locale = clerk_user.get("locale") or "es"

    # Avatar
    avatar_url = clerk_user.get("image_url")

    return {
        "email": email,
        "email_verified_at": email_verified_at,
        "full_name": full_name,
        "role": role,
        "locale": locale,
        "avatar_url": avatar_url,
        "password_hash": None,  # Clerk users have no password
    }


async def _provision_clerk_user(claims: ClerkClaims, db: AsyncSession) -> User:
    """Create a local user row from Clerk claims. Raises on failure."""
    clerk_user_id = claims.clerk_user_id

    try:
        clerk_user = await _fetch_clerk_user(clerk_user_id)
    except ClerkTokenInvalidError:
        _logger.warning("clerk_user_provision_failed", clerk_user_id=clerk_user_id)
        raise

    fields = _map_clerk_user_to_local(clerk_user)

    user = User(
        email=fields["email"],
        password_hash=fields["password_hash"],
        role=fields["role"],
        full_name=fields["full_name"],
        locale=fields["locale"],
        avatar_url=fields["avatar_url"],
        email_verified_at=fields["email_verified_at"],
        clerk_id=clerk_user_id,
    )

    db.add(user)

    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        # Concurrent first request: rollback and re-select.
        await db.rollback()
        result = await db.execute(
            select(User).where(User.clerk_id == clerk_user_id)
        )
        winner = result.scalar_one_or_none()
        if winner is None:
            _logger.warning("clerk_user_provision_integrity_error", clerk_user_id=clerk_user_id)
            raise ClerkTokenInvalidError("Failed to provision user (IntegrityError)") from None
        return winner
    except Exception as exc:  # noqa: BLE001
        _logger.warning("clerk_user_provision_error", clerk_user_id=clerk_user_id, error=str(exc))
        await db.rollback()
        raise ClerkTokenInvalidError("Failed to provision user") from exc

    return user


async def _resolve_clerk_user(
    claims: ClerkClaims, db: AsyncSession
) -> CurrentUser:
    """Resolve a Clerk user: lookup by clerk_id, or auto-provision if enabled."""
    settings = get_settings()
    clerk_user_id = claims.clerk_user_id

    # Try to find existing user
    result = await db.execute(
        select(User).where(User.clerk_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()

    if user is not None:
        return CurrentUser(
            id=user.id,
            name=user.full_name or f"user_{user.id}",
            role=user.role,
            auth_method="clerk",
        )

    # Not found locally
    if not settings.clerk_secret_key:
        _logger.warning("clerk_user_not_synced", clerk_user_id=clerk_user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="USER_NOT_SYNCED",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Auto-provision
    try:
        user = await _provision_clerk_user(claims, db)
    except ClerkTokenInvalidError as exc:
        _logger.warning(
            "clerk_user_provision_failed",
            clerk_user_id=clerk_user_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="USER_PROVISION_FAILED",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return CurrentUser(
        id=user.id,
        name=user.full_name or f"user_{user.id}",
        role=user.role,
        auth_method="clerk",
    )


async def get_current_user(
    api_key_header: str | None = Depends(_security),
    db: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Two-path authentication: Clerk → API key.

    When Clerk is enabled and the token has RS256 + kid, the Clerk path is
    attempted first. If verification succeeds, the local user is resolved
    (auto-provisioned if clerk_secret_key is set). A Clerk-format token
    that fails verification raises 401 immediately.

    Returns:
        CurrentUser with clerk data if valid Clerk session provided
        CurrentUser(id=0, role="service") if valid API key provided
        401 if no valid credentials
    """

    token = _extract_bearer(api_key_header)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Clerk path (only for RS256 + kid tokens)
    if is_clerk_enabled():
        try:
            # Sniff: check header before doing async work.
            try:
                header = jwt.get_unverified_header(token)
            except jwt.DecodeError:
                header = None

            if header and header.get("alg") == "RS256" and header.get("kid"):
                claims = await verify_clerk_session_token(token)
                return await _resolve_clerk_user(claims, db)
        except ClerkTokenInvalidError:
            _logger.debug("clerk_token_invalid", reason="verification_failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # 2. API key
    user = _try_api_key(token)
    if user:
        return user

    # None of the paths succeeded
    _logger.warning("auth_failed", has_header=bool(token))
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user_required(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Require an authenticated JWT/Clerk principal, rejecting the API key.

    The service API key resolves to ``CurrentUser(id=0, role="service")``,
    which is the RLS bypass principal. Endpoints that act on behalf of a
    specific account must not accept it, otherwise they would operate on
    user 0 (or fail on a foreign key). Machine-to-machine callers use the
    API key on the endpoints that explicitly want it instead.

    Must be declared after ``get_current_user``: FastAPI resolves the
    dependency expression at import time.
    """
    if current_user.auth_method == "api_key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ROLE_FORBIDDEN",
        )
    return current_user


async def optional_auth(
    api_key_header: str | None = Depends(_security),
    db: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Optional authentication - returns user if valid credentials provided.

    In open mode (no BACKEND_API_KEY), this always returns a service user (no auth required),
    UNLESS a Clerk token is provided (to support Clerk-first migration).
    In protected mode (BACKEND_API_KEY defined), this requires valid credentials:
    - Valid Clerk token → Clerk path (provisioning enabled)
    - Valid API key → returns user
    - No credentials or invalid credentials → raises 401
    """
    # Try Clerk token first if provided — even in open mode, a Clerk token
    # should authenticate the user rather than returning the service principal.
    token = None
    if api_key_header:
        token = _extract_bearer(api_key_header)
        if token and is_clerk_enabled():
            try:
                try:
                    header = jwt.get_unverified_header(token)
                except jwt.DecodeError:
                    header = None

                if header and header.get("alg") == "RS256" and header.get("kid"):
                    claims = await verify_clerk_session_token(token)
                    return await _resolve_clerk_user(claims, db)
            except ClerkTokenInvalidError:
                _logger.debug("clerk_token_invalid_optional", reason="verification_failed")
                # Fall through to API-key / protected-mode checks below.

    # In open mode (no BACKEND_API_KEY), skip auth entirely - return service user.
    # ``auth_method="open"`` (not "api_key") so the audit log in
    # ``_get_profile_or_404`` can distinguish a real API-key read from an
    # inert auto-fabrication when ``BACKEND_API_KEY`` is unset. See #87.
    if not is_auth_required():
        return CurrentUser(
            id=0,
            name="service",
            role="service",
            auth_method="open",
        )

    # In protected mode, require valid credentials
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not token:
        token = _extract_bearer(api_key_header)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # 1. Clerk path (re-check; already handled above for Clerk tokens)
    if is_clerk_enabled():
        try:
            try:
                header = jwt.get_unverified_header(token)
            except jwt.DecodeError:
                header = None

            if header and header.get("alg") == "RS256" and header.get("kid"):
                claims = await verify_clerk_session_token(token)
                return await _resolve_clerk_user(claims, db)
        except ClerkTokenInvalidError:
            _logger.debug("clerk_token_invalid_optional", reason="verification_failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # 2. API key
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


def require_adaptation_enabled() -> bool:
    """Dependency factory returned as a plain bool for endpoint-level gating.

    Wired to ``POST /v1/adaptations`` in PR2 once the adapter endpoint
    ships. While the feature is in development (PR1 only adds the flag)
    the value defaults to ``False`` so a stray endpoint can never leak
    into staging: the dependency returns 503 ``FEATURE_DISABLED`` instead.

    Usage (PR2):
        @router.post("/adaptations", dependencies=[Depends(require_adaptation_enabled)])
    """
    if not get_settings().adaptation_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FEATURE_DISABLED",
        )
    return True


def get_runner():
    """FastAPI dependency returning a process-local ``AdaptationRunner``.

    Lazy-imports ``build_runner`` to avoid pulling the LLM provider at
    module load. Tests override this dependency to inject a runner
    with a mocked LLM provider and the test DB session factory.

    Usage:
        @router.post("/adaptations")
        async def create_adaptation(
            runner: AdaptationRunner = Depends(get_runner),
            ...
        ):
            ...
    """
    from app.services.adaptation_runner import build_runner

    return build_runner()


# Keep the old verify_api_key for backward compatibility with specific routes
async def verify_api_key(
    api_key_header: str | None = Depends(_security),
    db: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Legacy API key verification for routes that need it.

    Prefer get_current_user for new endpoints.

    ``db`` MUST be injected and forwarded: ``get_current_user`` resolves the
    Clerk principal (and auto-provisions the user) through the database
    session. Calling it without a real session left the dependency default
    (a ``Depends`` marker) in place, so any Clerk-authenticated request to
    the ``/v1/users`` router crashed with
    ``AttributeError: 'Depends' object has no attribute 'execute'``
    (QA 2026-10).
    """
    return await get_current_user(api_key_header, db)


# Type alias for dependency injection
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def get_db(
    user: CurrentUser = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession, None]:
    """DB session with the RLS GUC bound to the authenticated principal.

    JWT/Clerk users get their own id (owner policies apply); API-key/service
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
    ``BACKEND_API_KEY`` is configured, so these sessions run under the
    service RLS context in open mode — same rows visible as before RLS.
    """
    async for session in get_session():
        await bind_rls_context(session, user.id, user.role)
        yield session
