"""
Tests de persistencia transaccional del flujo match (PR-A, tasks A5/A6/A8).

Matriz de escenarios del spec match-analysis cubierta acá:
- Happy path persiste JD + análisis en una transacción
- Error del LLM (no-429) → 502 sin persistir
- Rate limit del LLM (429 agotado) → 429 sin persistir
- Falla del proveedor de embeddings → 502 sin persistir
- Error de base de datos → 503 con rollback total
- Re-embedding on-demand del perfil (ausente / modelo distinto / ya vigente)
- Validación JD corto → 422 sin persistir
- Perfil inexistente → 404 sin persistir

Todos usan mocks de proveedores (sin LLM/HF reales) y DB real de test.
"""
from unittest.mock import AsyncMock, MagicMock

import groq
import httpx
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

import app.api.v1.match as match_module
from app.db.models import Analysis, JobDescription, Profile
from app.llm.schemas import Embedding, MatchAnalysis

JD_TEXT = (
    "Buscamos Python developer con 5 años de experiencia en FastAPI, "
    "PostgreSQL y despliegues en AWS. Trabajo remoto, equipo pequeño."
)

EMBEDDING_MODEL = "BAAI/bge-m3"


def _make_provider() -> MagicMock:
    """Proveedor LLM mockeado: embeddings de 1024 + análisis válido."""
    provider = MagicMock(name="LLMProviderMock")
    provider.generate_embedding = AsyncMock(
        return_value=Embedding(
            vector=[0.1] * 1024,
            model=EMBEDDING_MODEL,
            provider="huggingface",
        )
    )
    provider.generate_match = AsyncMock(
        return_value=MatchAnalysis(
            score=85,
            strengths=["Python", "FastAPI"],
            gaps=["Kubernetes"],
            energy_level="high",
            reasoning="Buen match general entre el perfil y el JD.",
        )
    )
    return provider


def _rate_limit_error() -> groq.RateLimitError:
    """Construye un groq.RateLimitError como el que surface el provider."""
    return groq.RateLimitError(
        "Rate limit reached",
        response=httpx.Response(
            429,
            request=httpx.Request("POST", "https://api.groq.com/test"),
        ),
        body=None,
    )


async def _count(clean_db, table: str) -> int:
    """Cantidad de filas de una tabla en el DB de test."""
    async with clean_db.engine.connect() as conn:
        result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
        return result.scalar_one()


async def test_match_happy_path_persists_jd_and_analysis(
    async_client, clean_db, patch_match_db, create_profile, monkeypatch
):
    """Happy path: persiste job_descriptions + analyses con embeddings y FKs."""
    profile = await create_profile(name="Test User")
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 85
    assert data["strengths"] == ["Python", "FastAPI"]
    assert data["gaps"] == ["Kubernetes"]
    assert data["energy_level"] == "high"
    assert data["reasoning"] == "Buen match general entre el perfil y el JD."

    async with clean_db.session_factory() as session:
        jds = (await session.execute(select(JobDescription))).scalars().all()
        analyses = (await session.execute(select(Analysis))).scalars().all()

        assert len(jds) == 1, "el JD debe persistirse exactamente una vez"
        jd = jds[0]
        assert jd.raw_text == JD_TEXT
        assert list(jd.embedding) == [0.1] * 1024
        assert jd.embedding_model == EMBEDDING_MODEL

        assert len(analyses) == 1, "el análisis debe persistirse exactamente una vez"
        row = analyses[0]
        assert row.job_description_id == jd.id, "FK analyses -> job_descriptions"
        assert row.profile_id == profile.id, "FK analyses -> profiles"
        assert row.profile_snapshot["mode"] == "complete"
        assert "Test User" in row.profile_snapshot["context"]
        assert row.profile_snapshot["chunks_used"] is None
        assert row.score == 85
        assert row.strengths == ["Python", "FastAPI"]
        assert row.gaps == ["Kubernetes"]
        assert row.energy_level == "high"
        assert row.reasoning == "Buen match general entre el perfil y el JD."
        assert list(row.embedding) == [0.1] * 1024
        assert row.embedding_model == EMBEDDING_MODEL


async def test_match_llm_error_returns_502_without_persisting(
    async_client, clean_db, patch_match_db, create_profile, monkeypatch
):
    """Error del LLM no-429 → 502 y ninguna fila persistida."""
    profile = await create_profile(name="Test User")
    provider = _make_provider()
    provider.generate_match = AsyncMock(side_effect=ValueError("LLM exploded"))
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 502
    assert await _count(clean_db, "job_descriptions") == 0
    assert await _count(clean_db, "analyses") == 0


async def test_match_llm_rate_limit_returns_429_without_persisting(
    async_client, clean_db, patch_match_db, create_profile, monkeypatch
):
    """429 agotado del LLM → 429 y ninguna fila persistida."""
    profile = await create_profile(name="Test User")
    provider = _make_provider()
    provider.generate_match = AsyncMock(side_effect=_rate_limit_error())
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 429
    assert await _count(clean_db, "job_descriptions") == 0
    assert await _count(clean_db, "analyses") == 0


