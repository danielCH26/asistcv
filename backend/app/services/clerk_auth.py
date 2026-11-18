"""
Clerk session-token verification.

Implements ODD slice S1 (backend core) of feat/clerk-auth-migration:
- Parses Clerk publishable keys to derive the Frontend API domain (fsa).
- Fetches Clerk's JWKS and caches it per kid with a 5-minute TTL.
- Verifies RS256 session tokens (issuer, no aud, azp check).
- All failures raise ``ClerkTokenInvalidError``; internal details are logged
  but never leaked to callers.

The module is designed for unit testing without network access: callers can
monkeypatch ``_fetch_jwks`` (the httpx seam) and ``_http_client`` to inject
fake responses. See ``tests/test_clerk_auth.py`` for the pattern.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import PyJWK

from app.core.config import get_settings
from app.core.logging import get_logger

_logger = get_logger("app.services.clerk_auth")

# Module-level JWKS cache: kid -> (PyJWK, fetched_at)
_jwks_cache: dict[str, tuple[PyJWK, float]] = {}
_jwks_cache_lock = asyncio.Lock()

# Cache TTL in seconds (5 minutes)
_JWKS_TTL = 300.0


class ClerkAuthError(Exception):
    """Base exception for Clerk auth failures."""
    pass


class ClerkTokenInvalidError(ClerkAuthError):
    """Token verification failed (expired, bad signature, unknown kid, etc.)."""
    pass


def _parse_publishable_key(key: str) -> str:
    """Derive the Frontend API domain (fsa) from a Clerk publishable key.

    Handles every publishable-key shape observed in the wild:

    * Modern JSON payload (current dashboard format)::

        pk_test_<base64url(JSON with key "fsa")>[[_$]|[$]]

      the trailing "$" (and any "_" right before it) may or may not be
      present depending on where the key was copied from.
    * Legacy payload::

        pk_test_<base64url("<front-api-domain>$")>

      the decoded value is the bare Frontend API domain followed by "$".

    Returns the fsa string, e.g. ``clerk.example.com``. Raises
    ``ClerkTokenInvalidError`` if the key cannot be parsed.
    """
    if not key.startswith("pk_"):
        raise ClerkTokenInvalidError("clerk_publishable_key does not start with pk_")

    # Strip the scheme prefix ("pk_test_" / "pk_live_" = 8 chars) and a
    # literal trailing "_$" or "$" if present. Copy-paste sources keep or
    # drop these inconsistently, so tolerate both.
    inner = key[8:]
    if inner.endswith("_$"):
        inner = inner[:-2]
    elif inner.endswith("$"):
        inner = inner[:-1]
    if not inner:
        raise ClerkTokenInvalidError(
            "clerk_publishable_key does not match expected format pk_..."
        )

    try:
        # Re-add standard base64 padding.
        # n % 4: 1→3, 2→2, 3→1, 0→0. Outer %4 ensures 0 stays 0.
        padding_chars = (4 - len(inner) % 4) % 4
        padded = inner + "=" * padding_chars
        decoded_bytes = base64.urlsafe_b64decode(padded)
    except Exception as exc:  # noqa: BLE001
        raise ClerkTokenInvalidError(
            f"clerk_publishable_key base64 decode failed: {exc}"
        ) from exc

    try:
        decoded_str = decoded_bytes.decode("utf-8")
    except (UnicodeDecodeError, TypeError) as exc:
        raise ClerkTokenInvalidError(
            f"clerk_publishable_key decode/parse failed: {exc}"
        ) from exc

    # Legacy shape: the decoded payload is the bare front-api domain with a
    # trailing "$" separator (e.g. "immense-lamb-7783.clerk.accounts.dev$").
    if not decoded_str.lstrip().startswith("{"):
        legacy_fsa = decoded_str.rstrip("$")
        if "." in legacy_fsa:
            return legacy_fsa
        raise ClerkTokenInvalidError(
            "clerk_publishable_key legacy payload is not a valid domain"
        )

    try:
        payload = json.loads(decoded_str)
        fsa = payload.get("fsa")
        if not fsa:
            raise ClerkTokenInvalidError(
                "clerk_publishable_key JSON payload missing 'fsa' key"
            )
        return fsa
    except json.JSONDecodeError as exc:
        raise ClerkTokenInvalidError(
            f"clerk_publishable_key decode/parse failed: {exc}"
        ) from exc


def _build_jwks_url(publishable_key: str) -> str:
    """Build the JWKS URL from the publishable key's fsa."""
    fsa = _parse_publishable_key(publishable_key)
    return f"https://{fsa}/.well-known/jwks.json"


