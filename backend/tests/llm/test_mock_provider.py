"""
Tests for the mock LLM provider and factory.
"""
import math
from pathlib import Path
from unittest.mock import patch

import pytest

from app.llm.factory import get_llm_provider
from app.llm.mock import DEFAULT_RESPONSE, MockProvider

# Fixture path for tests
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "llm_responses"


class TestMockProvider:
    """Tests for the MockProvider class."""

    @pytest.fixture
    def provider(self) -> MockProvider:
        """Create a MockProvider instance with test fixtures."""
        return MockProvider(fixtures_dir=FIXTURES_DIR)

    @pytest.mark.asyncio
    async def test_generate_match_returns_valid_analysis(self, provider: MockProvider):
        """Any JD text should return a valid MatchAnalysis object."""
        jd_text = "Software engineer position available"
        profile_context = {"profile_id": 1}

        result = await provider.generate_match(jd_text, profile_context)

        assert result is not None
        assert 0 <= result.score <= 100
        assert isinstance(result.strengths, list)
        assert isinstance(result.gaps, list)
        assert result.energy_level in ["low", "medium", "high"]
        assert isinstance(result.reasoning, str)

    @pytest.mark.asyncio
    async def test_generate_match_deterministic(self, provider: MockProvider):
        """Same input should produce the same output."""
        jd_text = "Software engineer position"
        profile_context = {"profile_id": 1}

        result1 = await provider.generate_match(jd_text, profile_context)
        result2 = await provider.generate_match(jd_text, profile_context)

        assert result1.score == result2.score
        assert result1.strengths == result2.strengths
        assert result1.gaps == result2.gaps
        assert result1.energy_level == result2.energy_level
        assert result1.reasoning == result2.reasoning

    @pytest.mark.asyncio
    async def test_generate_match_uses_fixture_by_keyword(self, provider: MockProvider):
        """If JD contains keywords, should return matching fixture response."""
        # JD contains "python" and "remote" - should match senior_python_remote.json
        jd_text = "Senior Python developer wanted for remote work"

        result = await provider.generate_match(jd_text, {"profile_id": 1})

        assert result.score == 78  # From fixture
        assert "Python" in result.strengths[0] or "Python" in result.reasoning

    @pytest.mark.asyncio
    async def test_generate_match_returns_default_when_no_match(self, provider: MockProvider):
        """When no fixture matches, should return default response."""
        jd_text = "xyz123 no matching keywords here"

        result = await provider.generate_match(jd_text, {"profile_id": 1})

        assert result.score == DEFAULT_RESPONSE["score"]
        assert result.strengths == DEFAULT_RESPONSE["strengths"]

    @pytest.mark.asyncio
    async def test_generate_embedding_deterministic(self, provider: MockProvider):
        """Same text should produce the same embedding vector."""
        text = "Hello world"

        embedding1 = await provider.generate_embedding(text)
        embedding2 = await provider.generate_embedding(text)

        assert embedding1.vector == embedding2.vector
        assert embedding1.model == embedding2.model

    @pytest.mark.asyncio
    async def test_generate_embedding_correct_dimension(self, provider: MockProvider):
        """Embedding vector should have exactly 1024 dimensions."""
        embedding = await provider.generate_embedding("Test text")

        assert len(embedding.vector) == 1024

    @pytest.mark.asyncio
    async def test_generate_embedding_normalized(self, provider: MockProvider):
        """Embedding vector should be L2-normalized (norm ≈ 1.0)."""
        embedding = await provider.generate_embedding("Test text")

        # Calculate L2 norm
        norm = math.sqrt(sum(v * v for v in embedding.vector))

        # Allow small floating point tolerance
        assert abs(norm - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_generate_embedding_model_identifier(self, provider: MockProvider):
        """Embedding should include model identifier."""
        embedding = await provider.generate_embedding("Test")

        assert embedding.model == "mock-embedding-v1"


class TestFactory:
    """Tests for the LLM provider factory."""

    def test_factory_returns_mock_when_configured(self):
        """With LLM_PROVIDER=mock, should return MockProvider."""
        with patch("app.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "mock"

            # Clear the cache to pick up the new setting
            get_llm_provider.cache_clear()

            provider = get_llm_provider()

            assert isinstance(provider, MockProvider)

            # Clean up cache
            get_llm_provider.cache_clear()

    def test_factory_raises_on_unknown_provider(self):
        """With invalid provider name, should raise ValueError."""
        with patch("app.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "invalid_provider"

            # Clear the cache
            get_llm_provider.cache_clear()

            with pytest.raises(ValueError) as exc_info:
                get_llm_provider()

            assert "Unknown LLM provider" in str(exc_info.value)
            assert "invalid_provider" in str(exc_info.value)

            # Clean up cache
            get_llm_provider.cache_clear()

    def test_factory_raises_on_vertex_not_supported(self):
        """With LLM_PROVIDER=vertex, should raise ValueError (no longer supported)."""
        with patch("app.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "vertex"

            # Clear the cache
            get_llm_provider.cache_clear()

            with pytest.raises(ValueError) as exc_info:
                get_llm_provider()

            assert "Unknown LLM provider" in str(exc_info.value)
            assert "vertex" in str(exc_info.value)

            # Clean up cache
            get_llm_provider.cache_clear()
