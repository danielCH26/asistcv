"""Endpoints de historial de análisis (GET /v1/analyses).

Los endpoints usan ``get_db_optional``: en modo abierto corren con el
contexto de servicio (visible para MCP/API key) y con JWT el contexto
RLS del usuario — la isolación cross-user la aplica la base de datos
(migración 011): el análisis de otro usuario devuelve 404, nunca 403.
"""
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.api.deps import CurrentUser, get_db_optional, optional_auth
from app.db.models import Analysis, JobDescription

router = APIRouter(tags=["analyses"])

# Tamaño del snippet de raw_text embebido en el detalle.
_SNIPPET_LENGTH = 200


class AnalysisSummary(BaseModel):
    """Ítem del listado de historial."""

    id: int
    profile_id: int | None = None
    job_description_id: int
    score: int | None = None
    created_at: datetime


class JobDescriptionEmbedded(BaseModel):
    """Referencia al JD asociado a un análisis."""

    id: int
    title: str | None = None
    company: str | None = None
    snippet: str


class AnalysisDetail(BaseModel):
    """Detalle completo de un análisis."""

    id: int
    profile_id: int | None = None
    job_description_id: int
    score: int | None = None
    strengths: list[str]
    gaps: list[str]
    energy_level: str | None = None
    reasoning: str | None = None
    created_at: datetime
    job_description: JobDescriptionEmbedded


def _as_str_list(value: Any) -> list[str]:
    """Normaliza el valor JSON de strengths/gaps a lista de strings."""
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _snippet(raw_text: str) -> str:
    """Devuelve un snippet del texto completo del JD."""
    if len(raw_text) <= _SNIPPET_LENGTH:
        return raw_text
    return raw_text[:_SNIPPET_LENGTH] + "…"


@router.get("/analyses", response_model=list[AnalysisSummary])
async def list_analyses(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    profile_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_db_optional),
    user: CurrentUser = Depends(optional_auth),
) -> list[AnalysisSummary]:
    """Lista análisis en orden cronológico inverso, con paginación offset.

    Defense in depth: RLS (migración 011) filtra a nivel BD y, además,
    el servicio agrega el filtro por owner para JWT (el usuario de
    servicio id=0 ve todo, paridad con el modo legacy/MCP).
    """
    query = select(Analysis)
    if user.id != 0:
        query = query.where(Analysis.owner_user_id == user.id)
    if profile_id is not None:
        query = query.where(Analysis.profile_id == profile_id)
    query = query.order_by(col(Analysis.created_at).desc(), col(Analysis.id).desc())
    query = query.offset(offset).limit(limit)

    result = await session.execute(query)
    rows = result.scalars().all()

    return [
        AnalysisSummary(
            id=cast(int, row.id),
            profile_id=row.profile_id,
            job_description_id=row.job_description_id,
            score=row.score,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/analyses/{analysis_id}", response_model=AnalysisDetail)
async def get_analysis(
    analysis_id: int,
    session: AsyncSession = Depends(get_db_optional),
    user: CurrentUser = Depends(optional_auth),
) -> AnalysisDetail:
    """Devuelve el detalle completo de un análisis con su JD embebido.

    El análisis de otro usuario devuelve 404 (nunca 403): la fila no
    visible no revela su existencia (RLS + filtro de servicio).
    """
    query = select(Analysis).where(Analysis.id == analysis_id)
    if user.id != 0:
        query = query.where(Analysis.owner_user_id == user.id)
    result = await session.execute(query)
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=f"Analysis with id {analysis_id} not found",
        )

    jd_result = await session.execute(
        select(JobDescription).where(JobDescription.id == analysis.job_description_id)
    )
    job_description = jd_result.scalar_one_or_none()

    embedded = JobDescriptionEmbedded(
        id=analysis.job_description_id,
        title=job_description.title if job_description else None,
        company=job_description.company if job_description else None,
        snippet=_snippet(job_description.raw_text) if job_description else "",
    )

    return AnalysisDetail(
        id=cast(int, analysis.id),
        profile_id=analysis.profile_id,
        job_description_id=analysis.job_description_id,
        score=analysis.score,
        strengths=_as_str_list(analysis.strengths),
        gaps=_as_str_list(analysis.gaps),
        energy_level=analysis.energy_level,
        reasoning=analysis.reasoning,
        created_at=analysis.created_at,
        job_description=embedded,
    )
