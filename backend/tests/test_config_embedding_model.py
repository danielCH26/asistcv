"""Tests for Settings.resolved_embedding_model (issue #101).

The on-demand re-embedding condition and the retrieval cache key compare
stored `embedding_model` markers against the model the ACTIVE embedding
provider produces. These tests pin that resolution per provider so a
default flip (gemini|huggingface|mock) cannot silently desync the markers.
"""

from app.core.config import Settings


def _settings(**overrides: str) -> Settings:
    """Build Settings with explicit provider fields, no env interference."""
    return Settings(
        embedding_provider=overrides.get("embedding_provider", "gemini"),
        gemini_embedding_model=overrides.get(
            "gemini_embedding_model", "gemini-embedding-001"
        ),
        hf_embedding_model=overrides.get("hf_embedding_model", "BAAI/bge-m3"),
    )


def test_huggingface_provider_resolves_hf_model():
    settings = _settings(embedding_provider="huggingface")
    assert settings.resolved_embedding_model == "BAAI/bge-m3"


def test_mock_provider_resolves_mock_marker():
    settings = _settings(embedding_provider="mock")
    assert settings.resolved_embedding_model == "mock-embedding-v1"


def test_case_insensitive_provider_resolution():
    settings = _settings(embedding_provider="GEMINI")
    assert settings.resolved_embedding_model == "gemini-embedding-001"
