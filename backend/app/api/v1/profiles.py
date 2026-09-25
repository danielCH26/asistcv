"""CRUD + embedding-status de perfiles (PR-C, task C4).

POST/PATCH generan (o regeneran) el embedding del perfil en el mismo
flujo. GET /v1/profiles/{id}/embedding-status reporta si hay vector
persistido y bajo qué modelo — útil para inspección y para el scenario
"Perfil nuevo genera embedding" del spec semantic-retrieval.

Todos los endpoints viven bajo `/v1` y exigen API key cuando
`BACKEND_API_KEY` está definida (wiring en `main.py`).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db_optional
from app.core.config import get_settings  # noqa: F401  (kept for future thresholds)
from app.core.logging import get_logger
from app.db.models import Profile
from app.llm.factory import get_llm_provider

router = APIRouter(tags=["profiles"])
logger = get_logger("app.api.profiles")


class ProfileCreate(BaseModel):
    """Body de POST /v1/profiles."""

    name: str = Field(min_length=1, max_length=255)
    headline: str | None = Field(default=None, max_length=500)
    experience: dict[str, Any] | None = None
    skills: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None


class ProfilePatch(BaseModel):
    """Body de PATCH /v1/profiles/{id}. Cualquier campo es opcional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    headline: str | None = Field(default=None, max_length=500)
    experience: dict[str, Any] | None = None
    skills: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None


class ProfileOut(BaseModel):
    """Salida estándar de un perfil."""

    id: int
    name: str
    headline: str | None = None
    experience: dict[str, Any] | None = None
    skills: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class EmbeddingStatus(BaseModel):
    """Estado del embedding persistido del perfil."""

    has_embedding: bool
    embedding_model: str | None = None
    last_calculated: datetime | None = None


def _serialize(profile: Profile) -> ProfileOut:
    """Pasa el modelo ORM a Pydantic para la respuesta."""
    return ProfileOut(
        id=cast(int, profile.id),
        name=profile.name,
        headline=profile.headline,
        experience=profile.experience,
        skills=profile.skills,
        preferences=profile.preferences,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


async def _get_profile_or_404(
    session: AsyncSession, profile_id: int
) -> Profile:
    """Lookup helper: 404 si no existe."""
    result = await session.execute(select(Profile).where(Profile.id == profile_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail=f"Profile with id {profile_id} not found",
        )
    return profile


async def _compute_and_persist_embedding(
    session: AsyncSession,
    profile: Profile,
) -> None:
    """Calcula el embedding del perfil y lo persiste en la misma sesión.

    Falla suave: si el provider no responde, registramos warning y el
    match flow hará on-demand re-embedding después (PR-A, task A6).
    """
    provider = get_llm_provider()

    payload = {
        "name": profile.name,
        "headline": profile.headline,
        "experience": profile.experience,
        "skills": profile.skills,
        "preferences": profile.preferences,
    }
    text = json.dumps(payload, ensure_ascii=False, default=str)
    try:
        embedding = await provider.generate_embedding(text)
    except Exception as exc:
        logger.warning(
            "profile_embedding_compute_failed",
            profile_id=profile.id,
            error=str(exc)[:200],
        )
        return

    profile.embedding = list(embedding.vector)
    profile.embedding_model = embedding.model
    profile.updated_at = datetime.now(UTC)
    session.add(profile)
    await session.flush()


@router.post("/profiles", response_model=ProfileOut, status_code=201)
async def create_profile(
    payload: ProfileCreate,
    session: AsyncSession = Depends(get_db_optional),
) -> ProfileOut:
    """Crea un perfil y calcula su embedding inicial.

    El embedding puede fallar silenciosamente (warning log) — el match
    flow lo regenera on-demand (PR-A, A6). El perfil igual queda
    persistido.
    """
    profile = Profile(
        name=payload.name,
        headline=payload.headline,
        experience=payload.experience,
        skills=payload.skills,
        preferences=payload.preferences,
    )
    session.add(profile)
    await session.flush()  # para tener profile.id antes del embedding

    await _compute_and_persist_embedding(session, profile)
    await session.commit()
    await session.refresh(profile)

    return _serialize(profile)


@router.get("/profiles/{profile_id}", response_model=ProfileOut)
async def get_profile(
    profile_id: int,
    session: AsyncSession = Depends(get_db_optional),
) -> ProfileOut:
    """Detalle completo de un perfil. 404 si no existe."""
    profile = await _get_profile_or_404(session, profile_id)
    return _serialize(profile)


@router.patch("/profiles/{profile_id}", response_model=ProfileOut)
async def patch_profile(
    profile_id: int,
    payload: ProfilePatch,
    session: AsyncSession = Depends(get_db_optional),
) -> ProfileOut:
    """Actualiza un perfil. Recalcula embedding si cambió experience/skills.

    Cambios de `name` o `headline` también recalculan el embedding
    porque forman parte del texto serializado que produce el vector.
    """
    profile = await _get_profile_or_404(session, profile_id)

    data = payload.model_dump(exclude_unset=True)
    relevant = {"name", "headline", "experience", "skills", "preferences"}
    fields_changed = bool(set(data.keys()) & relevant)
    for field_name, value in data.items():
        setattr(profile, field_name, value)

    if fields_changed:
        await _compute_and_persist_embedding(session, profile)

    await session.commit()
    await session.refresh(profile)
    return _serialize(profile)


@router.get(
    "/profiles/{profile_id}/embedding-status",
    response_model=EmbeddingStatus,
)
async def get_embedding_status(
    profile_id: int,
    session: AsyncSession = Depends(get_db_optional),
) -> EmbeddingStatus:
    """Inspección barata: ¿hay embedding persistido y bajo qué modelo?"""
    profile = await _get_profile_or_404(session, profile_id)
    return EmbeddingStatus(
        has_embedding=profile.embedding is not None,
        embedding_model=profile.embedding_model,
        last_calculated=profile.updated_at if profile.embedding is not None else None,
    )
