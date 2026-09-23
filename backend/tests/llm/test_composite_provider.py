"""
Tests for the Composite provider.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.composite import CompositeProvider
from app.llm.schemas import Embedding, MatchAnalysis


class TestCompositeProvider:
    """Tests for the CompositeProvider class."""

    @pytest.fixture
    def mock_llm_provider(self):
        """Create a mock LLM provider."""
        provider = AsyncMock()
        provider.generate_match = AsyncMock(
            return_value=MatchAnalysis(
                score=80,
                strengths=["Python"],
                gaps=["AWS"],
                energy_level="high",
                reasoning="Good match",
            )
        )
        return provider

    @pytest.fixture
    def mock_embedding_provider(self):
        """Create a mock embedding provider."""
        provider = AsyncMock()
        provider.generate_embedding = AsyncMock(
            return_value=Embedding(
                vector=[0.1] * 1024,
                model="BAAI/bge-m3",
                provider="huggingface",
            )
        )
        return provider

    @pytest.fixture
    def composite(
        self, mock_llm_provider, mock_embedding_provider
    ) -> CompositeProvider:
        """Create a CompositeProvider instance."""
        return CompositeProvider(
            llm_provider=mock_llm_provider,
            embedding_provider=mock_embedding_provider,
        )

    @pytest.mark.asyncio
    async def test_generate_match_delegates_to_llm_provider(
        self, composite, mock_llm_provider
    ):
        """Should delegate generate_match to LLM provider."""
        jd_text = "Python developer"
        profile_context = {"skills": ["Python"]}

        result = await composite.generate_match(jd_text, profile_context)

        mock_llm_provider.generate_match.assert_called_once_with(jd_text, profile_context)
        assert result.score == 80
        assert "Python" in result.strengths

    @pytest.mark.asyncio
    async def test_generate_embedding_delegates_to_embedding_provider(
        self, composite, mock_embedding_provider
    ):
        """Should delegate generate_embedding to embedding provider."""
        text = "Test text"

        result = await composite.generate_embedding(text)

        mock_embedding_provider.generate_embedding.assert_called_once_with(text)
        assert len(result.vector) == 1024
        assert result.provider == "huggingface"

    @pytest.mark.asyncio
    async def test_composite_preserves_llm_errors(self, composite, mock_llm_provider):
        """Should propagate errors from LLM provider."""
        mock_llm_provider.generate_match = AsyncMock(
            side_effect=ValueError("LLM error")
        )

        with pytest.raises(ValueError) as exc_info:
            await composite.generate_match("JD", {})

        assert "LLM error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_composite_preserves_embedding_errors(
        self, composite, mock_embedding_provider
    ):
        """Should propagate errors from embedding provider."""
        mock_embedding_provider.generate_embedding = AsyncMock(
            side_effect=ValueError("Embedding error")
        )

        with pytest.raises(ValueError) as exc_info:
            await composite.generate_embedding("text")

        assert "Embedding error" in str(exc_info.value)


class TestCompositeProviderFactory:
    """Tests for CompositeProvider integration with factory."""

    def test_factory_creates_composite_for_groq(self):
        """Should create CompositeProvider when LLM_PROVIDER=groq."""
        from app.llm.factory import get_llm_provider

        with patch("app.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "groq"
            mock_settings.return_value.groq_api_key = "groq_key"
            mock_settings.return_value.groq_model = "llama-3.3-70b-versatile"
            mock_settings.return_value.huggingface_api_key = "hf_key"
            mock_settings.return_value.hf_embedding_model = "BAAI/bge-m3"

            get_llm_provider.cache_clear()

            provider = get_llm_provider()

            # Should be a CompositeProvider
            assert isinstance(provider, CompositeProvider)

            get_llm_provider.cache_clear()
