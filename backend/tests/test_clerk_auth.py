"""
Tests for app.services.clerk_auth (ODD slice S1).

Covers:
- is_clerk_enabled() returns correct value based on publishable key.
- _parse_publishable_key derives fsa correctly from pk_test_..._$ format.
- verify_clerk_session_token: valid token → ClerkClaims; expired → raises;
  wrong signature → raises; azp not in allowed parties → raises.
- Unknown kid → one forced refetch, then pass (asserts second fetch).
- Disabled (no publishable key) → is_clerk_enabled() False.

Uses real RSA keypairs (cryptography package) so tokens can be signed
and verified without any external network dependency.
"""
from __future__ import annotations

import json
import time
from base64 import urlsafe_b64encode
from unittest.mock import AsyncMock, patch

import jwt
import pytest

from app.core.config import get_settings
from app.services.clerk_auth import (
    ClerkClaims,
    ClerkTokenInvalidError,
    _build_jwks_url,
    _check_azp,
    _jwks_cache,
    _parse_publishable_key,
    get_clerk_authorized_parties,
    is_clerk_enabled,
    verify_clerk_session_token,
)

# ---------------------------------------------------------------------------
# RSA keypair helpers
# ---------------------------------------------------------------------------
try:
    from cryptography.hazmat.primitives.asymmetric import rsa
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

    def _fake_rsa_keypair():
        return None, None


def generate_rsa_keypair():
    """Generate a 2048-bit RSA keypair. Returns (private_key, public_key_jwk)."""
    if not HAS_CRYPTOGRAPHY:
        raise ImportError("cryptography not installed")
    private = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public = private.public_key()

    # Build JWK components
    public_numbers = public.public_numbers()
    n = public_numbers.n
    e = public_numbers.e

    def _int_to_base64url(value: int) -> str:
        byte_len = (value.bit_length() + 7) // 8
        return urlsafe_b64encode(value.to_bytes(byte_len, "big")).rstrip(b"=").decode("ascii")

    return private, {
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "kid": "test-key-1",
        "n": _int_to_base64url(n),
        "e": _int_to_base64url(e),
    }


def sign_token(private_key, payload: dict, kid: str = "test-key-1", **overrides) -> str:
    """Sign a payload as a Clerk-style session token."""
    payload = dict(payload)
    payload.setdefault("iat", int(time.time()))
    payload.setdefault("exp", int(time.time()) + 3600)
    # Real Clerk session tokens carry the issuer WITHOUT a trailing slash
    # (e.g. "https://immense-lamb-7783.clerk.accounts.dev"). QA 2026-10.
    payload.setdefault("iss", "https://frontend.clerk.dev")
    payload.setdefault("sub", "user_test_123")
    payload.setdefault("sess_id", "sess_test_abc")
    payload.update(overrides)
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def rsa_keys():
    """Session-scoped RSA keypair so all fixtures and tests share the same keypair."""
    private, public_jwk = generate_rsa_keypair()
    return private, public_jwk


@pytest.fixture
def fake_jwks(rsa_keys):
    """Return a JWKS dict with the session-scoped public key."""
    _, public_jwk = rsa_keys
    return {"keys": [public_jwk]}


@pytest.fixture
def clerk_env(monkeypatch):
    """Enable Clerk with a publishable key and clear the settings cache."""
    # Build a pk_test_..._$ key whose fsa = "frontend.clerk.dev"
    # Format: pk_test_<base64url(json) with 'fsa'>_$
    fsa = "frontend.clerk.dev"
    payload_bytes = json.dumps({"fsa": fsa}).encode()
    encoded = urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
    pk = f"pk_test_{encoded}" + chr(95) + chr(36)

    from app.services import clerk_auth
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", pk)
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", f"https://{fsa}")
    get_settings.cache_clear()
    clerk_auth._jwks_cache.clear()  # ensure clean JWKS cache per test
    yield {"pk": pk, "fsa": fsa}
    get_settings.cache_clear()
    clerk_auth._jwks_cache.clear()


@pytest.fixture
def clerk_with_secret_env(clerk_env, monkeypatch):
    """Enable Clerk with both publishable and secret key."""
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_secret_xyz")
    get_settings.cache_clear()
    yield clerk_env
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# is_clerk_enabled
# ---------------------------------------------------------------------------

def test_is_clerk_enabled_true_when_pk_set(clerk_env):
    """Clerk is enabled when CLERK_PUBLISHABLE_KEY is set."""
    assert is_clerk_enabled() is True


