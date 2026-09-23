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


def test_match_endpoint_with_mock(client: TestClient):
    """Test /v1/match endpoint returns mock analysis with LLM_PROVIDER=mock."""
    from unittest.mock import AsyncMock, MagicMock

    from app.db.models import Profile
    from app.db.session import get_session
    from app.main import app

    profile = Profile(id=1, name="Test User")
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = profile

    async def override_get_session():
        session = AsyncMock()
        session.execute = AsyncMock(return_value=execute_result)
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        response = client.post(
            "/v1/match",
            json={"jd_text": "test job description", "profile_id": 1}
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

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


def test_docs_available(client: TestClient):
    """Test OpenAPI docs are available."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc_available(client: TestClient):
    """Test ReDoc docs are available."""
    response = client.get("/redoc")
    assert response.status_code == 200
