"""
Audit token generation and validation.

Generates secure tokens for anonymous audit uploads that are:
- Unique (UUID v4)
- Verifiable (SHA256 hash stored, original token never persisted)
- Time-limited (expires in 30 days)
"""
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

# Token validity period (30 days as per spec)
AUDIT_TOKEN_VALIDITY_DAYS = 30


def generate_audit_token() -> tuple[str, str]:
    """
    Generate a new audit token and its hash.

    Returns:
        Tuple of (plain_token, token_hash) where:
        - plain_token: The token to give to the user (UUID string)
        - token_hash: The SHA256 hash to store in the database
    """
    plain_token = str(uuid.uuid4())
    token_hash = hashlib.sha256(plain_token.encode()).hexdigest()
    return plain_token, token_hash


def compute_token_hash(token: str) -> str:
    """Compute SHA256 hash of a token."""
    return hashlib.sha256(token.encode()).hexdigest()


def calculate_expiry(created_at: datetime | None = None) -> datetime:
    """
    Calculate the expiry timestamp for an audit token.

    Args:
        created_at: When the audit was created. Defaults to now().

    Returns:
        datetime with timezone indicating when the audit expires.
    """
    if created_at is None:
        created_at = datetime.now(UTC)
    elif created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    return created_at + timedelta(days=AUDIT_TOKEN_VALIDITY_DAYS)


def is_expired(expires_at: datetime) -> bool:
    """Check if an audit has expired."""
    now = datetime.now(UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return now >= expires_at


def hash_ip(ip: str | None) -> str | None:
    """
    Hash an IP address for storage.

    Args:
        ip: The IP address to hash (may be None).

    Returns:
        SHA256 hash of the IP, or None if input was None.
    """
    if ip is None:
        return None
    return hashlib.sha256(ip.encode()).hexdigest()[:64]
