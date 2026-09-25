"""
Recruiter consent endpoints.

Provides endpoints for recruiters to give or update their consent.
This is required for the consent gate on recruiter roster endpoints.
"""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.db.models import RecruiterAuditLog, RecruiterConsent
from app.schemas.recruiter import ConsentRequest, ConsentResponse

router = APIRouter(prefix="/recruiter/consent", tags=["recruiter-consent"])

# Current ToS version - in production, this would come from config
CURRENT_TOS_VERSION = "v1.2"


def _audit_log(
    db: AsyncSession,
    recruiter_id: int,
    action: str,
    details: dict | None = None,
) -> None:
    """Helper to create audit log entries for consent events."""
    log = RecruiterAuditLog(
        recruiter_id=recruiter_id,
        action=action,
        details=details,
    )
    db.add(log)


@router.post("", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED)
async def give_consent(
    request: Request,
    body: ConsentRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Give or update consent as a recruiter.

    This endpoint allows:
    - New recruiters to give initial consent during registration
    - Existing recruiters to re-consent when ToS is updated

    Returns the consent record with accepted_at timestamp.
    """
    # Only recruiters can give consent
    if current_user.role != "recruiter":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ROLE_FORBIDDEN"
        )

    # Validate consent fields
    if not body.accept_tos or not body.good_faith_declaration:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CONSENT_REQUIRED"
        )

    # Use provided tos_version or default to current
    tos_version = body.tos_version or CURRENT_TOS_VERSION

    # Check if consent already exists
    result = await db.execute(
        select(RecruiterConsent).where(
            RecruiterConsent.user_id == current_user.id
        )
    )
    existing_consent = result.scalar_one_or_none()

    if existing_consent:
        # Update existing consent - this is a re-consent event
        existing_consent.accepted_at = datetime.now(UTC)
        existing_consent.tos_version = tos_version
        existing_consent.ip = request.client.host if request.client else None
        existing_consent.user_agent = request.headers.get("user-agent")
        await db.flush()

        # Log consent_recovered event
        _audit_log(
            db,
            current_user.id,
            "consent_recovered",
            {"tos_version": tos_version},
        )

        await db.commit()
        await db.refresh(existing_consent)
        return ConsentResponse(
            accepted_at=existing_consent.accepted_at,
            tos_version=existing_consent.tos_version,
        )

    # Create new consent
    consent = RecruiterConsent(
        user_id=current_user.id,
        accepted_at=datetime.now(UTC),
        tos_version=tos_version,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(consent)
    await db.flush()

    # Log consent_given event
    _audit_log(
        db,
        current_user.id,
        "consent_given",
        {"tos_version": tos_version},
    )

    await db.commit()
    await db.refresh(consent)

    return ConsentResponse(
        accepted_at=consent.accepted_at,
        tos_version=consent.tos_version,
    )


@router.get("", response_model=ConsentResponse)
async def get_consent(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Get current consent status for the authenticated recruiter.
    """
    if current_user.role != "recruiter":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ROLE_FORBIDDEN"
        )

    result = await db.execute(
        select(RecruiterConsent).where(
            RecruiterConsent.user_id == current_user.id
        )
    )
    consent = result.scalar_one_or_none()

    if not consent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CONSENT_REQUIRED"
        )

    return ConsentResponse(
        accepted_at=consent.accepted_at,
        tos_version=consent.tos_version,
    )
