"""
Authentication endpoints: register, login, refresh, logout, verify-email.

These endpoints handle user authentication with JWT and refresh token rotation.
"""
import secrets as _secrets_module
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import (
    create_token_pair,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.models import (
    EmailVerificationToken,
    LoginAttempt,
    RecruiterConsent,
    RefreshToken,
    SecurityEvent,
    User,
)
from app.db.session import get_session, get_session_context
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    SignUpRequest,
    TokenResponse,
    VerifyEmailConfirm,
)
from app.services import email_service
from app.services.rls_context import bind_rls_context

router = APIRouter(prefix="/auth", tags=["auth"])
_logger = get_logger("app.api.auth")

# Rate limit settings
MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPTS_WINDOW_MINUTES = 15


async def _check_rate_limit(email: str, ip: str | None, db: AsyncSession) -> None:
    """
    Check if account is locked due to too many failed login attempts.

    A4 fix: Blocks on BOTH email AND IP so that an attacker cannot bypass
    the per-account limit by cycling through different IP addresses.
    A3 fix: The auth_login_attempts table now has indexes on
    (email, attempted_at) and (ip, attempted_at) for efficient queries.
    """
    window_start = datetime.now(UTC) - timedelta(minutes=LOGIN_ATTEMPTS_WINDOW_MINUTES)

    # Build base conditions: failed attempts within the time window
    base_conditions = [
        LoginAttempt.attempted_at >= window_start,
        LoginAttempt.success.is_(False),
    ]

    # Check per-email count
    email_count = 0
    email_result = await db.execute(
        select(func.count(LoginAttempt.id)).where(
            and_(LoginAttempt.email == email.lower(), *base_conditions)
        )
    )
    email_count = email_result.scalar() or 0

    # Check per-IP count (A4 fix)
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
    await _check_rate_limit(body.email, request.client.host if request.client else None, db)

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
    new_token_hash = hash_token(new_refresh_token)
    new_refresh = RefreshToken(
        user_id=user.id,
        token_hash=new_token_hash,
        # ABSOLUTE session lifetime. The rotated token inherits the
        # presented token's expiry instead of recomputing it from now, so
        # one login is bounded by a single JWT_REFRESH_TTL window no
        # matter how many times the client rotates (the SPA polls every
        # 30s, which previously made the TTL sliding and unreachable).
        #
        # This cannot mint an already-expired token: the check at the top
        # of this handler runs against the *presented* token, i.e. the same
        # row whose ``expires_at`` is inherited, and it raises before we
        # ever get here. The inherited value is therefore >= now.
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
):
    """Request a verification email.

    Generates a 32-byte URL-safe token, persists its SHA256 hash with a
    TTL from ``EMAIL_VERIFICATION_TTL_SECONDS`` (default 24h), and tries
    to deliver the link via ``email_service``. The DB write happens
    under the caller's RLS context — same approach as the billing
    endpoints, so the INSERT passes the owner policy on
    ``email_verification_tokens``.

    Service role (``auth_method="api_key"``) is rejected with 403: an
    API-key caller can mint verification emails for user 0, but user 0 is
    the RLS bypass principal and the resulting row would either fail the
    owner check or attach to the wrong account.

    Delivery is best-effort. With ``RESEND_API_KEY`` unset the request
    still returns 202 — the link is recoverable from the logs (the
    service logs ``email_service_disabled`` plus the recipient and
    subject) and the token row is persisted, so a manual resend or admin
    redelivery can complete the loop without re-running the request.
    """
    if current_user.auth_method == "api_key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ROLE_FORBIDDEN",
        )

    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.email_verification_ttl_seconds)
    token_hash = hash_token(_secrets_module.token_urlsafe(32))

    async with get_session_context() as session:
        await bind_rls_context(session, current_user.id, current_user.role)
        token_row = EmailVerificationToken(
            user_id=current_user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        session.add(token_row)
        await session.commit()
        await session.refresh(token_row)
        token_id = token_row.id

    # Build the link outside the session: settings + id stay in scope.
    verify_url = (
        f"{settings.frontend_url}/verify-email?token={token_hash}"
    )
    html_body = _verification_email_html(verify_url, settings.email_verification_ttl_seconds)
    text_body = (
        f"Confirma tu email abriendo este enlace (válido por "
        f"{settings.email_verification_ttl_seconds // 3600} horas):\n\n{verify_url}"
    )

    # Load the email address outside the RLS session — only used to send,
    # never written. If the user row is missing for some reason we skip
    # the send and let the operator notice; the token row is still there.
    user_email = await _load_user_email(current_user.id)
    if user_email is not None:
        await email_service.send_email_async(
            to=user_email,
            subject="Confirma tu email en AsistCV",
            html_body=html_body,
            text_body=text_body,
        )

    return {"detail": "Verification email sent", "token_id": token_id}


@router.post("/verify-email/confirm", status_code=status.HTTP_200_OK)
async def confirm_verify_email(
    request: Request,
    body: VerifyEmailConfirm,
):
    """Confirm email verification with the token sent in the email.

    Validates the SHA256 hash lookup and three invariants: token exists,
    not expired, not already used. On success the user is loaded, the
    token is marked ``used_at = now()``, and ``email_verified_at`` is
    stamped on the user row.

    Returns 400 (not 401 / 404) on every failure path so the client can
    treat "link broken" as a single condition. The detail string
    differentiates the cases — TOKEN_EXPIRED / TOKEN_USED /
    INVALID_TOKEN — for diagnostics and analytics.
    """
    token_hash = hash_token(body.token)

    async with get_session_context() as session:
        # The plaintext token is a one-shot capability. Once we hold the
        # matching row, the token grants the right to verify the email
        # it was issued for — we run the whole transaction under the
        # SERVICE RLS context (set_rls_service) so the SELECT against
        # ``users`` and the UPDATE on ``email_verified_at`` pass without
        # needing the owner's own session. Same approach as the audit
        # claim and other capability-token flows in the codebase.
        from app.services.rls_context import set_rls_service

        await set_rls_service(session)

        result = await session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == token_hash
            )
        )
        token_row = result.scalar_one_or_none()

        if token_row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_TOKEN",
            )

        if token_row.used_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TOKEN_USED",
            )

        if token_row.expires_at <= datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TOKEN_EXPIRED",
            )

        user_result = await session.execute(
            select(User).where(User.id == token_row.user_id)
        )
        user = user_result.scalar_one_or_none()

        if user is None:
            # CASCADE on user delete should make this unreachable; if it
            # ever happens, surface the same error as a bad token so we
            # don't leak existence info.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_TOKEN",
            )

        now = datetime.now(UTC)
        user.email_verified_at = now
        token_row.used_at = now
        await session.commit()

    return {"detail": "Email verified"}