def test_is_clerk_enabled_false_when_pk_not_set(monkeypatch):
    """Clerk is disabled when no publishable key is set."""
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY", raising=False)
    get_settings.cache_clear()
    try:
        assert is_clerk_enabled() is False
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# _parse_publishable_key
# ---------------------------------------------------------------------------

def test_parse_publishable_key_valid(clerk_env):
    """_parse_publishable_key returns the fsa from a valid key."""
    fsa = _parse_publishable_key(clerk_env["pk"])
    assert fsa == clerk_env["fsa"]


def test_parse_publishable_key_missing_prefix_raises():
    """Key not starting with pk_ raises ClerkTokenInvalidError."""
    with pytest.raises(ClerkTokenInvalidError):
        _parse_publishable_key("sk_live_something")


def test_parse_publishable_key_non_base64_garbage_raises():
    """Undecodable payload raises ClerkTokenInvalidError (no valid domain/JSON)."""
    with pytest.raises(ClerkTokenInvalidError):
        _parse_publishable_key("pk_test_abcdef")


def test_parse_publishable_key_invalid_base64_raises():
    """Key with un-decodable base64 raises ClerkTokenInvalidError."""
    with pytest.raises(ClerkTokenInvalidError):
        _parse_publishable_key("pk_test_!!!not-base64!!!_$")


@pytest.mark.asyncio
async def test_expected_issuer_has_no_trailing_slash(clerk_env, rsa_keys, fake_jwks):
    """The expected issuer must NOT carry a trailing slash.

    Regression (QA 2026-10): the issuer was built as ``https://{fsa}/`` while
    real Clerk session tokens carry ``https://{fsa}`` (no trailing slash).
    Every Clerk-authenticated request then failed with
    "Token issuer mismatch" -> 401 Invalid credentials in production.
    """
    private, _ = rsa_keys
    token = sign_token(private, {"sub": "user_test_abc"})

    with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = fake_jwks
        _jwks_cache.clear()
        claims = await verify_clerk_session_token(token)

    assert claims.issuer == f"https://{clerk_env['fsa']}"
    assert not claims.issuer.endswith("/")


@pytest.mark.asyncio
async def test_token_with_trailing_slash_issuer_is_rejected(
    clerk_env, rsa_keys, fake_jwks
):
    """A token whose iss has a trailing slash must not be accepted.

    Clerk never emits that form; accepting it would silently widen the
    issuer allow-list beyond the real Frontend API domain.
    """
    private, _ = rsa_keys
    token = sign_token(private, {"sub": "user_test_abc"},
                       iss=f"https://{clerk_env['fsa']}/")

    with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = fake_jwks
        _jwks_cache.clear()
        with pytest.raises(ClerkTokenInvalidError) as exc_info:
            await verify_clerk_session_token(token)

    assert "issuer" in str(exc_info.value).lower()


def test_parse_publishable_key_legacy_domain_format():
    """Legacy keys decode to the bare front-api domain + trailing '$'."""
    # Real-world shape observed in production (2026-10): the dashboard value
    # was pk_test_<b64url('immense-lamb-7783.clerk.accounts.dev$')>.
    payload = "immense-lamb-7783.clerk.accounts.dev$"
    encoded = urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()
    assert _parse_publishable_key(f"pk_test_{encoded}") == (
        "immense-lamb-7783.clerk.accounts.dev"
    )


def test_parse_publishable_key_json_without_trailer():
    """Modern JSON payload without any trailing $/ _$ still parses."""
    payload_bytes = json.dumps({"fsa": "clerk.example.com"}).encode()
    encoded = urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
    assert _parse_publishable_key(f"pk_test_{encoded}") == "clerk.example.com"


def test_parse_publishable_key_json_with_literal_dollar():
    """Modern JSON payload with a literal trailing $ (copy variants) parses."""
    payload_bytes = json.dumps({"fsa": "clerk.example.com"}).encode()
    encoded = urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
    assert _parse_publishable_key(f"pk_test_{encoded}$") == "clerk.example.com"


def test_parse_publishable_key_missing_fsa_raises():
    """Key with valid base64 but no 'fsa' field raises ClerkTokenInvalidError."""
    # Encode a JSON without the 'fsa' key.
    payload_bytes = json.dumps({"iss": "something"}).encode()
    encoded = urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
    key = f"pk_test_{encoded}_" + chr(36)
    with pytest.raises(ClerkTokenInvalidError):
        _parse_publishable_key(key)


# ---------------------------------------------------------------------------
# _build_jwks_url
# ---------------------------------------------------------------------------

def test_build_jwks_url(clerk_env):
    """JWKS URL is constructed as https://{fsa}/.well-known/jwks.json."""
    url = _build_jwks_url(clerk_env["pk"])
    assert url == f"https://{clerk_env['fsa']}/.well-known/jwks.json"


