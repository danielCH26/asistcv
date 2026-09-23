"""
Smoke tests for FastAPI endpoints.
"""
from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """Test /health endpoint returns ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ping_endpoint(client: TestClient):
    """Test /v1/ping endpoint returns pong with timestamp."""
    response = client.get("/v1/ping")
    assert response.status_code == 200
    data = response.json()
    assert data["pong"] is True
    assert "timestamp" in data


async def test_match_endpoint_smoke(async_client, clean_db, patch_match_db, create_profile):
    """Smoke: /v1/match con MockProvider persiste JD + análisis (mock real de fábrica)."""
    from sqlmodel import select

    from app.db.models import Analysis, JobDescription

    profile = await create_profile(name="Smoke User")

    response = await async_client.post(
        "/v1/match",
        json={
            "jd_text": (
                "We are looking for a Python developer with strong backend "
                "experience in FastAPI and PostgreSQL for a remote role."
            ),
            "profile_id": profile.id,
        },
    )

    assert response.status_code == 200
    data = response.json()
    # Mock provider returns default response for unknown keywords
    assert data["score"] is not None
    assert isinstance(data["score"], int)
    assert 0 <= data["score"] <= 100
    assert "strengths" in data
    assert "gaps" in data
    assert "energy_level" in data
    assert "reasoning" in data

    # Persistencia mínima: 1 JD + 1 análisis.
    async with clean_db.session_factory() as session:
        jds = (await session.execute(select(JobDescription))).scalars().all()
        analyses = (await session.execute(select(Analysis))).scalars().all()
        assert len(jds) == 1
        assert len(analyses) == 1
        assert analyses[0].job_description_id == jds[0].id


def test_docs_available(client: TestClient):
    """Test OpenAPI docs are available."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc_available(client: TestClient):
    """Test ReDoc docs are available."""
    response = client.get("/redoc")
    assert response.status_code == 200