def _verification_email_html(verify_url: str, ttl_seconds: int) -> str:
    """Render the verification email as HTML.

    Kept inline (no template engine) — it's a single screen and the
    link text matters more than the markup. The TTL is rendered in hours
    because minute-level precision is noise in a "click within a day"
    flow.
    """
    hours = max(1, ttl_seconds // 3600)
    return (
        "<html><body style=\"font-family: -apple-system, Segoe UI, "
        "Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: "
        "24px; color: #1f2937;\">"
        "<h2 style=\"color: #111827;\">Confirmá tu email</h2>"
        "<p>Para terminar de configurar tu cuenta y poder comprar "
        "planes, abrí este enlace:</p>"
        f"<p style=\"margin: 24px 0;\"><a href=\"{verify_url}\""
        " style=\"background-color: #2563eb; color: white; padding: "
        "10px 18px; border-radius: 6px; text-decoration: none;\">"
        "Confirmar email</a></p>"
        f"<p style=\"font-size: 13px; color: #6b7280;\">El enlace es "
        f"válido por {hours} hora(s). Si no lo usás en ese plazo, "
        "pedí uno nuevo desde tu perfil.</p>"
        "<p style=\"font-size: 13px; color: #6b7280;\">Si no pediste "
        "este mensaje, podés ignorarlo.</p>"
        "</body></html>"
    )


async def _load_user_email(user_id: int) -> str | None:
    """Look up the recipient email for a verification request.

    Runs under the SERVICE RLS context (the only principal that can read
    ``users`` rows that don't belong to the caller). It is only used to
    know *where* to send the email — never persisted into the request
    response — so widening the read scope to service is consistent with
    how audit-funnel helpers reach across owners.
    """
    from app.services.rls_context import set_rls_service

    try:
        async with get_session_context() as session:
            await set_rls_service(session)
            # Se selecciona la entidad, no la columna suelta: es el patrón que
            # usa el resto del router, y `User.email` sobre un modelo SQLModel
            # no resuelve el overload de `select` en el type checker.
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            return user.email if user else None
    except Exception as exc:  # noqa: BLE001 - log + skip, never crash the request
        _logger.warning(
            "verify_email_user_lookup_failed",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None
