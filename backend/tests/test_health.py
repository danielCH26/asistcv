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


def test_match_placeholder(client: TestClient):
    """Test /v1/match endpoint returns placeholder response."""
    response = client.post(
        "/v1/match",
        json={"jd_text": "test job description", "profile_id": 1}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["score"] is None
    assert data["status"] == "not_implemented_yet"
    assert "Sprint 1" in data["message"]


def test_docs_available(client: TestClient):
    """Test OpenAPI docs are available."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc_available(client: TestClient):
    """Test ReDoc docs are available."""
    response = client.get("/redoc")
    assert response.status_code == 200
