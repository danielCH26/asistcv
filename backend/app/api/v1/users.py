"""
User profile endpoints: GET/PATCH /users/me, password change.

These endpoints allow users to view and update their own profile.
"""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.security import hash_password, verify_password
from app.db.models import RefreshToken, User
from app.db.session import get_session
from app.schemas.auth import (
    ChangePasswordRequest,
    UpdateUserRequest,
    UserResponse,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Get current user's profile."""
    if current_user.auth_method == "api_key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ROLE_FORBIDDEN"
        )

    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    request: UpdateUserRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Update current user's profile."""
    if current_user.auth_method == "api_key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ROLE_FORBIDDEN"
        )

    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check if trying to change role (forbidden)
    if request.model_dump(exclude_unset=True).get("role"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ROLE_IMMUTABLE"
        )

    # Update allowed fields
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field != "role":  # Role is immutable
            setattr(user, field, value)

    user.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)

    return user


@router.post("/me/password", status_code=status.HTTP_200_OK)
async def change_password(
    request: ChangePasswordRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Change current user's password."""
    if current_user.auth_method == "api_key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ROLE_FORBIDDEN"
        )

    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Verify current password
    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_PASSWORD"
        )

    # Update password
    user.password_hash = hash_password(request.new_password)
    user.updated_at = datetime.now(UTC)

    # Revoke all active refresh tokens (force re-login)
    await db.execute(
        RefreshToken.__table__.update()
        .where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.consumed_at.is_(None)
        )
        .values(revoked_at=datetime.now(UTC))
    )

    await db.commit()

    return {"detail": "Password changed successfully"}
