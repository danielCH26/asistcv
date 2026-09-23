"""
Tests del historial de análisis: GET /v1/analyses y GET /v1/analyses/{id}.

Escenarios del spec match-analysis cubiertos acá:
- "Listado cronológico inverso"
- "Historial vacío"
- "Filtrar historial por perfil"
- "Detalle de un análisis"
- "Detalle de análisis inexistente"
- Paginación limit/offset (design sección 5, sin escenario en spec)

Usa DB real de test; sin proveedores externos (no interviene el flujo match).
"""
from datetime import UTC, datetime, timedelta

from app.db.models import Analysis, JobDescription

BASE_TIME = datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC)
EMBEDDING_MODEL = "BAAI/bge-m3"
RAW_TEXT = "Buscamos un desarrollador Python senior con experiencia en cloud." * 3


async def _seed_analysis(
    clean_db,
    profile_id: int | None,
    *,
    created_at: datetime,
    score: int = 80,
    title: str | None = None,
    company: str | None = None,
    raw_text: str | None = None,
) -> Analysis:
    """Inserta un análisis (con su JD) directamente en el DB de test."""
    async with clean_db.session_factory() as session:
        jd = JobDescription(
            raw_text=raw_text or RAW_TEXT,
            title=title,
            company=company,
            embedding=[0.1] * 1024,
            embedding_model=EMBEDDING_MODEL,
        )
        session.add(jd)
        await session.flush()

        row = Analysis(
            job_description_id=jd.id,
            profile_id=profile_id,
            profile_snapshot={"name": "Test User"},
            score=score,
            strengths=["Python", "FastAPI"],
            gaps=["Docker"],
            energy_level="high",
            reasoning="Match sólido con el perfil solicitado.",
            embedding=[0.1] * 1024,
            embedding_model=EMBEDDING_MODEL,
            created_at=created_at,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def _seed_profile(clean_db, name: str) -> int:
    """Inserta un perfil de test y devuelve su id."""
    from app.db.models import Profile

    async with clean_db.session_factory() as session:
        profile = Profile(name=name)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile.id


async def test_list_empty_returns_empty_array(async_client, clean_db, override_get_session):
    """Historial vacío → 200 con []."""
    response = await async_client.get("/v1/analyses")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_reverse_chronological_order(async_client, clean_db, override_get_session):
    """Listado en orden created_at DESC."""
    profile_id = await _seed_profile(clean_db, "Test User")
    first = await _seed_analysis(clean_db, profile_id, created_at=BASE_TIME)
    second = await _seed_analysis(clean_db, profile_id, created_at=BASE_TIME + timedelta(hours=1))
    third = await _seed_analysis(clean_db, profile_id, created_at=BASE_TIME + timedelta(hours=2))

    response = await async_client.get("/v1/analyses")

    assert response.status_code == 200
    items = response.json()
    assert [item["id"] for item in items] == [third.id, second.id, first.id]

    expected_keys = {"id", "profile_id", "job_description_id", "score", "created_at"}
    assert set(items[0].keys()) == expected_keys
    assert items[0]["profile_id"] == profile_id
    assert items[0]["score"] == 80
    assert items[0]["job_description_id"] == third.job_description_id


async def test_list_pagination_limit_offset(async_client, clean_db, override_get_session):
    """Paginación por offset: defaults (20/0), límites y errores de validación."""
    profile_id = await _seed_profile(clean_db, "Test User")
    rows = [
        await _seed_analysis(clean_db, profile_id, created_at=BASE_TIME + timedelta(hours=i))
        for i in range(5)
    ]

    # Default: limit=20 → devuelve todos (5).
    response = await async_client.get("/v1/analyses")
    assert response.status_code == 200
    assert len(response.json()) == 5

    # Primera página.
    response = await async_client.get("/v1/analyses", params={"limit": 2, "offset": 0})
    assert [item["id"] for item in response.json()] == [rows[4].id, rows[3].id]

    # Segunda página.
    response = await async_client.get("/v1/analyses", params={"limit": 2, "offset": 2})
    assert [item["id"] for item in response.json()] == [rows[2].id, rows[1].id]

    # Última página parcial.
    response = await async_client.get("/v1/analyses", params={"limit": 2, "offset": 4})
    assert [item["id"] for item in response.json()] == [rows[0].id]

    # Validación: límites de limit/offset.
    assert (await async_client.get("/v1/analyses", params={"limit": 0})).status_code == 422
    assert (await async_client.get("/v1/analyses", params={"limit": 101})).status_code == 422
    assert (await async_client.get("/v1/analyses", params={"offset": -1})).status_code == 422


async def test_list_filter_by_profile(async_client, clean_db, override_get_session):
    """Filtro ?profile_id= devuelve solo análisis de ese perfil."""
    profile_a = await _seed_profile(clean_db, "Perfil A")
    profile_b = await _seed_profile(clean_db, "Perfil B")
    a1 = await _seed_analysis(clean_db, profile_a, created_at=BASE_TIME)
    await _seed_analysis(clean_db, profile_b, created_at=BASE_TIME + timedelta(hours=1))
    a2 = await _seed_analysis(clean_db, profile_a, created_at=BASE_TIME + timedelta(hours=2))

    response = await async_client.get("/v1/analyses", params={"profile_id": profile_a})

    assert response.status_code == 200
    items = response.json()
    assert [item["id"] for item in items] == [a2.id, a1.id]
    assert all(item["profile_id"] == profile_a for item in items)


async def test_list_summary_handles_legacy_null_profile(
    async_client, clean_db, override_get_session
):
    """Filas legacy sin profile_id se listan con profile_id null."""
    legacy = await _seed_analysis(clean_db, None, created_at=BASE_TIME)

    response = await async_client.get("/v1/analyses")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["id"] == legacy.id
    assert items[0]["profile_id"] is None


async def test_detail_returns_full_analysis_with_embedded_jd(
    async_client, clean_db, override_get_session
):
    """Detalle: análisis completo + job_description embebido (title/company/snippet)."""
    profile_id = await _seed_profile(clean_db, "Test User")
    row = await _seed_analysis(
        clean_db,
        profile_id,
        created_at=BASE_TIME,
        score=72,
        title="Senior Python Developer",
        company="Acme Corp",
    )

    response = await async_client.get(f"/v1/analyses/{row.id}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == row.id
    assert detail["profile_id"] == profile_id
    assert detail["score"] == 72
    assert detail["strengths"] == ["Python", "FastAPI"]
    assert detail["gaps"] == ["Docker"]
    assert detail["energy_level"] == "high"
    assert detail["reasoning"] == "Match sólido con el perfil solicitado."
    assert detail["created_at"] == BASE_TIME.isoformat().replace("+00:00", "Z")

    jd = detail["job_description"]
    assert jd["id"] == row.job_description_id
    assert jd["title"] == "Senior Python Developer"
    assert jd["company"] == "Acme Corp"
    assert jd["snippet"] == RAW_TEXT


async def test_detail_truncates_long_raw_text(async_client, clean_db, override_get_session):
    """Snippet del JD: raw_text largo se trunca a 200 chars + ellipsis."""
    profile_id = await _seed_profile(clean_db, "Test User")
    long_text = "Requisitos del puesto: " + "x" * 400
    row = await _seed_analysis(
        clean_db, profile_id, created_at=BASE_TIME, raw_text=long_text
    )

    response = await async_client.get(f"/v1/analyses/{row.id}")

    assert response.status_code == 200
    snippet = response.json()["job_description"]["snippet"]
    assert len(snippet) == 201, "200 chars + ellipsis"
    assert snippet.endswith("…")
    assert snippet[:200] == long_text[:200]


async def test_detail_missing_analysis_returns_404(
    async_client, clean_db, override_get_session
):
    """Detalle de un id inexistente → 404 con mensaje identificable."""
    response = await async_client.get("/v1/analyses/99999")

    assert response.status_code == 404
    assert "99999" in response.json()["detail"]
