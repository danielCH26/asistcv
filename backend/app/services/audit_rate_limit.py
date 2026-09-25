"""
Rate limiting for anonymous audit endpoint.

Implements 3 successful audits per IP per 24 hours.
Uses database-backed counter for simplicity (vs Redis).
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditUpload
from app.services.audit_token import hash_ip

# Rate limit configuration
AUDIT_RATE_LIMIT = 3  # Max successful audits per IP per day
AUDIT_RATE_LIMIT_WINDOW_HOURS = 24


async def get_audit_count_by_ip(session: AsyncSession, ip_hash: str) -> int:
    """
    Get the number of successful audits for an IP in the last 24 hours.

    Args:
        session: Database session
        ip_hash: SHA256 hash of the client IP

    Returns:
        Number of successful audits in the rate limit window
    """
    window_start = datetime.now(UTC) - timedelta(hours=AUDIT_RATE_LIMIT_WINDOW_HOURS)

    result = await session.execute(
        select(func.count(AuditUpload.id)).where(
            and_(
                AuditUpload.ip_hash == ip_hash,
                AuditUpload.created_at >= window_start,
            )
        )
    )
    return result.scalar() or 0


async def check_rate_limit(session: AsyncSession, ip: str | None) -> tuple[bool, int]:
    """
    Check if an IP has exceeded the rate limit.

    Args:
        session: Database session
        ip: Client IP address (may be None for internal requests)

    Returns:
        Tuple of (allowed: bool, seconds_until_reset: int)
        - allowed: True if the request is within the rate limit
        - seconds_until_reset: Seconds until the rate limit window resets
    """
    if ip is None:
        # No IP means no rate limit (internal requests)
        return True, 0

    ip_hash = hash_ip(ip)
    count = await get_audit_count_by_ip(session, ip_hash)

    if count >= AUDIT_RATE_LIMIT:
        # Calculate seconds until oldest audit expires from the window
        window_start = datetime.now(UTC) - timedelta(hours=AUDIT_RATE_LIMIT_WINDOW_HOURS)
        reset_time = window_start + timedelta(hours=AUDIT_RATE_LIMIT_WINDOW_HOURS)
        seconds_until_reset = max(0, int((reset_time - datetime.now(UTC)).total_seconds()))
        return False, seconds_until_reset

    return True, 0