# ---------------------------------------------------------------------------
# get_clerk_authorized_parties
# ---------------------------------------------------------------------------

def test_authorized_parties_falls_back_to_frontend_url(monkeypatch):
    """No CLERK_AUTHORIZED_PARTIES → falls back to frontend_url."""
    monkeypatch.delenv("CLERK_AUTHORIZED_PARTIES", raising=False)
    monkeypatch.setenv("FRONTEND_URL", "https://myapp.com")
    get_settings.cache_clear()
    try:
        parties = get_clerk_authorized_parties()
        assert parties == ["https://myapp.com"]
    finally:
        get_settings.cache_clear()


def test_authorized_parties_from_env(monkeypatch):
    """CLERK_AUTHORIZED_PARTIES is parsed into a list."""
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://a.com, https://b.com")
    get_settings.cache_clear()
    try:
        parties = get_clerk_authorized_parties()
        assert parties == ["https://a.com", "https://b.com"]
    finally:
        get_settings.cache_clear()


def test_authorized_parties_empty_list_skips_azp_check(monkeypatch):
    """Empty CLERK_AUTHORIZED_PARTIES → azp check is skipped."""
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "")
    get_settings.cache_clear()
    try:
        parties = get_clerk_authorized_parties()
        assert parties == []  # empty → skip azp
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# _check_azp
# ---------------------------------------------------------------------------

def test_check_azp_passes_when_azp_in_list():
    """azp in allowed parties → no exception."""
    _check_azp({"azp": "https://myapp.com"}, ["https://myapp.com", "https://other.com"])


def test_check_azp_raises_when_azp_not_in_list():
    """azp NOT in allowed parties → ClerkTokenInvalidError."""
    with pytest.raises(ClerkTokenInvalidError) as exc_info:
        _check_azp({"azp": "https://evil.com"}, ["https://myapp.com"])
    assert "not in allowed parties" in str(exc_info.value)


def test_check_azp_skipped_when_allowed_parties_empty():
    """azp check is skipped when allowed_parties is empty."""
    _check_azp({"azp": "anything"}, [])  # must not raise


def test_check_azp_skipped_when_no_azp_in_token():
    """azp check is skipped when token has no azp claim."""
    _check_azp({}, ["https://myapp.com"])  # must not raise


# ---------------------------------------------------------------------------
# verify_clerk_session_token
# ---------------------------------------------------------------------------

async def test_verify_valid_token_returns_claims(clerk_env, rsa_keys, fake_jwks):
    """A valid RS256 token signed by the JWKS key returns ClerkClaims."""
    private, _ = rsa_keys

    token = sign_token(private, {"sub": "user_test_abc", "sess_id": "sess_xyz"}, kid="test-key-1")

    with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = fake_jwks

        # Clear cache to force fresh fetch
        _jwks_cache.clear()

        claims = await verify_clerk_session_token(token)

    assert isinstance(claims, ClerkClaims)
    assert claims.clerk_user_id == "user_test_abc"
    assert claims.session_id == "sess_xyz"
    assert claims.issuer == "https://frontend.clerk.dev"
    assert claims.expires_at > int(time.time())


async def test_verify_expired_token_raises(clerk_env, rsa_keys, fake_jwks):
    """An expired token raises ClerkTokenInvalidError."""
    private, _ = rsa_keys
    past = int(time.time()) - 3600
    token = sign_token(private, {"sub": "user_test_abc", "iat": past - 3600, "exp": past})

    with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = fake_jwks
        _jwks_cache.clear()

        with pytest.raises(ClerkTokenInvalidError) as exc_info:
            await verify_clerk_session_token(token)
        assert "expired" in str(exc_info.value).lower()


async def test_verify_wrong_signature_raises(clerk_env, rsa_keys, fake_jwks):
    """A token signed with a different key raises ClerkTokenInvalidError."""
    # Generate a second keypair
    other_private, _ = generate_rsa_keypair()
    token = sign_token(other_private, {"sub": "user_test_abc"}, kid="test-key-1")

    with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = fake_jwks
        _jwks_cache.clear()

        with pytest.raises(ClerkTokenInvalidError) as exc_info:
            await verify_clerk_session_token(token)
        assert "signature" in str(exc_info.value).lower()


