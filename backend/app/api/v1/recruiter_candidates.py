"""
Recruiter candidates endpoints.

CRUD operations for external candidates managed by recruiters.
"""
import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.logging import get_logger
from app.db.models import (
    RecruiterAnalysis,
    RecruiterAuditLog,
    RecruiterCandidate,
    RecruiterCandidateCV,
)
from app.db.session import get_session_context
from app.schemas.recruiter import (
    CandidateCreate,
    CandidateListResponse,
    CandidateMatchRequest,
    CandidateMatchResponse,
    CandidateRankedResponse,
    CandidateResponse,
    CandidateUpdate,
)
from app.services.consent_gate import check_recruiter_consent
from app.services.pdf_parser import PDFNoTextError, PDFParseError, parse_pdf
from app.services.rls_context import bind_rls_context
from app.services.tier_limits import check_limit, increment_usage

router = APIRouter(prefix="/recruiter/candidates", tags=["recruiter-candidates"])
logger = get_logger("app.api.recruiter_candidates")

# Constants
MAX_CV_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100


def _audit_log(
    db: AsyncSession,
    recruiter_id: int,
    action: str,
    candidate_id: int | None = None,
    details: dict | None = None,
) -> None:
    """Helper to create audit log entries."""
    log = RecruiterAuditLog(
        recruiter_id=recruiter_id,
        candidate_id=candidate_id,
        action=action,
        details=details,
    )
    db.add(log)


async def _parse_pdf_cv(
    file: UploadFile,
) -> tuple[bytes, str | None]:
    """
    Parse PDF CV and extract text.

    Returns (raw_bytes, raw_text).
    Uses pdf_parser service to extract text from PDF.
    """
    contents = await file.read()
    if len(contents) > MAX_CV_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="FILE_TOO_LARGE"
        )

    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="UNSUPPORTED_MEDIA_TYPE"
        )

    # Parse PDF and extract text
    try:
        parsed = parse_pdf(contents)
        return contents, parsed.raw_text
    except PDFNoTextError:
        # PDF has no extractable text
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF_NO_TEXT"
        )
    except PDFParseError:
        # PDF parsing failed completely
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PDF_PARSE_FAILED"
        )


