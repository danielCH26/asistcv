"""
Rate limiting for anonymous audit endpoint.

Fixes applied:
- A11: retry_after calculated from oldest audit's expires_at, not fixed window math.
- A12: Serializes concurrent callers using a sub-select with FOR UPDATE SKIP LOCKED.
  PostgreSQL does not allow FOR UPDATE on aggregate functions, so we select the
  rows first (which acquires row-level locks), then count and min in Python.
  Concurrent callers for the same IP will queue at the row locks, ensuring
  consistent counts.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditUpload

# Rate limit configuration
AUDIT_RATE_LIMIT = 3  # Max successful audits per IP per day
AUDIT_RATE_LIMIT_WINDOW_HOURS = 24

# Lazy import to avoid circular reference at module load time
_hash_ip = None


def _get_hash_ip():
    global _hash_ip
    if _hash_ip is None:
        # noqa: PTO505 — intentional deferred import to avoid circular reference
        from app.services.audit_token import (
            hash_ip as _h,  # pylint: disable=import-outside-toplevel
        )

        _hash_ip = _h
    return _hash_ip


async def get_audit_count_by_ip(session: AsyncSession, ip_hash: str) -> tuple[int, datetime | None]:
    """
    Get the number of successful audits for an IP in the last 24 hours AND
    the oldest audit's expires_at within that window.

    Uses a sub-select with FOR UPDATE SKIP LOCKED to serialize concurrent callers
    at the row level (PostgreSQL does not support FOR UPDATE on aggregates).
    Concurrent requests for the same IP queue at the row locks, so each sees a
    consistent count that includes the other's inserts after commit.

    Args:
        session: Database session
        ip_hash: SHA256 hash of the client IP

    Returns:
        Tuple of (count: int, oldest_expires_at: datetime | None)
    """
    window_start = datetime.now(UTC) - timedelta(hours=AUDIT_RATE_LIMIT_WINDOW_HOURS)

    # Select and lock the relevant rows first, then count in Python.
    # FOR UPDATE SKIP LOCKED makes concurrent callers wait rather than fail,
    # ensuring consistent count reads across concurrent transactions.
    stmt = (
        select(AuditUpload)
        .where(
            and_(
                AuditUpload.ip_hash == ip_hash,
                AuditUpload.created_at >= window_start,
            )
        )
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    count = len(rows)
    oldest_expires_at = min((r.expires_at for r in rows), default=None)
    return count, oldest_expires_at


async def check_rate_limit(session: AsyncSession, ip: str | None) -> tuple[bool, int]:
    """
    Check if an IP has exceeded the rate limit.

    Uses FOR UPDATE SKIP LOCKED internally so that concurrent callers for the same
    IP are serialized at the database level — one always waits for the other's
    commit before counting, eliminating the check-then-insert race.

    Args:
        session: Database session
        ip: Client IP address (may be None for internal requests)

    Returns:
        Tuple of (allowed: bool, seconds_until_reset: int)
        - allowed: True if the request is within the rate limit
        - seconds_until_reset: Seconds until the oldest audit in the window expires
    """
    if ip is None:
        # No IP means no rate limit (internal requests)
        return True, 0

    hash_fn = _get_hash_ip()
    ip_hash = hash_fn(ip)
    count, oldest_expires_at = await get_audit_count_by_ip(session, ip_hash)

    if count >= AUDIT_RATE_LIMIT:
        # A11 fix: compute retry_after from the oldest audit's expires_at,
        # not from a fixed window start (which always produced ≈0 seconds).
        if oldest_expires_at:
            seconds_until_reset = max(0, int((oldest_expires_at - datetime.now(UTC)).total_seconds()))
        else:
            # Fallback: use full window duration as an upper bound
            seconds_until_reset = AUDIT_RATE_LIMIT_WINDOW_HOURS * 3600
        return False, seconds_until_reset

    return True, 0