async def test_verify_azp_not_in_allowed_parties_raises(clerk_env, rsa_keys, fake_jwks, monkeypatch):
    """Token with azp not in CLERK_AUTHORIZED_PARTIES raises."""
    private, _ = rsa_keys

    # Set an explicit allowed parties that does NOT include the token's azp
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://not-my-app.com")
    get_settings.cache_clear()

    token = sign_token(private, {"sub": "user_test_abc", "azp": "https://evil.com"})

    with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = fake_jwks
        _jwks_cache.clear()

        with pytest.raises(ClerkTokenInvalidError) as exc_info:
            await verify_clerk_session_token(token)
        assert "not in allowed parties" in str(exc_info.value)


async def test_verify_unknown_kid_refetch_then_pass(clerk_env, rsa_keys, fake_jwks):
    """Unknown kid triggers one forced refetch; if key appears, verification succeeds."""
    # Session-scoped rsa_keys: all usages share the same keypair.
    signing_private, public_jwk = rsa_keys

    # First JWKS response: missing the kid.
    fake_jwks_missing = {"keys": []}
    # Second JWKS response: has the kid (same public_jwk from session-scoped rsa_keys).
    fake_jwks_found = {"keys": [public_jwk]}
    token = sign_token(signing_private, {"sub": "user_test_abc", "sess_id": "sess_xyz"}, kid="test-key-1")

    call_count = {"n": 0}

    async def _fake_fetch(url):
        call_count["n"] += 1
        return fake_jwks_missing if call_count["n"] == 1 else fake_jwks_found

    with patch("app.services.clerk_auth._fetch_jwks", side_effect=_fake_fetch):
        _jwks_cache.clear()
        from app.services import clerk_auth
        clerk_auth._jwks_cache.clear()
        claims = await verify_clerk_session_token(token)

    assert call_count["n"] == 2, "Should have fetched JWKS twice (miss then hit)"
    assert claims.clerk_user_id == "user_test_abc"


async def test_verify_unknown_kid_remain_unknown_raises(clerk_env, rsa_keys):
    """Unknown kid that never appears in JWKS raises ClerkTokenInvalidError."""
    private, _ = rsa_keys

    token = sign_token(private, {"sub": "user_test_abc"}, kid="unknown-kid")

    with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = {"keys": []}  # kid never appears
        _jwks_cache.clear()

        with pytest.raises(ClerkTokenInvalidError) as exc_info:
            await verify_clerk_session_token(token)
        assert "unknown kid" in str(exc_info.value).lower()


async def test_verify_disabled_no_publishable_key(monkeypatch):
    """When Clerk is disabled, any token raises with clear message."""
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(ClerkTokenInvalidError) as exc_info:
            await verify_clerk_session_token("eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.sig")
        assert "not configured" in str(exc_info.value).lower()
    finally:
        get_settings.cache_clear()


async def test_verify_non_rs256_token_raises(clerk_env, monkeypatch):
    """A token with alg != RS256 raises ClerkTokenInvalidError (not a Clerk token)."""
    # Build a fake token with HS256 header (not Clerk).
    # The clerk auth path sniffs alg and raises for non-RS256.
    # We can test this by patching the alg in the header.
    fake_header = {"alg": "HS256", "kid": "test"}
    fake_token = "eyJhbGciOiJIUzI1NiIsImtpZCI6InRlc3QifQ.eyJzdWIiOiJ1c2VyIn0.fake"

    with patch("jwt.get_unverified_header", return_value=fake_header):
        with pytest.raises(ClerkTokenInvalidError) as exc_info:
            await verify_clerk_session_token(fake_token)
        assert "RS256" in str(exc_info.value)


async def test_verify_bad_header_raises(clerk_env):
    """A token whose header cannot be parsed raises ClerkTokenInvalidError."""
    with patch("jwt.get_unverified_header", side_effect=jwt.DecodeError("bad header")):
        with pytest.raises(ClerkTokenInvalidError) as exc_info:
            await verify_clerk_session_token("not-a-jwt")
        assert "header" in str(exc_info.value).lower()


async def test_verify_missing_sub_claim_raises(clerk_env, rsa_keys, fake_jwks):
    """Token without 'sub' claim raises ClerkTokenInvalidError."""
    private, _ = rsa_keys

    # Create a token with NO sub: bypass sign_token's setdefault("sub", ...).
    token_payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "iss": "https://frontend.clerk.dev",
        # NOTE: no "sub" key
    }
    token = jwt.encode(token_payload, private, algorithm="RS256", headers={"kid": "test-key-1"})

    with patch("app.services.clerk_auth._fetch_jwks", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = fake_jwks
        _jwks_cache.clear()
        with pytest.raises(ClerkTokenInvalidError) as exc_info:
            await verify_clerk_session_token(token)
        assert "sub" in str(exc_info.value).lower() or "required claim" in str(exc_info.value).lower()
