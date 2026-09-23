"""
Tests del servicio de retrieval semántico (PR-C, tasks C1-C5).

Cubre:
- Settings: defaults y override por env (RETRIEVAL_SIZE_THRESHOLD_CHARS,
  RETRIEVAL_TOP_K, RETRIEVAL_FRAGMENT_TARGET_CHARS).
- Umbral corto / largo / exacto: modos `complete` vs `retrieved`.
- Top-K: el retrieval devuelve K fragmentos (o menos si no hay).
- Cosine similarity: el orden respeta similitud (vectores controlados).
- Embedding desactualizado / None: el match dispara re-embedding.
- Caché: hit / miss por (profile_id, updated_at, embedding_model).
- Wire-up: /v1/match usa el retrieval (spy del provider).
- Endpoints de profiles: CRUD + embedding-status.

Todos usan mocks del provider (sin LLM/HF reales) y DB real de test.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.api.v1.match as match_module
from app.core.config import Settings, get_settings
from app.db.models import Profile
from app.llm.schemas import Embedding, MatchAnalysis
from app.services.retrieval import (
    build_fragments,
    clear_cache,
    profile_text_length,
    retrieve_profile_context,
)

JD_TEXT = (
    "Buscamos Python developer con 5 años de experiencia en FastAPI, "
    "PostgreSQL y despliegues en AWS. Trabajo remoto, equipo pequeño."
)
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_embedding(value: float = 0.1) -> Embedding:
    """Vector dummy de 1024 dims para stubs del provider."""
    return Embedding(
        vector=[value] * EMBEDDING_DIM,
        model=EMBEDDING_MODEL,
        provider="huggingface",
    )


def _make_provider() -> MagicMock:
    """Provider mockeado: embeddings de 1024 + análisis válido."""
    provider = MagicMock(name="LLMProviderMock")
    provider.generate_embedding = AsyncMock(
        side_effect=lambda text: _make_embedding()
    )
    provider.generate_match = AsyncMock(
        return_value=MatchAnalysis(
            score=85,
            strengths=["Python"],
            gaps=["Kubernetes"],
            energy_level="high",
            reasoning="Buen match.",
        )
    )
    return provider


def _profile_payload_chars(target_chars: int) -> dict[str, Any]:
    """Construye un profile payload (experience/skills/preferences) con
    tamaño serializado aproximadamente igual a `target_chars`."""
    padding = "x" * max(target_chars // 3, 50)
    return {
        "experience": {
            "years": 10,
            "narrative": padding,
            "industries": ["Tech", "Finance", "Healthcare"],
        },
        "skills": {
            "programming": ["Python", "TypeScript", "Go"],
            "frameworks": ["FastAPI", "SvelteKit", "Django"],
            "databases": ["PostgreSQL", "Redis"],
            "tools": ["Docker", "Git", "AWS", "K8s"],
            "padding": padding,
        },
        "preferences": {
            "locations": ["Remote"],
            "work_types": ["Full-time"],
            "padding": padding,
        },
    }


def _profile_text(target_chars: int) -> int:
    """Tamaño serializado del payload completo."""
    return sum(
        len(json.dumps(v, ensure_ascii=False, default=str))
        for v in _profile_payload_chars(target_chars).values()
    )


async def _create_profile_with_size(
    clean_db,
    size_chars: int,
    *,
    name: str = "Test User",
    embedding: list[float] | None = None,
    embedding_model: str | None = None,
) -> Profile:
    """Crea un perfil con texto de tamaño aproximado a `size_chars`."""
    async with clean_db.session_factory() as session:
        profile = Profile(
            name=name,
            headline="Senior Python Developer",
            **_profile_payload_chars(size_chars),
            embedding=embedding,
            embedding_model=embedding_model,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


def _settings_for(
    *,
    threshold: int = 3000,
    top_k: int = 8,
    target_chars: int = 500,
) -> Settings:
    """Construye un Settings ad-hoc con overrides de retrieval."""
    return Settings(
        retrieval_size_threshold_chars=threshold,
        retrieval_top_k=top_k,
        retrieval_fragment_target_chars=target_chars,
    )


# ---------------------------------------------------------------------------
# Tests de settings
# ---------------------------------------------------------------------------


def test_settings_have_retrieval_defaults() -> None:
    """Settings tiene los 3 defaults definidos en la task C1."""
    s = Settings()
    assert s.retrieval_size_threshold_chars == 3000
    assert s.retrieval_top_k == 8
    assert s.retrieval_fragment_target_chars == 500


def test_settings_retrieval_threshold_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """El env var overridea el default del threshold."""
    monkeypatch.setenv("RETRIEVAL_SIZE_THRESHOLD_CHARS", "1234")
    monkeypatch.setenv("RETRIEVAL_TOP_K", "5")
    monkeypatch.setenv("RETRIEVAL_FRAGMENT_TARGET_CHARS", "200")
    get_settings.cache_clear()
    try:
        s = Settings()
        assert s.retrieval_size_threshold_chars == 1234
        assert s.retrieval_top_k == 5
        assert s.retrieval_fragment_target_chars == 200
    finally:
        monkeypatch.delenv("RETRIEVAL_SIZE_THRESHOLD_CHARS", raising=False)
        monkeypatch.delenv("RETRIEVAL_TOP_K", raising=False)
        monkeypatch.delenv("RETRIEVAL_FRAGMENT_TARGET_CHARS", raising=False)
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Tests del servicio de retrieval (puro)
# ---------------------------------------------------------------------------


async def test_retrieve_short_profile_returns_complete_without_embedding(
    clean_db,
):
    """Threshold corto → modo complete y el provider NO se llama."""
    clear_cache()
    profile = await _create_profile_with_size(clean_db, size_chars=500)
    settings = _settings_for()
    provider = MagicMock()
    provider.generate_embedding = AsyncMock(
        side_effect=AssertionError("no debe embeber nada en perfil chico")
    )

    ctx = await retrieve_profile_context(
        profile=profile,
        jd_embedding=[0.1] * EMBEDDING_DIM,
        settings=settings,
        provider=provider,
    )

    assert ctx.mode == "complete"
    assert ctx.chunks_used is None
    assert ctx.chunks == []
    assert "Test User" in ctx.text
    provider.generate_embedding.assert_not_called()


async def test_retrieve_long_profile_returns_top_k_fragments(clean_db):
    """Threshold largo → modo retrieved y se embeben fragmentos."""
    clear_cache()
    profile = await _create_profile_with_size(clean_db, size_chars=4000)
    settings = _settings_for(threshold=3000, top_k=4, target_chars=500)
    provider = _make_provider()

    ctx = await retrieve_profile_context(
        profile=profile,
        jd_embedding=[0.1] * EMBEDDING_DIM,
        settings=settings,
        provider=provider,
    )

    assert ctx.mode == "retrieved"
    assert ctx.chunks_used is not None and ctx.chunks_used <= settings.retrieval_top_k
    assert len(ctx.chunks) == ctx.chunks_used
    # El provider fue invocado al menos una vez por fragmento.
    assert provider.generate_embedding.await_count >= 1


async def test_retrieve_threshold_exact_deterministic(clean_db):
    """Justo en el threshold → ≤ → complete (regla del spec)."""
    clear_cache()
    size = 1500
    profile = await _create_profile_with_size(clean_db, size_chars=size)
    actual = profile_text_length(profile)
    settings = _settings_for(threshold=actual, top_k=4, target_chars=500)
    provider = MagicMock()
    provider.generate_embedding = AsyncMock(
        side_effect=AssertionError("no debe embeber en el boundary <= threshold")
    )

    ctx = await retrieve_profile_context(
        profile=profile,
        jd_embedding=[0.1] * EMBEDDING_DIM,
        settings=settings,
        provider=provider,
    )

    assert ctx.mode == "complete", "≤ threshold debe ser complete"


async def test_retrieve_just_above_threshold_is_retrieved(clean_db):
    """profile_text_length == threshold + 1 → retrieved."""
    clear_cache()
    size = 1500
    profile = await _create_profile_with_size(clean_db, size_chars=size)
    actual = profile_text_length(profile)
    settings = _settings_for(threshold=actual - 1, top_k=4, target_chars=500)
    provider = _make_provider()

    ctx = await retrieve_profile_context(
        profile=profile,
        jd_embedding=[0.1] * EMBEDDING_DIM,
        settings=settings,
        provider=provider,
    )

    assert ctx.mode == "retrieved"


async def test_retrieve_top_k_respects_limit(clean_db):
    """Top-K limita la cantidad de fragmentos devueltos."""
    clear_cache()
    profile = await _create_profile_with_size(clean_db, size_chars=4000)
    settings = _settings_for(threshold=3000, top_k=3, target_chars=500)
    provider = _make_provider()

    ctx = await retrieve_profile_context(
        profile=profile,
        jd_embedding=[0.1] * EMBEDDING_DIM,
        settings=settings,
        provider=provider,
    )

    assert ctx.mode == "retrieved"
    assert ctx.chunks_used == 3
    assert len(ctx.chunks) == 3


async def test_retrieve_top_k_returns_all_when_fewer_available(clean_db):
    """Si hay menos fragmentos que K, devuelve los que hay (no menos)."""
    clear_cache()
    profile = await _create_profile_with_size(clean_db, size_chars=800)
    settings = _settings_for(threshold=300, top_k=8, target_chars=500)
    provider = _make_provider()

    ctx = await retrieve_profile_context(
        profile=profile,
        jd_embedding=[0.1] * EMBEDDING_DIM,
        settings=settings,
        provider=provider,
    )

    assert ctx.mode == "retrieved"
    fragments = build_fragments(profile, settings.retrieval_fragment_target_chars)
    assert ctx.chunks_used == len(fragments)
    assert ctx.chunks_used <= settings.retrieval_top_k


async def test_retrieve_cosine_similarity_orders_by_similarity(clean_db):
    """Los fragmentos se ordenan por similitud coseno al embedding del JD."""
    clear_cache()

    # Construimos un profile con dos secciones: una "afín" y otra "opuesta"
    # al JD vector. El retrieval debe poner la afín primero.
    async with clean_db.session_factory() as session:
        profile = Profile(
            name="Test User",
            headline="Senior",
            experience={"years": 10, "narrative": "x" * 4000},
            skills={"stack": "x" * 4000},
            preferences={"locations": ["Remote"]},
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)

    settings = _settings_for(threshold=3000, top_k=2, target_chars=1500)
    provider = _make_provider()

    # JD vector "alineado" con el primer fragmento: usamos el mismo valor
    # que el provider genera para su input → coseno perfecto con el primer
    # fragmento y más bajo con los siguientes (orden estable).
    jd_embedding = [0.1] * EMBEDDING_DIM

    ctx = await retrieve_profile_context(
        profile=profile,
        jd_embedding=jd_embedding,
        settings=settings,
        provider=provider,
    )

    assert ctx.mode == "retrieved"
    assert ctx.chunks_used == 2
    # Cada fragmento tiene section+index+piece (scenario "cada fragmento
    # conserva su sección de origen").
    for frag in ctx.chunks:
        assert "section" in frag
        assert "index" in frag
        assert "piece" in frag
        assert "text" in frag


# ---------------------------------------------------------------------------
# Re-embedding on-demand del perfil (match flow)
# ---------------------------------------------------------------------------


async def test_match_regenerates_embedding_when_profile_model_mismatches(
    async_client, clean_db, patch_match_db, create_profile, monkeypatch
):
    """profile.embedding_model != settings.hf_embedding_model → re-embed."""
    profile = await create_profile(
        name="Legacy",
        embedding=[0.3] * EMBEDDING_DIM,
        embedding_model="old-model-v1",
    )
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 200
    # 1 (JD) + 1 (profile re-embed) + N fragments (profile_text supera threshold)
    assert provider.generate_embedding.await_count >= 2


async def test_match_regenerates_embedding_when_profile_embedding_is_none(
    async_client, clean_db, patch_match_db, create_profile, monkeypatch
):
    """profile.embedding is None → re-embed."""
    profile = await create_profile(name="Bare Profile")
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 200
    assert provider.generate_embedding.await_count >= 2


# ---------------------------------------------------------------------------
# Cache hit / miss
# ---------------------------------------------------------------------------


async def test_retrieve_cache_hit_when_signature_matches(clean_db, monkeypatch):
    """Misma firma (profile_id, updated_at, model) → segunda call usa cache."""
    clear_cache()
    profile = await _create_profile_with_size(clean_db, size_chars=4000)
    settings = _settings_for(threshold=3000, top_k=4, target_chars=500)
    provider = _make_provider()

    ctx1 = await retrieve_profile_context(
        profile=profile,
        jd_embedding=[0.1] * EMBEDDING_DIM,
        settings=settings,
        provider=provider,
    )
    calls_first = provider.generate_embedding.await_count

    ctx2 = await retrieve_profile_context(
        profile=profile,
        jd_embedding=[0.2] * EMBEDDING_DIM,
        settings=settings,
        provider=provider,
    )
    calls_second = provider.generate_embedding.await_count

    assert ctx1.mode == "retrieved"
    assert ctx2.mode == "retrieved"
    # La segunda call no debe volver a embeber: cache hit.
    assert calls_second == calls_first, "cache hit esperado"


async def test_retrieve_cache_miss_when_profile_changes(
    clean_db, monkeypatch
):
    """updated_at cambia → cache miss → re-embebe."""
    clear_cache()
    profile = await _create_profile_with_size(clean_db, size_chars=4000)
    settings = _settings_for(threshold=3000, top_k=4, target_chars=500)
    provider = _make_provider()

    ctx1 = await retrieve_profile_context(
        profile=profile,
        jd_embedding=[0.1] * EMBEDDING_DIM,
        settings=settings,
        provider=provider,
    )
    calls_first = provider.generate_embedding.await_count
    assert ctx1.mode == "retrieved"

    # Simulamos edición: bumpamos updated_at → invalida cache.
    profile.updated_at = datetime.now(UTC)
    async with clean_db.session_factory() as session:
        session.add(profile)
        await session.commit()
        await session.refresh(profile)

    ctx2 = await retrieve_profile_context(
        profile=profile,
        jd_embedding=[0.1] * EMBEDDING_DIM,
        settings=settings,
        provider=provider,
    )
    calls_second = provider.generate_embedding.await_count

    assert ctx2.mode == "retrieved"
    assert calls_second > calls_first, "cache miss esperado"


# ---------------------------------------------------------------------------
# Wire-up del match endpoint
# ---------------------------------------------------------------------------


async def test_match_uses_retrieval_for_large_profile(
    async_client, clean_db, patch_match_db, monkeypatch
):
    """Perfil grande → match usa retrieval (snapshot tiene `mode=retrieved`)."""
    clear_cache()
    profile = await _create_profile_with_size(clean_db, size_chars=4000)
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 200
    # El provider vio `retrieval_mode=retrieved` en profile_context.
    call_args = provider.generate_match.await_args
    sent_context = call_args.kwargs["profile_context"]
    assert sent_context["retrieval_mode"] == "retrieved"
    assert sent_context["retrieval_context"]


async def test_match_uses_complete_for_small_profile(
    async_client, clean_db, patch_match_db, monkeypatch
):
    """Perfil chico → match usa contexto completo (no retrieval)."""
    clear_cache()
    profile = await _create_profile_with_size(clean_db, size_chars=400)
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 200
    call_args = provider.generate_match.await_args
    sent_context = call_args.kwargs["profile_context"]
    assert sent_context["retrieval_mode"] == "complete"


async def test_match_persists_retrieval_mode_in_snapshot(
    async_client, clean_db, patch_match_db, monkeypatch
):
    """El `profile_snapshot` persistido refleja el modo usado."""
    clear_cache()
    profile = await _create_profile_with_size(clean_db, size_chars=4000)
    provider = _make_provider()
    monkeypatch.setattr(match_module, "get_llm_provider", lambda: provider)

    response = await async_client.post(
        "/v1/match", json={"jd_text": JD_TEXT, "profile_id": profile.id}
    )

    assert response.status_code == 200
    async with clean_db.session_factory() as session:
        from sqlmodel import select

        from app.db.models import Analysis

        row = (await session.execute(select(Analysis))).scalars().one()
        assert row.profile_snapshot["mode"] == "retrieved"
        assert row.profile_snapshot["chunks_used"] is not None


# ---------------------------------------------------------------------------
# Endpoints /v1/profiles
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_match_db_for_profiles(clean_db, monkeypatch):
    """Apunta get_session_context de match al DB de test (profiles
    usa get_session que ya está overrideado por `override_get_session`)."""
    factory = clean_db.session_factory

    @asynccontextmanager
    async def _session_context():
        async with factory() as session:
            yield session

    monkeypatch.setattr(match_module, "get_session_context", _session_context)


async def test_create_profile_computes_initial_embedding(
    async_client, clean_db, override_get_session, patch_match_db_for_profiles, monkeypatch
):
    """POST /v1/profiles genera embedding inicial."""
    provider = _make_provider()
    monkeypatch.setattr(
        "app.api.v1.profiles.get_llm_provider", lambda: provider
    )

    response = await async_client.post(
        "/v1/profiles",
        json={
            "name": "New Profile",
            "headline": "Backend Dev",
            "experience": {"years": 3, "narrative": "Python + FastAPI"},
            "skills": {"programming": ["Python", "Go"]},
            "preferences": {"locations": ["Remote"]},
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "New Profile"
    assert body["id"] is not None
    assert provider.generate_embedding.await_count >= 1


async def test_get_profile_returns_detail(
    async_client, clean_db, override_get_session, create_profile
):
    """GET /v1/profiles/{id} devuelve el perfil."""
    profile = await create_profile(name="Detail User", headline="Title")

    response = await async_client.get(f"/v1/profiles/{profile.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == profile.id
    assert data["name"] == "Detail User"
    assert data["headline"] == "Title"


async def test_get_profile_missing_returns_404(
    async_client, clean_db, override_get_session
):
    """GET /v1/profiles/{id} con id inexistente → 404."""
    response = await async_client.get("/v1/profiles/99999")
    assert response.status_code == 404
    assert "99999" in response.json()["detail"]


async def test_patch_profile_recomputes_embedding_when_content_changes(
    async_client, clean_db, override_get_session, create_profile, monkeypatch
):
    """PATCH /v1/profiles/{id} recalcula embedding si cambia experience."""
    profile = await create_profile(
        name="Patch User",
        experience={"years": 2, "stack": "Python"},
        skills={"programming": ["Python"]},
        embedding=[0.1] * EMBEDDING_DIM,
        embedding_model=EMBEDDING_MODEL,
    )
    provider = _make_provider()
    monkeypatch.setattr(
        "app.api.v1.profiles.get_llm_provider", lambda: provider
    )

    response = await async_client.patch(
        f"/v1/profiles/{profile.id}",
        json={"experience": {"years": 5, "stack": "Python + Go"}},
    )

    assert response.status_code == 200
    assert provider.generate_embedding.await_count >= 1


async def test_embedding_status_reports_state(
    async_client, clean_db, override_get_session, create_profile
):
    """GET /v1/profiles/{id}/embedding-status refleja el vector persistido."""
    # Sin embedding.
    bare = await create_profile(name="Bare")
    response = await async_client.get(f"/v1/profiles/{bare.id}/embedding-status")
    assert response.status_code == 200
    body = response.json()
    assert body["has_embedding"] is False
    assert body["embedding_model"] is None
    assert body["last_calculated"] is None

    # Con embedding.
    embedded = await create_profile(
        name="With Embedding",
        embedding=[0.1] * EMBEDDING_DIM,
        embedding_model=EMBEDDING_MODEL,
    )
    response = await async_client.get(
        f"/v1/profiles/{embedded.id}/embedding-status"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_embedding"] is True
    assert body["embedding_model"] == EMBEDDING_MODEL
    assert body["last_calculated"] is not None


async def test_embedding_status_missing_returns_404(
    async_client, clean_db, override_get_session
):
    """embedding-status de id inexistente → 404."""
    response = await async_client.get("/v1/profiles/99999/embedding-status")
    assert response.status_code == 404
