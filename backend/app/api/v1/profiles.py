"""CRUD + embedding-status de perfiles (PR-C, task C4).

POST/PATCH generan (o regeneran) el embedding del perfil en el mismo
flujo. GET /v1/profiles/{id}/embedding-status reporta si hay vector
persistido y bajo qué modelo — útil para inspección y para el scenario
"Perfil nuevo genera embedding" del spec semantic-retrieval.

Todos los endpoints viven bajo `/v1` y exigen API key cuando
`BACKEND_API_KEY` está definida (wiring en `main.py`).

Ownership (issue #85)
---------------------
`profiles` NO tiene RLS (la migración 011 no la cubrió: `relrowsecurity =
false`), así que el aislamiento entre usuarios es 100% explícito en esta
capa. Para un principal real el predicado es
``Profile.owner_user_id == <principal.id>``; un perfil ajeno es 404, nunca
403, para no revelar existencia.

El usuario de servicio (id 0, API key) conserva la lectura sin filtro, por
paridad con `analyses.py` y con el modo single-user del MCP adapter. Esa
es una decisión deliberada, no un descuido: la API key es una credencial
compartida y tratarla como "root de lectura" es el contrato que ya tienen
`analyses`, `job_descriptions` y `users_cvs`. Lo que este módulo cierra es
el IDOR entre USUARIOS autenticados, que es el agujero reportado.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import (
    CurrentUser,
    get_current_user_required,
    get_db,
    get_db_optional,
    optional_auth,
)
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
    session: AsyncSession, profile_id: int, user: CurrentUser
) -> Profile:
    """Lookup helper acotado al owner: 404 si no existe o no es del caller.

    El filtro de ownership va ACÁ y no en RLS porque `profiles` no tiene
    policies (migración 011 no la cubrió). Para el principal de servicio
    (id 0) el filtro se omite: ver la nota de ownership en el módulo.
    """
    query = select(Profile).where(Profile.id == profile_id)
    if user.id != 0:
        query = query.where(Profile.owner_user_id == user.id)
    result = await session.execute(query)
    profile = result.scalar_one_or_none()
    if profile is None:
        # 404 y no 403: un 403 confirmaría que el id existe.
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
    session: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user_required),
) -> ProfileOut:
    """Crea un perfil y calcula su embedding inicial.

    El embedding puede fallar silenciosamente (warning log) — el match
    flow lo regenera on-demand (PR-A, A6). El perfil igual queda
    persistido.

    Ownership (issue #85): exige un principal JWT REAL y estampa
    `owner_user_id`. `optional_auth` no sirve para esta decisión porque en
    modo abierto fabrica el usuario de servicio (id 0) — estampar 0
    rompería el FK `fk_profiles_owner_user_id_users` (no existe un
    usuario 0) y dejarlo NULL crearía una fila huérfana que el filtro de
    lectura después oculta a todos. `get_current_user_required` ya existe
    exactamente para esto: rechaza la API key con 403 y exige credenciales
    (401) aunque el despliegue esté en modo abierto.
    """
    profile = Profile(
        name=payload.name,
        headline=payload.headline,
        experience=payload.experience,
        skills=payload.skills,
        preferences=payload.preferences,
        owner_user_id=user.id,
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
    user: CurrentUser = Depends(optional_auth),
) -> ProfileOut:
    """Detalle completo de un perfil. 404 si no existe o es de otro usuario."""
    profile = await _get_profile_or_404(session, profile_id, user)
    return _serialize(profile)


@router.patch("/profiles/{profile_id}", response_model=ProfileOut)
async def patch_profile(
    profile_id: int,
    payload: ProfilePatch,
    session: AsyncSession = Depends(get_db_optional),
    user: CurrentUser = Depends(optional_auth),
) -> ProfileOut:
    """Actualiza un perfil. Recalcula embedding si cambió experience/skills.

    Cambios de `name` o `headline` también recalculan el embedding
    porque forman parte del texto serializado que produce el vector.

    El write está acotado por el mismo lookup que el read: sin ownership
    no se toca la fila, así que un PATCH cross-user no puede mutar nada.
    """
    profile = await _get_profile_or_404(session, profile_id, user)

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
    user: CurrentUser = Depends(optional_auth),
) -> EmbeddingStatus:
    """Inspección barata: ¿hay embedding persistido y bajo qué modelo?"""
    profile = await _get_profile_or_404(session, profile_id, user)
    return EmbeddingStatus(
        has_embedding=profile.embedding is not None,
        embedding_model=profile.embedding_model,
        last_calculated=profile.updated_at if profile.embedding is not None else None,
    )
