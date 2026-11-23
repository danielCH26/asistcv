"""
Unit tests for the native auth dependencies (JWT + API key, no Clerk).

These cover the two-path contract restored in feat/passwordless-auth:
- ``_extract_bearer`` header parsing (scheme casing, malformed values)
- ``_try_jwt`` happy path and failure modes (expired, forged, non-JWT)
- ``_try_api_key`` constant-time comparison in protected mode
- ``get_current_user`` rejects missing credentials with 401
- ``optional_auth`` open-mode auto-fabrication (``auth_method="open"``)
"""

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from app.api.deps import (
    _extract_bearer,
    _try_api_key,
    _try_jwt,
    get_current_user,
    is_auth_required,
    optional_auth,
)
from app.core.config import get_settings
from app.core.security import create_access_token

# ---------------------------------------------------------------------------
# _extract_bearer
# ---------------------------------------------------------------------------


def test_extract_bearer_accepts_bearer_scheme() -> None:
    assert _extract_bearer("Bearer abc123") == "abc123"


def test_extract_bearer_is_case_insensitive() -> None:
    assert _extract_bearer("bearer abc123") == "abc123"
    assert _extract_bearer("BEARER abc123") == "abc123"


def test_extract_bearer_rejects_other_schemes() -> None:
    assert _extract_bearer("Token abc123") is None


def test_extract_bearer_rejects_missing_or_empty() -> None:
    assert _extract_bearer(None) is None
    assert _extract_bearer("") is None
    assert _extract_bearer("Bearer") is None
    assert _extract_bearer("Bearer ") is None


# ---------------------------------------------------------------------------
# _try_jwt
# ---------------------------------------------------------------------------


def test_try_jwt_valid_token_resolves_principal() -> None:
    token = create_access_token({"sub": "7", "role": "recruiter"})

    user = _try_jwt(token)

    assert user is not None
    assert user.id == 7
    assert user.role == "recruiter"
    assert user.auth_method == "jwt"


def test_try_jwt_expired_token_returns_none() -> None:
    from datetime import timedelta

    token = create_access_token(
        {"sub": "7", "role": "recruiter"},
        expires_delta=timedelta(seconds=-1),
    )

    assert _try_jwt(token) is None


def test_try_jwt_forged_token_returns_none() -> None:
    settings = get_settings()
    forged = pyjwt.encode(
        {"sub": "1", "role": "recruiter", "exp": 9999999999},
        "wrong-secret-never-used-in-prod",
        algorithm=settings.jwt_algorithm,
    )

    assert _try_jwt(forged) is None


def test_try_jwt_non_jwt_string_returns_none() -> None:
    # API keys and opaque tokens do not start with the JWT heuristic prefix.
    assert _try_jwt("sk-some-api-key-value") is None


# ---------------------------------------------------------------------------
# _try_api_key / is_auth_required
# ---------------------------------------------------------------------------


def test_try_api_key_disabled_when_no_backend_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "backend_api_key", None, raising=False)

    assert _try_api_key("anything") is None
    assert is_auth_required() is False


def test_try_api_key_valid_key_resolves_service_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "backend_api_key", "test-service-key", raising=False)

    user = _try_api_key("test-service-key")

    assert user is not None
    assert user.id == 0
    assert user.role == "service"
    assert user.auth_method == "api_key"


def test_try_api_key_wrong_key_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "backend_api_key", "test-service-key", raising=False)

    assert _try_api_key("wrong-key") is None


# ---------------------------------------------------------------------------
# get_current_user / optional_auth
# ---------------------------------------------------------------------------


async def test_get_current_user_requires_credentials() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(api_key_header=None)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid credentials"


async def test_get_current_user_accepts_valid_jwt() -> None:
    token = create_access_token({"sub": "9", "role": "job_seeker"})

    user = await get_current_user(api_key_header=f"Bearer {token}")

    assert user.id == 9
    assert user.auth_method == "jwt"


async def test_optional_auth_open_mode_fabricates_service_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "backend_api_key", None, raising=False)

    user = await optional_auth(api_key_header=None)

    assert user.id == 0
    assert user.role == "service"
    assert user.auth_method == "open"


async def test_optional_auth_protected_mode_rejects_anonymous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "backend_api_key", "test-service-key", raising=False)

    with pytest.raises(HTTPException) as excinfo:
        await optional_auth(api_key_header=None)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid or missing API key"


async def test_optional_auth_protected_mode_accepts_jwt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "backend_api_key", "test-service-key", raising=False)
    token = create_access_token({"sub": "11", "role": "job_seeker"})

    user = await optional_auth(api_key_header=f"Bearer {token}")

    assert user.id == 11
    assert user.auth_method == "jwt"
