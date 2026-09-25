"""
CV management endpoints: upload, list, get, update, delete.

All endpoints require JWT authentication and enforce owner-only access.
"""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db
from app.core.logging import get_logger
from app.db.models import UserCV
from app.llm.factory import get_llm_provider
from app.schemas.cv import (
    CVCreateRequest,
    CVDetailResponse,
    CVResponse,
    CVUpdateRequest,
    CVUploadResponse,
)
from app.services import pdf_parser

logger = get_logger(__name__)

router = APIRouter(prefix="/cvs", tags=["cvs"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


async def get_current_user_required(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Ensure user is authenticated with JWT, not API key."""
    if current_user.auth_method == "api_key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ROLE_FORBIDDEN"
        )
    return current_user


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CVUploadResponse)
async def upload_cv(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """Upload a PDF CV.

    Accepts multipart file upload with PDF content.
    - Content-Type must be application/pdf (415 if not)
    - File size must be <= 10MB (413 if exceeded)
    - Must contain extractable text (422 PDF_NO_TEXT if not)
    """
    # Validate content type
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="UNSUPPORTED_MEDIA_TYPE"
        )

    # Read file content
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {str(e)}"
        )

    # Check file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="FILE_TOO_LARGE"
        )

    # Parse PDF - distinguish no-text from parse failure
    try:
        parsed = pdf_parser.parse_pdf(content)
    except pdf_parser.PDFNoTextError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF_NO_TEXT"
        )
    except pdf_parser.PDFParseError as e:
        # Log OOM incidents with stack trace and tentative cv_id
        logger.exception(
            "pdf_parse_failed",
            cv_id_tentative=e.cv_id_tentative,
            error=str(e)[:200],
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PDF_PARSE_FAILED"
        )

    # Store file (optional for now - we store raw_blob in DB)
    # file_path = cv_storage.store_cv(current_user.id, file.filename, content)

    # Create CV record
    cv = UserCV(
        owner_user_id=current_user.id,
        original_filename=file.filename or "cv.pdf",
        detected_locale=parsed.detected_locale,
        raw_blob=content,
        raw_text=parsed.raw_text,
        structured=parsed.structured,
    )

    db.add(cv)
    await db.commit()
    await db.refresh(cv)

    return CVUploadResponse(
        cv_id=cv.id,
        original_filename=cv.original_filename,
        detected_locale=cv.detected_locale or "es",
        structured=cv.structured,
    )


@router.post("/structured", status_code=status.HTTP_201_CREATED, response_model=CVUploadResponse)
async def create_structured_cv(
    request: CVCreateRequest,
    current_user: CurrentUser = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """Create a CV from structured editor data.

    Accepts JSON body with structured CV data instead of PDF.
    """
    # Create CV record with structured data
    cv = UserCV(
        owner_user_id=current_user.id,
        original_filename=request.original_filename,
        detected_locale="es",  # Default, could be from user profile
        raw_text=None,
        raw_blob=None,
        structured=request.structured.model_dump(),
    )

    db.add(cv)
    await db.commit()
    await db.refresh(cv)

    return CVUploadResponse(
        cv_id=cv.id,
        original_filename=cv.original_filename,
        detected_locale=cv.detected_locale or "es",
        structured=cv.structured,
    )


@router.get("", response_model=list[CVResponse])
async def list_cvs(
    current_user: CurrentUser = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """List all CVs for the current user."""
    result = await db.execute(
        select(UserCV)
        .where(UserCV.owner_user_id == current_user.id)
        .order_by(UserCV.created_at.desc())
    )
    cvs = result.scalars().all()

    return cvs


@router.get("/{cv_id}", response_model=CVDetailResponse)
async def get_cv(
    cv_id: int,
    current_user: CurrentUser = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific CV by ID.

    Returns 404 if CV doesn't exist or belongs to another user.
    """
    result = await db.execute(
        select(UserCV).where(
            UserCV.id == cv_id,
            UserCV.owner_user_id == current_user.id
        )
    )
    cv = result.scalar_one_or_none()

    if not cv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CV_NOT_FOUND"
        )

    return cv


async def recalc_embedding(cv: UserCV, db: AsyncSession) -> None:
    """Recalculate embedding from CV text.

    Used when CV content changes (PATCH).
    """
    if not cv.raw_text:
        return  # No text to embed

    try:
        provider = get_llm_provider()
        # Build text from structured data + raw_text
        text = cv.raw_text
        if cv.structured:
            # Include key structured fields for better embedding
            struct = cv.structured
            payload = {
                "name": struct.get("full_name", ""),
                "skills": ", ".join(struct.get("skills", [])),
                "experience": str(struct.get("experience", "")),
            }
            text = f"{payload['name']} {payload['skills']} {payload['experience']} {cv.raw_text}"

        embedding = await provider.generate_embedding(text)
        cv.embedding = list(embedding.vector)
        cv.embedding_model = embedding.model
    except Exception as e:
        logger.warning(
            "cv_embedding_recalc_failed",
            cv_id=cv.id,
            error=str(e)[:200],
        )


@router.patch("/{cv_id}", response_model=CVDetailResponse)
async def update_cv(
    cv_id: int,
    request: CVUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """Update CV structured data.

    Updates the structured data and marks last_edited_at.
    Recalculates embedding if text content changed (R3).
    """
    result = await db.execute(
        select(UserCV).where(
            UserCV.id == cv_id,
            UserCV.owner_user_id == current_user.id
        )
    )
    cv = result.scalar_one_or_none()

    if not cv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CV_NOT_FOUND"
        )

    # Update structured data
    cv.structured = request.structured.model_dump()
    cv.last_edited_at = datetime.now(UTC)

    # Recalculate embedding when CV content changes (R3)
    await recalc_embedding(cv, db)

    await db.commit()
    await db.refresh(cv)

    return cv


@router.delete("/{cv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cv(
    cv_id: int,
    current_user: CurrentUser = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """Delete a CV.

    Returns 204 on success, 404 if CV doesn't exist or belongs to another user.
    """
    result = await db.execute(
        select(UserCV).where(
            UserCV.id == cv_id,
            UserCV.owner_user_id == current_user.id
        )
    )
    cv = result.scalar_one_or_none()

    if not cv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CV_NOT_FOUND"
        )

    # Delete stored file if exists
    # if cv.file_path:
    #     cv_storage.delete_cv(cv.file_path)

    await db.delete(cv)
    await db.commit()

    return None
