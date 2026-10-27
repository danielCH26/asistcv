"""
Authentication endpoints: passwordless email-code login, refresh, logout.

Slice S1b of feat/passwordless-auth (Clerk replacement). Login and signup
share one flow: the user submits an email, receives a 6-digit code, and
verification issues a native token pair — creating the account on first
login. Passwords are not part of this flow (``users.password_hash`` is
nullable since migration 029).
"""
from datetime import UTC, datetime, timedelta

import secrets as _secrets_module
import string as _string_module

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import create_token_pair, hash_email_code, hash_token
from app.db.models import (
    AuthEmailCode,
    LoginAttempt,
    RefreshToken,
    SecurityEvent,
    User,
)
from app.db.session import get_session
from app.schemas.auth import (
    EmailCodeRequest,
    EmailCodeVerifyRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services import email_service

router = APIRouter(prefix="/auth", tags=["auth"])
_logger = get_logger("app.api.auth")

# Brute-force protection (ported from the pre-Clerk auth router).
MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPTS_WINDOW_MINUTES = 15

# Email-code specific throttles.
CODE_RESEND_COOLDOWN_SECONDS = 60
CODE_HOURLY_CAP = 10


async def _check_rate_limit(email: str, ip: str | None, db: AsyncSession) -> None:
    """Reject the request when too many failed attempts accumulated.

    Blocks on BOTH email AND IP so an attacker cannot bypass the
    per-account limit by cycling IP addresses (A4 fix). Relies on the
    indexes on ``auth_login_attempts (email, attempted_at)`` and
    ``(ip, attempted_at)``.
    """
    window_start = datetime.now(UTC) - timedelta(minutes=LOGIN_ATTEMPTS_WINDOW_MINUTES)

    base_conditions = [
        LoginAttempt.attempted_at >= window_start,
        LoginAttempt.success.is_(False),
    ]

    email_result = await db.execute(
        select(func.count(LoginAttempt.id)).where(
            and_(LoginAttempt.email == email.lower(), *base_conditions)
        )
    )
    email_count = email_result.scalar() or 0

    ip_count = 0
    if ip:
        ip_result = await db.execute(
            select(func.count(LoginAttempt.id)).where(
                and_(LoginAttempt.ip == ip, *base_conditions)
            )
        )
        ip_count = ip_result.scalar() or 0

    if email_count >= MAX_LOGIN_ATTEMPTS or ip_count >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="RATE_LIMITED",
            headers={"Retry-After": str(LOGIN_ATTEMPTS_WINDOW_MINUTES * 60)},
        )


