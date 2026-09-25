"""
Tests for security module (password hashing, JWT handling).

These tests cover:
- bcrypt password hashing and verification
- JWT token creation and decoding
- Refresh token generation
"""
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_access_token,
    hash_password,
    hash_token,
    verify_password,
)


class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_hash_password_creates_hash(self) -> None:
        """hash_password creates a bcrypt hash."""
        password = "TestPassword123"
        hashed = hash_password(password)

        assert hashed is not None
        assert hashed != password
        assert hashed.startswith("$2")  # bcrypt prefix

    def test_verify_password_correct(self) -> None:
        """verify_password returns True for correct password."""
        password = "TestPassword123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """verify_password returns False for incorrect password."""
        password = "TestPassword123"
        wrong_password = "WrongPassword456"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False


class TestJWTTokens:
    """Tests for JWT token functions."""

    def test_create_access_token_creates_valid_token(self) -> None:
        """create_access_token creates a valid JWT."""
        token = create_access_token({"sub": "123", "role": "job_seeker"})

        assert token is not None
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # JWT has 3 parts

    def test_decode_access_token_returns_payload(self) -> None:
        """decode_access_token returns the payload."""
        token = create_access_token({"sub": "123", "role": "job_seeker"})

        payload = decode_access_token(token)

        assert payload["sub"] == "123"
        assert payload["role"] == "job_seeker"
        assert "exp" in payload
        assert "iat" in payload
        assert "jti" in payload

    def test_decode_access_token_requires_sub(self) -> None:
        """decode_access_token requires 'sub' claim."""
        import jwt

        # Create token without sub
        from app.core.config import get_settings
        settings = get_settings()
        token = jwt.encode(
            {"exp": 9999999999, "role": "job_seeker"},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm
        )

        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)


class TestRefreshTokens:
    """Tests for refresh token functions."""

    def test_create_refresh_token_creates_opaque_token(self) -> None:
        """create_refresh_token creates a URL-safe opaque token."""
        token = create_refresh_token()

        assert token is not None
        assert isinstance(token, str)
        assert len(token) >= 32  # 256 bits URL-safe

    def test_hash_token_creates_sha256(self) -> None:
        """hash_token creates SHA256 hash."""
        token = "test-token"
        hashed = hash_token(token)

        assert hashed is not None
        assert isinstance(hashed, str)
        assert len(hashed) == 64  # SHA256 hex length

    def test_hash_token_is_deterministic(self) -> None:
        """hash_token is deterministic."""
        token = "test-token"
        hash1 = hash_token(token)
        hash2 = hash_token(token)

        assert hash1 == hash2


class TestTokenPair:
    """Tests for token pair creation."""

    def test_create_token_pair_returns_both_tokens(self) -> None:
        """create_token_pair returns access and refresh tokens."""
        access, refresh = create_token_pair(user_id=123, role="job_seeker")

        assert access is not None
        assert refresh is not None
        assert isinstance(access, str)
        assert isinstance(refresh, str)
        assert len(access.split(".")) == 3  # JWT
        assert len(refresh) >= 32  # Opaque token

    def test_create_token_pair_contains_correct_user_id(self) -> None:
        """Token pair is created for the correct user."""
        access, _ = create_token_pair(user_id=456, role="recruiter")

        payload = decode_access_token(access)

        assert payload["sub"] == "456"
        assert payload["role"] == "recruiter"
