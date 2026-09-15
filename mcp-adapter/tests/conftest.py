"""Fixtures para los tests."""

from unittest.mock import AsyncMock

import pytest

from asistcv_mcp.config import Settings


@pytest.fixture
def mock_backend_client():
    """Fixture que retorna un AsyncMock del BackendClient."""
    client = AsyncMock()
    client.get_health = AsyncMock(return_value={"status": "ok"})
    client.evaluate_match = AsyncMock(
        return_value={
            "score": 0.85,
            "strengths": ["Python", "FastAPI", "TypeScript"],
            "gaps": ["Kubernetes"],
            "energy_level": "high",
            "reasoning": "Good technical match",
        }
    )
    client.close = AsyncMock()
    return client


@pytest.fixture
def settings() -> Settings:
    """Fixture con configuración de test."""
    return Settings(
        backend_url="http://localhost:8000",
        backend_api_key=None,
        log_level="DEBUG",
        timeout_seconds=30.0,
    )


@pytest.fixture
def settings_with_api_key() -> Settings:
    """Fixture con configuración de test con API key."""
    return Settings(
        backend_url="http://localhost:8000",
        backend_api_key="test-api-key",
        log_level="DEBUG",
        timeout_seconds=30.0,
    )