#: Shared httpx.AsyncClient for JWKS fetches. Tests can patch this.
_http_client: httpx.AsyncClient | None = None


async def _fetch_jwks(jwks_url: str) -> dict[str, Any]:
    """Fetch JWKS JSON from Clerk. Raises ClerkTokenInvalidError on network errors."""
    global _http_client

    # Reuse the shared client when one is installed (tests); otherwise use a
    # short-lived client that is closed right after the fetch.
    try:
        if _http_client is not None:
            response = await _http_client.get(jwks_url)
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(jwks_url)

        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        _logger.warning("clerk_jwks_http_error", url=jwks_url, status=exc.response.status_code)
        raise ClerkTokenInvalidError(f"JWKS fetch returned {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        _logger.warning("clerk_jwks_network_error", url=jwks_url, error=str(exc))
        raise ClerkTokenInvalidError(f"JWKS fetch failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        _logger.warning("clerk_jwks_error", url=jwks_url, error=str(exc))
        raise ClerkTokenInvalidError(f"JWKS fetch failed: {exc}") from exc


async def _get_signing_key(jwks_url: str, kid: str) -> PyJWK:
    """Return a PyJWK for the given kid, using cache + one forced-refetch on miss."""
    now = time.monotonic()
    attempted_refresh = False

    while True:
        # Check cache
        if kid in _jwks_cache:
            key, fetched_at = _jwks_cache[kid]
            if now - fetched_at < _JWKS_TTL:
                return key

        # Fetch JWKS (first time or forced-refresh after a miss)
        jwks = await _fetch_jwks(jwks_url)

        # Populate cache
        async with _jwks_cache_lock:
            for k in jwks.get("keys", []):
                k_id = k.get("kid")
                if not k_id:
                    continue
                try:
                    pjwk = PyJWK.from_dict(k)
                    _jwks_cache[k_id] = (pjwk, now)
                except Exception as exc:  # noqa: BLE001
                    _logger.debug("clerk_jwk_parse_error", kid=k_id, error=str(exc))

        # Try again (unknown kid may now be resolved after refresh)
        if kid in _jwks_cache:
            return _jwks_cache[kid][0]

        if attempted_refresh:
            # Already tried refreshing once → give up
            raise ClerkTokenInvalidError(f"Unknown kid '{kid}' after JWKS refresh")

        attempted_refresh = True
        # Loop back: force-refresh the full JWKS from the server

    # unreachable


def _check_azp(claims: dict[str, Any], allowed_parties: list[str]) -> None:
    """Verify the azp claim is in allowed_parties. Raises if not."""
    azp = claims.get("azp")
    # No azp claim in token → skip check (Clerk tokens may omit it).
    if not azp:
        return
    if not allowed_parties:
        # Empty allowed list = skip azp check
        return
    if azp not in allowed_parties:
        raise ClerkTokenInvalidError(f"azp '{azp}' not in allowed parties {allowed_parties}")


async def verify_clerk_session_token(token: str) -> ClerkClaims:
    """Verify a Clerk session token and return its claims.

    Raises ClerkTokenInvalidError on any verification failure. The token is
    never treated as a legacy token if this call raises.

    Steps:
    1. Extract unverified header (kid, alg).
    2. Fetch / verify JWKS key.
    3. Decode with RS256 (issuer verified, no aud claim).
    4. Check azp against allowed parties.
    5. Return ClerkClaims.
    """
    settings = get_settings()
    publishable_key = settings.clerk_publishable_key

    if not publishable_key:
        raise ClerkTokenInvalidError("Clerk auth is not configured (no publishable key)")

    # Step 1: unverified header — just to get kid and alg
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError as exc:
        _logger.debug("clerk_token_header_parse_error", error=str(exc))
        raise ClerkTokenInvalidError("Token header could not be parsed") from exc

    alg = header.get("alg")
    if alg != "RS256":
        # Not a Clerk-format token; fall through to legacy path.
        raise ClerkTokenInvalidError(
            f"Unexpected algorithm '{alg}' — expected RS256 for Clerk tokens"
        )

    kid = header.get("kid")
    if not kid:
        raise ClerkTokenInvalidError("Token header missing 'kid' claim")

    # Step 2: fetch JWKS key
    jwks_url = _build_jwks_url(publishable_key)
    try:
        signing_key = await _get_signing_key(jwks_url, kid)
    except ClerkTokenInvalidError:
        raise
    except Exception as exc:  # noqa: BLE001
        _logger.warning("clerk_signing_key_error", kid=kid, error=str(exc))
        raise ClerkTokenInvalidError("Could not obtain signing key") from exc

    # Step 3: decode RS256 token
    # Clerk session tokens have no aud claim; issuer is the Frontend API domain.
    #
    # Clerk emits ``iss`` WITHOUT a trailing slash
    # (e.g. "https://immense-lamb-7783.clerk.accounts.dev"), so the issuer
    # must be built exactly that way. A trailing slash made every real
    # session token fail with "Token issuer mismatch" → 401
    # "Invalid credentials" (QA 2026-10, bug in the S1-S4 Clerk commit).
    issuer = f"https://{_parse_publishable_key(publishable_key)}"

    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        _logger.debug("clerk_token_expired")
        raise ClerkTokenInvalidError("Token has expired")
    except jwt.InvalidIssuerError:
        _logger.debug("clerk_token_bad_issuer")
        raise ClerkTokenInvalidError("Token issuer mismatch")
    except jwt.InvalidSignatureError:
        _logger.debug("clerk_token_bad_signature")
        raise ClerkTokenInvalidError("Token signature verification failed")
    except jwt.DecodeError as exc:
        _logger.debug("clerk_token_decode_error", error=str(exc))
        raise ClerkTokenInvalidError("Token payload could not be decoded") from exc
    except jwt.PyJWKClientError as exc:
        _logger.warning("clerk_jwks_client_error", error=str(exc))
        raise ClerkTokenInvalidError("JWKS client error during verification") from exc
    except Exception as exc:  # noqa: BLE001
        _logger.warning("clerk_token_unknown_error", error=str(exc))
        raise ClerkTokenInvalidError("Token verification failed") from exc

    # Step 4: azp check
    allowed_parties = get_clerk_authorized_parties()
    _check_azp(payload, allowed_parties)

    # Step 5: extract claims
    try:
        return ClerkClaims(
            clerk_user_id=payload["sub"],
            # Clerk session tokens carry the session id in ``sid`` (older
            # token versions used ``sess_id``). Informational only.
            session_id=payload.get("sid") or payload.get("sess_id", ""),
            issuer=payload.get("iss", ""),
            issued_at=payload.get("iat", 0),
            expires_at=payload.get("exp", 0),
        )
    except KeyError as exc:
        _logger.warning("clerk_token_missing_claim", claim=str(exc))
        raise ClerkTokenInvalidError(f"Token missing required claim: {exc}") from exc


@dataclass(frozen=True)
class ClerkClaims:
    """Verified claims extracted from a Clerk session token."""
    clerk_user_id: str
    session_id: str
    issuer: str
    issued_at: int
    expires_at: int


def is_clerk_enabled() -> bool:
    """True when Clerk auth is active (publishable key is configured).

    Reads from get_settings() which is cached; callers should call
    get_settings.cache_clear() before changing env vars to ensure fresh reads.
    """
    return bool(get_settings().clerk_publishable_key)


def get_clerk_authorized_parties() -> list[str]:
    """Parse CLERK_AUTHORIZED_PARTIES from settings.

    Empty string / None → fall back to ``frontend_url``.
    Empty resulting list → azp check is skipped.
    """
    settings = get_settings()
    raw = settings.clerk_authorized_parties

    if raw is not None:
        # "" (empty string) → skip azp check entirely.
        if raw.strip() == "":
            return []
        # Strip whitespace around each entry; drop empty segments.
        parties = [p.strip() for p in raw.split(",") if p.strip()]
        if parties:
            return parties

    # None / unset → fall back to frontend_url origin.
    frontend = settings.frontend_url.rstrip("/")
    return [frontend]
