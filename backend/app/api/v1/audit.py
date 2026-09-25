"""
Audit API endpoints for anonymous CV analysis.

Provides:
- POST /v1/audit/anonymous - Submit JD + CV for analysis (rate limited)
- POST /v1/audit/{token}/capture-email - Capture email for audit result
- POST /v1/audit/{token}/claim - Claim audit after user signup
- GET /v1/audit/{token} - Retrieve cached audit result
- POST /internal/audit/cleanup - Internal endpoint for retention cron
"""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models import AuditFunnelEvent, AuditUpload, User
from app.db.session import get_session_context
from app.schemas.audit import (
    AuditAnonymousResponse,
    AuditRetrieveResponse,
    CaptureEmailRequest,
    CaptureEmailResponse,
    ClaimAuditRequest,
    ClaimAuditResponse,
)
from app.services.audit_rate_limit import AUDIT_RATE_LIMIT, check_rate_limit
from app.services.audit_retention import delete_expired_audits, verify_cleanup_token
from app.services.audit_runner import run_audit
from app.services.audit_token import (
    compute_token_hash,
    hash_ip,
)
from app.services.rls_context import set_rls_anonymous, set_rls_service

router = APIRouter(tags=["audit"])
logger = get_logger("app.api.audit")

# Maximum PDF size (10MB)
MAX_PDF_SIZE = 10 * 1024 * 1024