@router.post("", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    request: Request,
    body: CandidateCreate,
    file: UploadFile | None = File(None),
    current_user: CurrentUser = Depends(check_recruiter_consent),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new candidate in the recruiter's roster.

    Accepts multipart with candidate data and optional PDF CV.
    """
    # This endpoint uses the consent gate from main.py
    # The actual implementation will use RecruiterConsentDep

    # Check for duplicate email within this recruiter's roster
    if body.email:
        result = await db.execute(
            select(RecruiterCandidate).where(
                RecruiterCandidate.recruiter_id == current_user.id,
                RecruiterCandidate.email == body.email.lower(),
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CANDIDATE_DUPLICATED"
            )

    # Handle CV upload if provided
    cv_id = None
    raw_blob = None
    raw_text = None

    if file:
        raw_blob, raw_text = await _parse_pdf_cv(file)
        cv = RecruiterCandidateCV(
            candidate_id=None,  # Will update after candidate is created
            original_filename=file.filename or "unknown.pdf",
            raw_blob=raw_blob,
            raw_text=raw_text,
        )
        db.add(cv)
        await db.flush()
        cv_id = cv.id

    # Create candidate
    candidate = RecruiterCandidate(
        recruiter_id=current_user.id,
        full_name=body.full_name,
        email=body.email.lower() if body.email else None,
        phone=body.phone,
        notes=body.notes,
        cv_id=cv_id,
    )
    db.add(candidate)
    await db.flush()

    # Update CV with candidate_id
    if cv_id:
        cv.candidate_id = candidate.id

    # Create audit log
    sha256_hash = hashlib.sha256(raw_blob or b"").hexdigest() if raw_blob else None
    _audit_log(
        db,
        current_user.id,
        "candidate_added",
        candidate.id,
        {"sha256": sha256_hash},
    )

    await db.commit()
    await db.refresh(candidate)

    return CandidateResponse(
        id=candidate.id,
        recruiter_id=candidate.recruiter_id,
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        notes=candidate.notes,
        cv_id=candidate.cv_id,
        last_analysed_at=candidate.last_analysed_at,
        created_at=candidate.created_at,
    )


@router.get("", response_model=CandidateListResponse)
async def list_candidates(
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    current_user: CurrentUser = Depends(check_recruiter_consent),
    db: AsyncSession = Depends(get_db),
):
    """
    List candidates in the recruiter's roster with pagination.
    """
    # Clamp page size
    page_size = min(page_size, MAX_PAGE_SIZE)
    offset = (page - 1) * page_size

    # Count total
    count_result = await db.execute(
        select(func.count()).select_from(RecruiterCandidate).where(
            RecruiterCandidate.recruiter_id == current_user.id
        )
    )
    total = count_result.scalar() or 0

    # Get candidates
    result = await db.execute(
        select(RecruiterCandidate).where(
            RecruiterCandidate.recruiter_id == current_user.id
        ).order_by(RecruiterCandidate.created_at.desc()).offset(offset).limit(page_size)
    )
    candidates = result.scalars().all()

    items = [
        CandidateResponse(
            id=c.id,
            recruiter_id=c.recruiter_id,
            full_name=c.full_name,
            email=c.email,
            phone=c.phone,
            notes=c.notes,
            cv_id=c.cv_id,
            last_analysed_at=c.last_analysed_at,
            created_at=c.created_at,
        )
        for c in candidates
    ]

    return CandidateListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(items)) < total,
    )


@router.get("/ranked", response_model=CandidateRankedResponse)
async def get_ranked_candidates(
    jd_text: str,
    current_user: CurrentUser = Depends(check_recruiter_consent),
    db: AsyncSession = Depends(get_db),
):
    """
    Get candidates ranked by match score × recency decay.

    This endpoint:
    1. Pre-filters top-K by embedding similarity
    2. Applies hybrid scoring: match_score × exp(-days/30)
    3. Applies floor: effective_score >= 0.5 × match_score when match_score >= 0.7
    """
    from app.services.candidate_ranking import rank_candidates

    # Get ranked candidates
    ranked = await rank_candidates(
        recruiter_id=current_user.id,
        jd_text=jd_text,
        db=db,
        top_k=10,
    )

    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(RecruiterCandidate).where(
            RecruiterCandidate.recruiter_id == current_user.id
        )
    )
    total = count_result.scalar() or 0

    items = [
        CandidateResponse(
            id=c.id,
            recruiter_id=c.recruiter_id,
            full_name=c.full_name,
            email=c.email,
            phone=c.phone,
            notes=c.notes,
            cv_id=c.cv_id,
            last_analysed_at=c.last_analysed_at,
            created_at=c.created_at,
        )
        for c, _ in ranked
    ]

    effective_scores = {c.id: score for c, score in ranked}

    return CandidateRankedResponse(
        items=items,
        total=len(items),
        effective_scores=effective_scores,
        total_candidates=total,
        is_truncated=total > 10,
    )


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: int,
    current_user: CurrentUser = Depends(check_recruiter_consent),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a specific candidate by ID.
    """
    result = await db.execute(
        select(RecruiterCandidate).where(
            RecruiterCandidate.id == candidate_id,
            RecruiterCandidate.recruiter_id == current_user.id,
        )
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CANDIDATE_NOT_FOUND"
        )

    return CandidateResponse(
        id=candidate.id,
        recruiter_id=candidate.recruiter_id,
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        notes=candidate.notes,
        cv_id=candidate.cv_id,
        last_analysed_at=candidate.last_analysed_at,
        created_at=candidate.created_at,
    )


@router.patch("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate(
    candidate_id: int,
    body: CandidateUpdate,
    current_user: CurrentUser = Depends(check_recruiter_consent),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a candidate's information.
    """
    result = await db.execute(
        select(RecruiterCandidate).where(
            RecruiterCandidate.id == candidate_id,
            RecruiterCandidate.recruiter_id == current_user.id,
        )
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CANDIDATE_NOT_FOUND"
        )

    # Check for duplicate email if changing
    if body.email and body.email.lower() != candidate.email:
        dup_result = await db.execute(
            select(RecruiterCandidate).where(
                RecruiterCandidate.recruiter_id == current_user.id,
                RecruiterCandidate.email == body.email.lower(),
                RecruiterCandidate.id != candidate_id,
            )
        )
        if dup_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CANDIDATE_DUPLICATED"
            )

    # Update fields
    if body.full_name is not None:
        candidate.full_name = body.full_name
    if body.email is not None:
        candidate.email = body.email.lower()
    if body.phone is not None:
        candidate.phone = body.phone
    if body.notes is not None:
        candidate.notes = body.notes

    # Audit log
    _audit_log(db, current_user.id, "candidate_updated", candidate.id)

    await db.commit()
    await db.refresh(candidate)

    return CandidateResponse(
        id=candidate.id,
        recruiter_id=candidate.recruiter_id,
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        notes=candidate.notes,
        cv_id=candidate.cv_id,
        last_analysed_at=candidate.last_analysed_at,
        created_at=candidate.created_at,
    )


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: int,
    current_user: CurrentUser = Depends(check_recruiter_consent),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a candidate and their CV/analyses.
    """
    result = await db.execute(
        select(RecruiterCandidate).where(
            RecruiterCandidate.id == candidate_id,
            RecruiterCandidate.recruiter_id == current_user.id,
        )
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CANDIDATE_NOT_FOUND"
        )

    # Audit log before deletion
    _audit_log(db, current_user.id, "candidate_deleted", candidate.id)

    # Delete candidate (cascades to CV and analyses)
    await db.delete(candidate)
    await db.commit()


@router.post("/{candidate_id}/match", response_model=CandidateMatchResponse)
async def match_candidate(
    candidate_id: int,
    body: CandidateMatchRequest,
    current_user: CurrentUser = Depends(check_recruiter_consent),
    db: AsyncSession = Depends(get_db),
):
    """
    Run match analysis for a candidate against a job description.

    Tier enforcement: Checks and increments usage counter before running match.
    Returns 402 PLAN_LIMIT_REACHED if user exceeds their plan's match limit.
    """
    # Validate JD length
    if len(body.jd_text) < 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="JD_TOO_SHORT"
        )

    # Tier enforcement: check limit first (read-only), increment only on success
    # This ensures credits are only consumed when the match actually succeeds
    try:
        async with get_session_context() as session:
            await bind_rls_context(session, current_user.id, current_user.role)
            # First check: does user have available quota?
            await check_limit(session, current_user.id, "match", current_user.role)
    except ValueError as e:
        raise HTTPException(
            status_code=402,
            detail="PLAN_LIMIT_REACHED"
        ) from e

    # Get candidate
    result = await db.execute(
        select(RecruiterCandidate).where(
            RecruiterCandidate.id == candidate_id,
            RecruiterCandidate.recruiter_id == current_user.id,
        )
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CANDIDATE_NOT_FOUND"
        )

    # Get CV if exists
    cv_result = await db.execute(
        select(RecruiterCandidateCV).where(
            RecruiterCandidateCV.id == candidate.cv_id
        )
    )
    cv = cv_result.scalar_one_or_none()

    if not cv or not cv.raw_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF_NO_TEXT"
        )

    # Run actual match pipeline using the LLM provider
    # Reuses the same pipeline as POST /v1/match but with candidate CV
    from app.llm.factory import get_llm_provider

    provider = get_llm_provider()

    # Generate match using LLM with candidate CV as profile
    try:
        match_result = await provider.generate_match(
            jd_text=body.jd_text,
            profile_context={
                "id": candidate.id,
                "name": candidate.full_name,
                "headline": f"Candidate CV - {candidate.full_name}",
                "experience": "",
                "skills": "",
                "preferences": "",
                "retrieval_mode": "full",
                "retrieval_context": cv.raw_text,  # Use CV raw text as context
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM match failed: {exc}",
        ) from exc

    analysis = RecruiterAnalysis(
        candidate_id=candidate_id,
        recruiter_id=current_user.id,
        jd_text=body.jd_text,
        score=match_result.score,
        strengths=match_result.strengths,
        gaps=match_result.gaps,
        reasoning=match_result.reasoning,
    )
    db.add(analysis)

    # Update candidate's last_analysed_at
    candidate.last_analysed_at = datetime.now(UTC)

    # Audit log
    _audit_log(db, current_user.id, "candidate_matched", candidate.id)

    await db.commit()
    await db.refresh(analysis)

    # Increment usage counter ONLY after successful match
    # This ensures credits are consumed only for successful matches
    try:
        async with get_session_context() as session:
            await bind_rls_context(session, current_user.id, current_user.role)
            await increment_usage(session, current_user.id, "match")
    except Exception as e:
        # Log but don't fail the request - usage tracking is best-effort
        logger.warning("usage_increment_failed", user_id=current_user.id, error=str(e))

    return CandidateMatchResponse(
        candidate_id=candidate_id,
        score=analysis.score,
        strengths=analysis.strengths,
        gaps=analysis.gaps,
        reasoning=analysis.reasoning,
        created_at=analysis.created_at,
    )
