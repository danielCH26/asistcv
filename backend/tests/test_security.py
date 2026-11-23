"""
Tests for security module (password hashing, JWT handling).

These tests cover:
- bcrypt password hashing and verification
- JWT token creation and decoding
- Refresh token generation
- Fail-closed validation of the JWT signing key
"""
import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_JWT_SECRET, Settings, get_settings
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


class TestJWTSecretFailClosed:
    """The JWT signing key must never resolve to the published default.

    Regression guard for the 2026-09-29 production incident: an access token
    signed with this repo's default secret was accepted by the deployed backend
    and returned a real user's data. The secret itself was rotated; these tests
    pin the structural fix so a future deploy cannot silently fall back again.
    """

    def test_absent_jwt_secret_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings refuses to validate when JWT_SECRET is not set at all."""
        monkeypatch.delenv("JWT_SECRET", raising=False)

        with pytest.raises(ValidationError) as excinfo:
            Settings(_env_file=None)

        message = str(excinfo.value)
        assert "JWT_SECRET" in message
        assert "not acceptable" in message
        assert "secrets.token_urlsafe(48)" in message

    def test_env_provided_default_jwt_secret_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The guard fires on the production path, where JWT_SECRET is set to the default."""
        monkeypatch.setenv("JWT_SECRET", DEFAULT_JWT_SECRET)

        with pytest.raises(ValidationError) as excinfo:
            Settings(_env_file=None)

        assert "JWT_SECRET" in str(excinfo.value)

    def test_explicit_non_default_jwt_secret_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A generated secret is accepted and resolved verbatim."""
        generated = "a-properly-generated-test-secret-value"
        monkeypatch.setenv("JWT_SECRET", generated)

        settings = Settings(_env_file=None)

        assert settings.jwt_secret == generated

    @pytest.mark.parametrize("whitespace", ["   ", "\t", "\n", " \t "])
    def test_whitespace_only_jwt_secret_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, whitespace: str
    ) -> None:
        """A blank secret is as forgeable as the published default.

        An equality test against DEFAULT_JWT_SECRET alone would accept
        "   ": it is not the default string, yet anyone can sign with it.
        This is reachable by copy-pasting a padded value or by a deploy
        whose secret was padded in transit.
        """
        monkeypatch.setenv("JWT_SECRET", whitespace)

        with pytest.raises(ValidationError) as excinfo:
            Settings(_env_file=None)

        assert "JWT_SECRET" in str(excinfo.value)

    def test_suite_runs_with_a_non_default_secret(self) -> None:
        """The suite configures a real secret rather than relaxing the guard."""
        assert get_settings().jwt_secret != DEFAULT_JWT_SECRET

    def test_token_round_trip_with_configured_secret(self) -> None:
        """A token signed with the configured secret decodes back to its claims."""
        token = create_access_token({"sub": "42", "role": "recruiter"})

        payload = decode_access_token(token)

        assert payload["sub"] == "42"
        assert payload["role"] == "recruiter"

    def test_token_signed_with_published_default_is_rejected(self) -> None:
        """The exact forgery from the incident no longer passes decode."""
        import jwt

        settings = get_settings()
        forged = jwt.encode(
            {"sub": "1", "role": "recruiter", "exp": 9999999999},
            DEFAULT_JWT_SECRET,
            algorithm=settings.jwt_algorithm,
        )

        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(forged)


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