def _get_client_ip(request: Request) -> str | None:
    """Extract client IP from request, handling X-Forwarded-For."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post(
    "/audit/anonymous",
    response_model=AuditAnonymousResponse,
    status_code=200,
    responses={
        413: {"description": "FILE_TOO_LARGE", "model": dict},
        415: {"description": "UNSUPPORTED_MEDIA_TYPE", "model": dict},
        422: {"description": "VALIDATION_ERROR", "model": dict},
        429: {"description": "RATE_LIMITED", "model": dict},
        503: {"description": "SERVICE_ERROR", "model": dict},
    },
)
async def create_audit(
    request: Request,
    response: Response,
) -> AuditAnonymousResponse:
    """
    Submit an anonymous audit request (JD + CV).

    Rate limited to 3 successful audits per IP per 24 hours.
    Returns the analysis result directly without persisting to analyses table.
    """
    # Get client IP for rate limiting
    client_ip = _get_client_ip(request)
    ip_hash = hash_ip(client_ip)

    async with get_session_context() as session:
        # Anonymous funnel context: unlinked audit_uploads rows only (RLS).
        await set_rls_anonymous(session)
        # Check rate limit
        allowed, retry_after = await check_rate_limit(session, client_ip)
        if not allowed:
            response.headers["Retry-After"] = str(retry_after)
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "RATE_LIMITED",
                    "message": f"Rate limit exceeded. Maximum {AUDIT_RATE_LIMIT} audits per day.",
                    "retry_after": retry_after,
                },
            )

        # Handle multipart form data
        form = await request.form()
        jd_text = form.get("jd_text", "")
        cv_text = form.get("cv_text", None)
        pdf_file = form.get("file")

        # Validate JD length
        if not jd_text or len(jd_text.strip()) < 50:
            raise HTTPException(
                status_code=422,
                detail={"code": "JD_TOO_SHORT", "message": "JD must be at least 50 characters"},
            )

        # Handle PDF file if provided
        pdf_bytes = None
        if pdf_file is not None:
            pdf_bytes = await pdf_file.read()
            if len(pdf_bytes) > MAX_PDF_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail={"code": "FILE_TOO_LARGE", "message": "PDF exceeds 10MB limit"},
                )

        # Run the audit
        try:
            result = await run_audit(
                session=session,
                jd_text=jd_text,
                cv_text=cv_text,
                pdf_bytes=pdf_bytes,
            )
        except ValueError as exc:
            if "JD_TOO_SHORT" in str(exc):
                raise HTTPException(
                    status_code=422,
                    detail={"code": "JD_TOO_SHORT", "message": str(exc)},
                )
            raise
        except Exception as exc:
            logger.error("audit_run_failed", error=str(exc)[:200])
            raise HTTPException(
                status_code=503,
                detail={"code": "SERVICE_ERROR", "message": "Failed to process audit"},
            )

        # Generate token and store audit
        from app.services.audit_token import calculate_expiry, generate_audit_token

        plain_token, token_hash = generate_audit_token()
        expires_at = calculate_expiry()

        # Create audit upload record
        audit = AuditUpload(
            audit_token_hash=token_hash,
            jd_text=jd_text,
            cv_text=cv_text,
            pdf_blob=pdf_bytes,
            audit_result_json=result.result_json,
            ip_hash=ip_hash,
            user_agent=request.headers.get("user-agent", "")[:500],
            expires_at=expires_at,
        )
        session.add(audit)

        # Log funnel event
        event = AuditFunnelEvent(
            ip_hash=ip_hash,
            step="audit_success",
            audit_id=audit.id,
        )
        session.add(event)

        await session.commit()
        await session.refresh(audit)

    # Set anti-scraping headers
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"

    return AuditAnonymousResponse(
        audit_token=plain_token,
        score=result.score,
        strengths=result.strengths,
        gaps=result.gaps,
        energy_level=result.energy_level,
        reasoning=result.reasoning,
    )


@router.post(
    "/audit/{token}/capture-email",
    response_model=CaptureEmailResponse,
    status_code=202,
    responses={
        400: {"description": "BAD_REQUEST", "model": dict},
        410: {"description": "AUDIT_EXPIRED", "model": dict},
        422: {"description": "EMAIL_INVALID", "model": dict},
    },
)
async def capture_email(
    token: str,
    body: CaptureEmailRequest,
) -> CaptureEmailResponse:
    """
    Capture email for an audit result.

    Allows users to receive their audit result via email.
    Only works within 1 hour of audit creation.
    """
    token_hash = compute_token_hash(token)

    async with get_session_context() as session:
        await set_rls_anonymous(session)
        result = await session.execute(
            select(AuditUpload).where(AuditUpload.audit_token_hash == token_hash)
        )
        audit = result.scalar_one_or_none()

        if audit is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "AUDIT_NOT_FOUND", "message": "Audit not found"},
            )

        # Check if audit is still valid (within 1 hour)
        age = datetime.now(UTC) - audit.created_at
        if age > timedelta(hours=1):
            raise HTTPException(
                status_code=410,
                detail={"code": "AUDIT_EXPIRED", "message": "Audit has expired (older than 1 hour)"},
            )

        # Check if email already captured
        if audit.email_captured:
            return CaptureEmailResponse(
                message="Email already captured for this audit",
            )

        # Update audit with email (in real implementation, would trigger email send)
        audit.email_captured = True
        # Store email temporarily in result_json for email sending
        if audit.audit_result_json is None:
            audit.audit_result_json = {}
        audit.audit_result_json["captured_email"] = body.email

        # Log funnel event
        event = AuditFunnelEvent(
            ip_hash=audit.ip_hash,
            step="capture_email",
            audit_id=audit.id,
        )
        session.add(event)

        await session.commit()

    # In production, trigger email sending here
    # For now, just return success

    return CaptureEmailResponse(
        message="Email captured successfully. Result will be sent shortly.",
    )


@router.post(
    "/audit/{token}/claim",
    response_model=ClaimAuditResponse,
    status_code=200,
    responses={
        400: {"description": "BAD_REQUEST", "model": dict},
        404: {"description": "AUDIT_NOT_FOUND", "model": dict},
    },
)
async def claim_audit(
    token: str,
    body: ClaimAuditRequest,
) -> ClaimAuditResponse:
    """
    Claim an audit after user signup.

    Links an anonymous audit to a user account so they can view it in their history.
    """
    token_hash = compute_token_hash(token)

    async with get_session_context() as session:
        # The claim links an anonymous audit to an account; the audit token
        # is the capability, so this backend-sanctioned transition runs in
        # the service context (anonymous WITH CHECK forbids linking).
        await set_rls_service(session)
        # Verify user exists
        user = await session.get(User, body.user_id)
        if user is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "USER_NOT_FOUND", "message": "User not found"},
            )

        # Find audit
        result = await session.execute(
            select(AuditUpload).where(AuditUpload.audit_token_hash == token_hash)
        )
        audit = result.scalar_one_or_none()

        if audit is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "AUDIT_NOT_FOUND", "message": "Audit not found"},
            )

        # Check if already linked
        if audit.linked_user_id is not None:
            return ClaimAuditResponse(
                success=True,
                message="Audit already linked to an account",
            )

        # Link audit to user
        audit.linked_user_id = body.user_id
        # Extend expiry to 30 more days from now (if not already extended)
        from app.services.audit_token import calculate_expiry

        if audit.email_captured:
            # Keep existing expiry if email was captured
            pass
        else:
            audit.expires_at = calculate_expiry()

        # Log funnel event
        event = AuditFunnelEvent(
            ip_hash=audit.ip_hash,
            step="audit_to_signup",
            audit_id=audit.id,
        )
        session.add(event)

        await session.commit()

    return ClaimAuditResponse(
        success=True,
        message="Audit linked to your account successfully",
    )


@router.get(
    "/audit/{token}",
    response_model=AuditRetrieveResponse,
    responses={
        404: {"description": "AUDIT_NOT_FOUND", "model": dict},
        410: {"description": "AUDIT_EXPIRED", "model": dict},
    },
)
async def get_audit(token: str) -> AuditRetrieveResponse:
    """
    Retrieve a cached audit result by token.

    Returns the audit if still valid (not expired).
    """
    token_hash = compute_token_hash(token)

    async with get_session_context() as session:
        await set_rls_anonymous(session)
        result = await session.execute(
            select(AuditUpload).where(AuditUpload.audit_token_hash == token_hash)
        )
        audit = result.scalar_one_or_none()

        if audit is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "AUDIT_NOT_FOUND", "message": "Audit not found"},
            )

        # Check if expired
        now = datetime.now(UTC)
        if audit.expires_at.tzinfo is None:
            audit.expires_at = audit.expires_at.replace(tzinfo=UTC)

        if now >= audit.expires_at:
            raise HTTPException(
                status_code=410,
                detail={"code": "AUDIT_EXPIRED", "message": "Audit has expired"},
            )

        if audit.audit_result_json is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "AUDIT_RESULT_NOT_FOUND", "message": "Audit result not found"},
            )

        return AuditRetrieveResponse(
            score=audit.audit_result_json.get("score", 0),
            strengths=audit.audit_result_json.get("strengths", []),
            gaps=audit.audit_result_json.get("gaps", []),
            energy_level=audit.audit_result_json.get("energy_level", "unknown"),
            reasoning=audit.audit_result_json.get("reasoning", ""),
            created_at=audit.created_at,
            email_captured=audit.email_captured,
        )


# Internal endpoint for cron job
@router.post(
    "/internal/audit/cleanup",
    status_code=200,
)
async def cleanup_audits(
    request: Request,
) -> dict:
    """
    Internal endpoint for cleaning up expired audits.

    Called by GitHub Actions cron job daily.
    Requires AUDIT_CLEANUP_TOKEN in the request body.
    """
    try:
        body = await request.json()
        token = body.get("token")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={"code": "BAD_REQUEST", "message": "Missing token in request body"},
        )

    if not verify_cleanup_token(token):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Invalid cleanup token"},
        )

    async with get_session_context() as session:
        # Cron retention path: service context (RLS bypass) so the DELETE
        # reaches expired unlinked rows without a user principal.
        await set_rls_service(session)
        deleted_count = await delete_expired_audits(session)

    return {
        "status": "success",
        "deleted_count": deleted_count,
    }
