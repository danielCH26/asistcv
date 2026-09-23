"""
Tests for the HuggingFace provider.
"""
from unittest.mock import patch

import pytest

from app.llm.huggingface_provider import (
    EXPECTED_DIMENSION,
    HF_EMBEDDING_URL,
    HuggingFaceProvider,
)


class TestHuggingFaceProvider:
    """Tests for the HuggingFaceProvider class."""

    @pytest.fixture
    def provider(self) -> HuggingFaceProvider:
        """Create a HuggingFaceProvider instance with test token."""
        return HuggingFaceProvider(api_key="test_token")

    def test_provider_initialization(self, provider: HuggingFaceProvider):
        """Provider should initialize with correct defaults."""
        assert provider._api_key == "test_token"
        assert provider._embedding_model == "BAAI/bge-m3"
        assert provider._timeout == 30.0
        assert provider._max_retries == 3

    def test_provider_custom_config(self):
        """Provider should accept custom configuration."""
        provider = HuggingFaceProvider(
            api_key="custom_key",
            embedding_model="custom-model",
            timeout=60.0,
        )
        assert provider._api_key == "custom_key"
        assert provider._embedding_model == "custom-model"
        assert provider._timeout == 60.0

    @pytest.mark.asyncio
    async def test_generate_match_raises_not_implemented(self, provider: HuggingFaceProvider):
        """Should raise NotImplementedError for match generation."""
        with pytest.raises(NotImplementedError) as exc_info:
            await provider.generate_match(jd_text="JD", profile_context={})

        assert "only supports embeddings" in str(exc_info.value)


class TestHuggingFaceProviderConfiguration:
    """Tests for provider configuration."""

    def test_default_model_is_bge_m3(self):
        """Should use BAAI/bge-m3 as default model."""
        provider = HuggingFaceProvider(api_key="test")
        assert provider._embedding_model == "BAAI/bge-m3"

    def test_custom_model(self):
        """Should allow custom model configuration."""
        provider = HuggingFaceProvider(api_key="test", embedding_model="custom-model")
        assert provider._embedding_model == "custom-model"

    def test_uses_correct_api_endpoint(self):
        """Should use HF Inference API endpoint."""
        assert HF_EMBEDDING_URL == "https://api-inference.huggingface.co/models/BAAI/bge-m3"

    def test_expected_dimension(self):
        """Should have correct expected dimension."""
        assert EXPECTED_DIMENSION == 1024


class TestHuggingFaceProviderFactory:
    """Tests for HuggingFace provider integration with factory."""

    def test_factory_requires_api_key(self):
        """Should raise error if HUGGINGFACE_API_KEY is missing."""
        from app.llm.factory import get_llm_provider

        with patch("app.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "huggingface"
            mock_settings.return_value.huggingface_api_key = None

            get_llm_provider.cache_clear()

            with pytest.raises(ValueError) as exc_info:
                get_llm_provider()

            assert "HUGGINGFACE_API_KEY" in str(exc_info.value)

            get_llm_provider.cache_clear()