async def test_match_embedding_failure_returns_502_without_persisting(
    async_client, clean_db, patch_match_db, create_profile, monkeypatch
):
    """Falla de HF al embeber el JD → 502 sin persistir JD ni análisis."""
    profile = await create_profile(name="Test User")
    provider = _make_provider()
    provider.generate_embedding = AsyncMock(
        side_effect=RuntimeError("HF API call failed after 4 attempts")
    )
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 502
    assert await _count(clean_db, "job_descriptions") == 0
    assert await _count(clean_db, "analyses") == 0


async def test_match_db_failure_returns_503_and_rolls_back(
    async_client, clean_db, patch_match_db, create_profile, monkeypatch
):
    """Error de escritura → 503 y rollback total (ni JD ni análisis)."""
    profile = await create_profile(name="Test User")
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)
    monkeypatch.setattr(
        AsyncSession,
        "flush",
        AsyncMock(
            side_effect=OperationalError("INSERT INTO job_descriptions", {}, Exception("db down"))
        ),
    )

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 503
    assert await _count(clean_db, "job_descriptions") == 0
    assert await _count(clean_db, "analyses") == 0


async def test_match_regenerates_missing_profile_embedding(
    async_client, clean_db, patch_match_db, create_profile, monkeypatch
):
    """Perfil sin embedding → se regenera on-demand y persiste (task A6)."""
    profile = await create_profile(name="Perfil Nuevo")
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 200
    assert provider.generate_embedding.await_count == 2, (
        "debe embeber JD + perfil (re-embedding on-demand)"
    )

    async with clean_db.session_factory() as session:
        stored = await session.get(Profile, profile.id)
        assert stored.embedding is not None
        assert len(list(stored.embedding)) == 1024
        assert stored.embedding_model == EMBEDDING_MODEL


async def test_match_skips_reembed_when_model_matches(
    async_client, clean_db, patch_match_db, create_profile, monkeypatch
):
    """Perfil con embedding vigente → NO se re-embebe (solo se embebe el JD)."""
    profile = await create_profile(
        name="Perfil Completo", embedding=[0.5] * 1024, embedding_model=EMBEDDING_MODEL
    )
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 200
    assert provider.generate_embedding.await_count == 1, "solo el JD debe embeberse"

    async with clean_db.session_factory() as session:
        stored = await session.get(Profile, profile.id)
        assert list(stored.embedding) == [0.5] * 1024, "el embedding no debe cambiar"
        assert stored.embedding_model == EMBEDDING_MODEL


async def test_match_regenerates_when_embedding_model_differs(
    async_client, clean_db, patch_match_db, create_profile, monkeypatch
):
    """Perfil con modelo de embedding viejo → regenera y persiste el nuevo."""
    profile = await create_profile(
        name="Perfil Legacy", embedding=[0.3] * 1024, embedding_model="old-model-v1"
    )
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 200
    assert provider.generate_embedding.await_count == 2

    async with clean_db.session_factory() as session:
        stored = await session.get(Profile, profile.id)
        assert stored.embedding_model == EMBEDDING_MODEL
        assert list(stored.embedding) == [0.1] * 1024


async def test_match_profile_reembed_failure_continues(
    async_client, clean_db, patch_match_db, create_profile, monkeypatch
):
    """Si falla el re-embedding del perfil, el match continúa sin bloquearse."""
    profile = await create_profile(name="Perfil Nuevo")
    provider = _make_provider()
    provider.generate_embedding = AsyncMock(
        side_effect=[
            Embedding(vector=[0.1] * 1024, model=EMBEDDING_MODEL, provider="huggingface"),
            RuntimeError("HF down al embeber el perfil"),
        ]
    )
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 200, "el match no debe fallar por el re-embedding"

    async with clean_db.session_factory() as session:
        stored = await session.get(Profile, profile.id)
        assert stored.embedding is None, "el perfil queda sin vector, sin romper el flujo"

    assert await _count(clean_db, "job_descriptions") == 1
    assert await _count(clean_db, "analyses") == 1


async def test_match_short_jd_returns_422_without_persisting(
    async_client, clean_db, patch_match_db, create_profile, monkeypatch
):
    """JD < 50 caracteres → 422 y ningún proveedor invocado ni fila escrita."""
    profile = await create_profile(name="Test User")
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": "JD demasiado corto", "profile_id": profile.id}
    )

    assert response.status_code == 422
    assert provider.generate_embedding.await_count == 0
    assert provider.generate_match.await_count == 0
    assert await _count(clean_db, "job_descriptions") == 0
    assert await _count(clean_db, "analyses") == 0


async def test_match_missing_profile_returns_404_without_persisting(
    async_client, clean_db, patch_match_db, monkeypatch
):
    """Perfil inexistente → 404 y ninguna fila persistida."""
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": 99999}
    )

    assert response.status_code == 404
    assert "99999" in response.json()["detail"]
    assert await _count(clean_db, "job_descriptions") == 0
    assert await _count(clean_db, "analyses") == 0
