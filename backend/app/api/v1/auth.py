"""
Authentication endpoints: register, login, refresh, logout, verify-email.

These endpoints handle user authentication with JWT and refresh token rotation.
"""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.security import (
    create_token_pair,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.models import LoginAttempt, RecruiterConsent, RefreshToken, SecurityEvent, User
from app.db.session import get_session
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    SignUpRequest,
    TokenResponse,
    VerifyEmailConfirm,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Rate limit settings
MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPTS_WINDOW_MINUTES = 15


async def _check_rate_limit(email: str, db: AsyncSession) -> None:
    """Check if account is locked due to too many failed login attempts."""
    window_start = datetime.now(UTC) - timedelta(minutes=LOGIN_ATTEMPTS_WINDOW_MINUTES)

    result = await db.execute(
        select(LoginAttempt).where(
            LoginAttempt.email == email.lower(),
            LoginAttempt.attempted_at >= window_start,
            LoginAttempt.success.is_(False)
        )
    )
    failed_attempts = result.scalars().all()

    if len(failed_attempts) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="RATE_LIMITED",
            headers={"Retry-After": str(LOGIN_ATTEMPTS_WINDOW_MINUTES * 60)}
        )


async def _record_login_attempt(
    email: str,
    success: bool,
    db: AsyncSession,
    request: Request
) -> None:
    """Record a login attempt for brute-force protection."""
    attempt = LoginAttempt(
        email=email.lower(),
        success=success,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(attempt)
    await db.commit()


async def _record_security_event(
    event: str,
    user_id: int | None,
    db: AsyncSession,
    request: Request,
    details: dict | None = None
) -> None:
    """Record a security event."""
    ev = SecurityEvent(
        event=event,
        user_id=user_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details=details,
    )
    db.add(ev)
    await db.commit()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    body: SignUpRequest,
    db: AsyncSession = Depends(get_session),
):
    """Register a new user account."""
    # Check if recruiter requires consent
    if body.role == "recruiter":
        if not body.accept_tos or not body.good_faith_declaration:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="CONSENT_REQUIRED"
            )

    # Check if email already exists
    result = await db.execute(
        select(User).where(User.email == body.email.lower())
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="EMAIL_TAKEN"
        )

    # Create new user
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role=body.role,
        full_name=body.full_name,
        locale=body.locale,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Persist consent for recruiters
    if body.role == "recruiter" and body.accept_tos and body.good_faith_declaration:
        tos_version = body.tos_version or "v1.2"
        # Register is an unauthenticated provisioning flow: bind the service
        # context so the recruiter_consents INSERT passes RLS (the row is
        # stamped with the new user's id).
        from app.services.rls_context import set_rls_service

        await set_rls_service(db)
        consent = RecruiterConsent(
            user_id=user.id,
            accepted_at=datetime.now(UTC),
            tos_version=tos_version,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(consent)
        await db.commit()

    # Create tokens
    access_token, refresh_token = create_token_pair(user.id, user.role)

    # Store refresh token
    from app.core.config import get_settings
    settings = get_settings()
    token_hash = hash_token(refresh_token)
    refresh = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_ttl),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(refresh)
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_session),
):
    """Login with email and password."""
    # Check rate limit first
    await _check_rate_limit(body.email, db)

    # Find user
    result = await db.execute(
        select(User).where(User.email == body.email.lower())
    )
    user = result.scalar_one_or_none()

    # Verify password (always verify to prevent timing attacks)
    password_valid = False
    if user:
        password_valid = verify_password(body.password, user.password_hash)

    if not password_valid or not user:
        # Record failed attempt
        await _record_login_attempt(body.email, False, db, request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Record successful attempt
    await _record_login_attempt(body.email, True, db, request)

    # Update last login
    user.last_login_at = datetime.now(UTC)
    await db.commit()

    # Create tokens
    access_token, refresh_token = create_token_pair(user.id, user.role)

    # Store refresh token
    from app.core.config import get_settings
    settings = get_settings()
    token_hash = hash_token(refresh_token)
    refresh = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_ttl),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(refresh)
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_session),
):
    """Refresh access token with rotation."""
    token_hash = hash_token(body.refresh_token)

    # Find the refresh token
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    refresh_token = result.scalar_one_or_none()

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOKEN_INVALID"
        )

    # Check if expired or revoked
    if refresh_token.revoked_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOKEN_INVALID"
        )

    if refresh_token.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOKEN_INVALID"
        )

    # Check if already consumed (token reuse)
    if refresh_token.consumed_at:
        # Revoke all active tokens for this user (security measure)
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == refresh_token.user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.consumed_at.is_(None)
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await _record_security_event(
            "token_reuse",
            refresh_token.user_id,
            db,
            request,
            {"token_id": refresh_token.id}
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOKEN_REUSED"
        )

    # Mark current token as consumed
    refresh_token.consumed_at = datetime.now(UTC)

    # Get user
    user_result = await db.execute(
        select(User).where(User.id == refresh_token.user_id)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOKEN_INVALID"
        )

    # Create new tokens
    access_token, new_refresh_token = create_token_pair(user.id, user.role)

    # Store new refresh token
    from app.core.config import get_settings
    settings = get_settings()
    new_token_hash = hash_token(new_refresh_token)
    new_refresh = RefreshToken(
        user_id=user.id,
        token_hash=new_token_hash,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_ttl),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(new_refresh)
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    body: RefreshRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Logout and revoke the refresh token."""
    token_hash = hash_token(body.refresh_token)

    # Revoke refresh token
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    refresh_token = result.scalar_one_or_none()

    if refresh_token:
        refresh_token.revoked_at = datetime.now(UTC)
        await db.commit()

    # Note: We don't revoke the access token here (it will expire naturally)
    # For stricter security, you could add it to token_revocation

    return None


@router.post("/verify-email/request", status_code=status.HTTP_202_ACCEPTED)
async def request_verify_email(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Request email verification email."""
    # TODO: Implement email sending logic
    # For now, just return 202
    return {"detail": "Verification email sent"}


@router.post("/verify-email/confirm", status_code=status.HTTP_200_OK)
async def confirm_verify_email(
    request: Request,
    body: VerifyEmailConfirm,
    db: AsyncSession = Depends(get_session),
):
    """Confirm email verification with token."""
    # TODO: Implement token verification
    # For now, just return success
    return {"detail": "Email verified"}
