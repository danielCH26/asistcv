"""
Consent gate service for recruiter endpoints.

This service provides the consent check dependency that enforces
that recruiters have accepted the ToS before using roster endpoints.
"""
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db
from app.db.models import RecruiterConsent


async def check_recruiter_consent(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """
    Dependency that enforces recruiter consent.

    For recruiters, checks that they have an accepted consent record.
    For non-recruiters, passes through without check.

    The session comes from ``get_db`` so the recruiter_consents SELECT
    runs with the caller's RLS context bound (the table is protected by
    migration 011; without it every lookup would return zero rows).

    Raises:
        HTTPException 403 CONSENT_REQUIRED if recruiter has no consent

    Returns:
        CurrentUser if consent is valid
    """
    # Only check for recruiters
    if current_user.role != "recruiter":
        return current_user

    # Check for consent record
    result = await db.execute(
        select(RecruiterConsent).where(
            RecruiterConsent.user_id == current_user.id
        )
    )
    consent = result.scalar_one_or_none()

    if not consent or consent.accepted_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CONSENT_REQUIRED"
        )

    return current_user


async def get_recruiter_consent(
    user_id: int,
    db: AsyncSession,
) -> RecruiterConsent | None:
    """Get the consent record for a recruiter."""
    result = await db.execute(
        select(RecruiterConsent).where(
            RecruiterConsent.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def create_recruiter_consent(
    user_id: int,
    tos_version: str,
    ip: str | None,
    user_agent: str | None,
    db: AsyncSession,
) -> RecruiterConsent:
    """Create a new consent record for a recruiter."""
    consent = RecruiterConsent(
        user_id=user_id,
        accepted_at=datetime.now(UTC),
        tos_version=tos_version,
        ip=ip,
        user_agent=user_agent,
    )
    db.add(consent)
    await db.commit()
    await db.refresh(consent)
    return consent


# Type alias for dependency injection
RecruiterConsentDep = Annotated[CurrentUser, Depends(check_recruiter_consent)]