async def _record_login_attempt(
    email: str,
    success: bool,
    db: AsyncSession,
    request: Request,
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
    details: dict | None = None,
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


def _generate_code(length: int) -> str:
    """Generate a numeric one-time code (crypto-grade randomness)."""
    return "".join(_secrets_module.choice(_string_module.digits) for _ in range(length))


def _code_email_html(code: str, ttl_minutes: int) -> str:
    """HTML body for the login-code email (Spanish, matches the product)."""
    return (
        "<html><body style=\"font-family:Arial,sans-serif\">"
        "<h2>Tu código para entrar a AsistCV</h2>"
        f"<p style=\"font-size:28px;font-weight:bold;letter-spacing:6px\">{code}</p>"
        f"<p>Este código vence en {ttl_minutes} minutos y puede usarse una sola vez.</p>"
        "<p>Si no fuiste vos, ignorá este mensaje.</p>"
        "</body></html>"
    )


def _code_email_text(code: str, ttl_minutes: int) -> str:
    """Plain-text body for the login-code email."""
    return (
        f"Tu código para entrar a AsistCV es: {code}\n\n"
        f"Vence en {ttl_minutes} minutos y puede usarse una sola vez.\n"
        "Si no fuiste vos, ignorá este mensaje."
    )


@router.post("/email-code/request", status_code=status.HTTP_202_ACCEPTED)
async def request_email_code(
    request: Request,
    body: EmailCodeRequest,
    db: AsyncSession = Depends(get_session),
):
    """Email a one-time login code to ``body.email``.

    The response is deliberately generic (no account-existence leak).
    Throttles: brute-force window (shared with login), a per-email
    resend cooldown, and an hourly cap per email so the endpoint can't
    be weaponized to bomb someone's inbox.

    Delivery is best-effort: with no provider key the request still
    returns 202 and the code is recoverable from the service log (the
    ``console`` provider prints it; the disabled provider logs it).
    """
    settings = get_settings()
    email = body.email.strip().lower()
    ip = request.client.host if request.client else None

    await _check_rate_limit(email, ip, db)

    now = datetime.now(UTC)

    # Resend cooldown: no second code for the same email inside the window.
    cooldown_start = now - timedelta(seconds=CODE_RESEND_COOLDOWN_SECONDS)
    recent = await db.execute(
        select(func.count(AuthEmailCode.id)).where(
            and_(
                AuthEmailCode.email == email,
                AuthEmailCode.created_at >= cooldown_start,
            )
        )
    )
    if (recent.scalar() or 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="CODE_COOLDOWN",
            headers={"Retry-After": str(CODE_RESEND_COOLDOWN_SECONDS)},
        )

    # Hourly cap per email (anti mail-bombing with paced requests).
    hour_start = now - timedelta(hours=1)
    hourly = await db.execute(
        select(func.count(AuthEmailCode.id)).where(
            and_(
                AuthEmailCode.email == email,
                AuthEmailCode.created_at >= hour_start,
            )
        )
    )
    if (hourly.scalar() or 0) >= CODE_HOURLY_CAP:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="RATE_LIMITED",
            headers={"Retry-After": "3600"},
        )

    code = _generate_code(settings.email_code_length)
    code_row = AuthEmailCode(
        email=email,
        code_hash=hash_email_code(code),
        expires_at=now + timedelta(seconds=settings.email_code_ttl_seconds),
    )

    # Single active code per email: retire any previous unused codes so
    # verification can only succeed against the newest one.
    await db.execute(
        update(AuthEmailCode)
        .where(
            AuthEmailCode.email == email,
            AuthEmailCode.used_at.is_(None),
        )
        .values(used_at=now)
    )
    db.add(code_row)
    await db.commit()

    ttl_minutes = max(1, settings.email_code_ttl_seconds // 60)
    await email_service.send_email_async(
        to=email,
        subject="Tu código para entrar a AsistCV",
        html_body=_code_email_html(code, ttl_minutes),
        text_body=_code_email_text(code, ttl_minutes),
    )

    return {"detail": "CODE_SENT"}


@router.post("/email-code/verify", response_model=TokenResponse)
async def verify_email_code(
    request: Request,
    body: EmailCodeVerifyRequest,
    db: AsyncSession = Depends(get_session),
):
    """Verify the code and issue a native token pair.

    Creates the account on first login (email is proven by the code);
    stamps ``email_verified_at`` for existing unverified accounts.
    Failures are recorded as login attempts so the shared brute-force
    window applies; the code itself enforces its own attempt budget.
    """
    settings = get_settings()
    email = body.email.strip().lower()
    ip = request.client.host if request.client else None
    now = datetime.now(UTC)

    await _check_rate_limit(email, ip, db)

    result = await db.execute(
        select(AuthEmailCode)
        .where(AuthEmailCode.email == email)
        .order_by(AuthEmailCode.created_at.desc(), AuthEmailCode.id.desc())
    )
    code_row = result.scalars().first()

    if code_row is None or code_row.used_at is not None:
        await _record_login_attempt(email, False, db, request)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INVALID_CODE",
        )

    if code_row.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CODE_EXPIRED",
        )

    if code_row.attempts >= settings.email_code_max_attempts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CODE_MAX_ATTEMPTS",
        )

    if not _secrets_module.compare_digest(
        code_row.code_hash, hash_email_code(body.code)
    ):
        code_row.attempts += 1
        await db.commit()
        await _record_login_attempt(email, False, db, request)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INVALID_CODE",
        )

    # Success: burn the code.
    code_row.used_at = now

    # Find-or-create the account.
    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalar_one_or_none()
    created = False
    if user is None:
        user = User(
            email=email,
            password_hash=None,
            role="job_seeker",
            full_name="",
            locale="es",
            email_verified_at=now,
        )
        db.add(user)
        created = True
    elif user.email_verified_at is None:
        # Ownership of the address is proven by the code itself.
        user.email_verified_at = now

    user.last_login_at = now
    await db.flush()

    access_token, refresh_token = create_token_pair(user.id, user.role)
    refresh = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=now + timedelta(seconds=settings.jwt_refresh_ttl),
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(refresh)
    await db.commit()

    await _record_login_attempt(email, True, db, request)
    if created:
        await _record_security_event(
            "user_created_email_code",
            user.id,
            db,
            request,
            {"email": email},
        )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_session),
):
    """Refresh access token with rotation (ported from the native era)."""
    token_hash = hash_token(body.refresh_token)

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    refresh_token = result.scalar_one_or_none()

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOKEN_INVALID",
        )

    if refresh_token.revoked_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOKEN_INVALID",
        )

    if refresh_token.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOKEN_INVALID",
        )

    # Reuse detection: a rotated-away token coming back means the token
    # store leaked — revoke the user's whole active family.
    if refresh_token.consumed_at:
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == refresh_token.user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.consumed_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await _record_security_event(
            "token_reuse",
            refresh_token.user_id,
            db,
            request,
            {"token_id": refresh_token.id},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOKEN_REUSED",
        )

    refresh_token.consumed_at = datetime.now(UTC)

    user_result = await db.execute(
        select(User).where(User.id == refresh_token.user_id)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOKEN_INVALID",
        )

    access_token, new_refresh_token = create_token_pair(user.id, user.role)

    new_token_hash = hash_token(new_refresh_token)
    new_refresh = RefreshToken(
        user_id=user.id,
        token_hash=new_token_hash,
        # ABSOLUTE session lifetime: inherit the presented token's expiry
        # instead of recomputing from now, so one login is bounded by a
        # single JWT_REFRESH_TTL window no matter how many rotations the
        # SPA performs. Cannot mint an expired token: the expiry check at
        # the top ran against this same row and it inherits from itself.
        expires_at=refresh_token.expires_at,
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

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    refresh_token = result.scalar_one_or_none()

    if refresh_token:
        refresh_token.revoked_at = datetime.now(UTC)
        await db.commit()

    # The access token is not revoked (it expires naturally); stricter
    # setups could add it to token_revocation.

    return None
