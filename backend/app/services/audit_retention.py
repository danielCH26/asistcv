"""
Audit retention service - handles cleanup of expired anonymous audits.

Removes audit uploads that have expired AND are not linked to a user account.
This preserves audits that users have claimed after signing up.
"""
from datetime import UTC, datetime

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import AuditFunnelEvent, AuditUpload

logger = get_logger("app.services.audit_retention")

# Internal cleanup token config key
AUDIT_CLEANUP_TOKEN_ENV = "AUDIT_CLEANUP_TOKEN"


async def delete_expired_audits(session: AsyncSession) -> int:
    """
    Delete all expired audits that are not linked to a user account.

    This function:
    - Finds audits where expires_at < now() AND linked_user_id IS NULL
    - Deletes associated funnel events first (to handle FK constraint)
    - Logs an audit_funnel_event for each deletion
    - Returns the count of deleted audits

    Args:
        session: Database session

    Returns:
        Number of audits deleted
    """
    now = datetime.now(UTC)

    # Find expired, unlinked audits
    result = await session.execute(
        select(AuditUpload).where(
            and_(
                AuditUpload.expires_at < now,
                AuditUpload.linked_user_id.is_(None),
            )
        )
    )
    expired_audits = result.scalars().all()
    count = len(expired_audits)

    if count == 0:
        logger.info("audit_retention_no_expired_audits")
        return 0

    # Get IDs for deletion
    expired_ids = [audit.id for audit in expired_audits]

    # Delete funnel events first (to handle FK constraint)
    await session.execute(
        delete(AuditFunnelEvent).where(
            AuditFunnelEvent.audit_id.in_(expired_ids)
        )
    )

    # Delete the expired audits
    await session.execute(
        delete(AuditUpload).where(
            and_(
                AuditUpload.expires_at < now,
                AuditUpload.linked_user_id.is_(None),
            )
        )
    )
    await session.commit()

    logger.info("audit_retention_deleted", count=count)
    return count


def verify_cleanup_token(token: str) -> bool:
    """
    Verify the cleanup token against the configured value.

    Args:
        token: Token submitted in the cleanup request

    Returns:
        True if the token matches the configured value
    """
    import hmac

    settings = get_settings()
    configured_token = getattr(settings, "audit_cleanup_token", None)

    if configured_token is None:
        logger.warning("audit_cleanup_token_not_configured")
        return False

    return hmac.compare_digest(token, configured_token)
