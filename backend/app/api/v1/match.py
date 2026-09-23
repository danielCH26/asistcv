"""
Match endpoint for JD vs profile analysis with transactional persistence.

Flow (design section 5): validate -> JD embedding (HF) -> profile lookup ->
on-demand profile re-embedding -> prompt (full profile; retrieval in PR-C)
-> LLM (Groq) -> parse -> SINGLE transaction (INSERT job_descriptions +
INSERT analyses). If the LLM or the embedding provider fails, nothing is
persisted.
"""
import json

import groq
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Analysis, JobDescription, Profile
from app.db.session import get_session_context
from app.llm.factory import get_llm_provider

router = APIRouter(tags=["match"])
logger = get_logger("app.api.match")

# Longitud mínima del JD (spec match-analysis: "Validación — JD ausente o corto").
MIN_JD_LENGTH = 50


class MatchRequest(BaseModel):
    """Request body for match endpoint."""
    jd_text: str = Field(min_length=MIN_JD_LENGTH)
    profile_id: int


class MatchResponse(BaseModel):
    """Response body for match endpoint."""
    score: int
    strengths: list[str]
    gaps: list[str]
    energy_level: str
    reasoning: str


@router.post("/match", response_model=MatchResponse)
async def match(
    request: MatchRequest,
    http_request: Request,
) -> MatchResponse:
    """
    Analyze match between a job description and a profile.

    All external I/O (HF embeddings, LLM) happens BEFORE opening the write
    transaction so no pooled connection is held during slow calls. The JD and
    the analysis are persisted atomically in a single transaction; if the LLM
    fails, nothing is persisted (a JD without an analysis is noise in
    single-user mode).

    Note: the full profile is used as context. Semantic retrieval over
    fragments arrives in PR-C (issue #16).
    """
    provider = get_llm_provider()

    # Paso 3: embedding del JD (I/O externo, antes de cualquier escritura).
    try:
        jd_embedding = await provider.generate_embedding(request.jd_text)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Embedding provider failed: {exc}",
        ) from exc

    # Paso 4: lookup del perfil en sesión corta (libera la conexión durante
    # las llamadas lentas al LLM).
    async with get_session_context() as session:
        result = await session.execute(
            select(Profile).where(Profile.id == request.profile_id)
        )
        profile = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail=f"Profile with id {request.profile_id} not found",
        )

    profile_context = {
        "id": profile.id,
        "name": profile.name,
        "headline": profile.headline,
        "experience": profile.experience,
        "skills": profile.skills,
        "preferences": profile.preferences,
    }

    # Paso 4b: re-embedding on-demand del perfil (vector NULL o modelo distinto).
    # El embedding del JD histórico nunca se regenera (es snapshot del análisis).
    settings = get_settings()
    profile_embedding = profile.embedding
    profile_embedding_model = profile.embedding_model
    profile_reembedded = False
    if profile_embedding is None or profile_embedding_model != settings.hf_embedding_model:
        try:
            profile_text = json.dumps(profile_context, ensure_ascii=False, default=str)
            profile_emb = await provider.generate_embedding(profile_text)
            profile_embedding = profile_emb.vector
            profile_embedding_model = profile_emb.model
            profile_reembedded = True
            logger.warning(
                "profile_reembedded_on_demand",
                profile_id=request.profile_id,
                embedding_model=profile_embedding_model,
            )
        except Exception as exc:
            # Degradación elegante: el match continúa sin vector de perfil.
            logger.warning(
                "profile_reembedding_skipped",
                profile_id=request.profile_id,
                error=str(exc)[:200],
            )

    # Pasos 5-7: contexto completo + LLM + parse/validación del esquema.
    try:
        analysis = await provider.generate_match(
            jd_text=request.jd_text,
            profile_context=profile_context,
        )
    except groq.RateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail="LLM rate limit exceeded after retries",
        ) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error generating match analysis: {exc}",
        ) from exc

    # Paso 8: transacción única. Si el LLM falló, nunca se llega acá.
    try:
        async with get_session_context() as session:
            jd_row = JobDescription(
                raw_text=request.jd_text,
                embedding=jd_embedding.vector,
                embedding_model=jd_embedding.model,
            )
            session.add(jd_row)
            await session.flush()

            analysis_row = Analysis(
                job_description_id=jd_row.id,
                profile_id=request.profile_id,
                profile_snapshot=profile_context,
                score=analysis.score,
                strengths=analysis.strengths,
                gaps=analysis.gaps,
                energy_level=analysis.energy_level,
                reasoning=analysis.reasoning,
                embedding=jd_embedding.vector,
                embedding_model=jd_embedding.model,
            )
            session.add(analysis_row)

            if profile_reembedded:
                db_profile = await session.get(Profile, request.profile_id)
                if db_profile is not None:
                    db_profile.embedding = profile_embedding
                    db_profile.embedding_model = profile_embedding_model

            await session.commit()
    except SQLAlchemyError:
        request_id = getattr(http_request.state, "request_id", "unknown")
        logger.exception("match_persistence_failed", request_id=request_id)
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable",
        ) from None

    return MatchResponse(
        score=analysis.score,
        strengths=analysis.strengths,
        gaps=analysis.gaps,
        energy_level=analysis.energy_level,
        reasoning=analysis.reasoning,
    )
