"""
Security utilities: password hashing and JWT handling.

Implements:
- bcrypt password hashing (cost 12)
- JWT access/refresh token generation and validation (HS256)
- Refresh token rotation support
"""
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    """Hash a password using bcrypt (cost 12)."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except ValueError:
        return False


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token with jti claim."""
    settings = get_settings()
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(seconds=settings.jwt_access_ttl)

    # Generate unique jti
    jti = secrets.token_urlsafe(16)

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": jti,
    })

    encoded = jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm
    )
    return encoded


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Requires 'exp' and 'sub' claims. Returns the payload if valid.
    Raises jwt.ExpiredSignatureError if expired.
    Raises jwt.InvalidTokenError if invalid.
    """
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]}
    )
    return payload


def create_refresh_token() -> str:
    """Create an opaque refresh token (32 bytes, URL-safe)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a refresh token with SHA256 for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_token_pair(user_id: int, role: str) -> tuple[str, str]:
    """Create access and refresh token pair for a user."""
    settings = get_settings()

    # Access token with user info
    access_token = create_access_token(
        data={"sub": str(user_id), "role": role},
        expires_delta=timedelta(seconds=settings.jwt_access_ttl)
    )

    # Opaque refresh token
    refresh_token = create_refresh_token()

    return access_token, refresh_token
