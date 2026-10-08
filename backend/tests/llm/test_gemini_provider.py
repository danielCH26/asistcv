"""
Tests for the Gemini embedding provider.

Uses the httpx monkeypatch pattern from test_email_service.py:
patch.object(httpx, "AsyncClient", return_value=fake_client)
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.gemini_provider import EXPECTED_DIMENSION, GeminiEmbeddingProvider
from app.llm.schemas import Embedding


class TestGeminiEmbeddingProvider:
    """Tests for the GeminiEmbeddingProvider class."""

    @pytest.fixture
    def provider(self) -> GeminiEmbeddingProvider:
        """Create a GeminiEmbeddingProvider instance with test key."""
        return GeminiEmbeddingProvider(api_key="test_api_key")

    def test_provider_initialization_defaults(self, provider: GeminiEmbeddingProvider):
        """Provider should initialize with correct defaults."""
        assert provider._api_key == "test_api_key"
        assert provider._model == "gemini-embedding-001"
        assert provider._timeout == 30.0

    def test_provider_custom_config(self):
        """Provider should accept custom configuration."""
        provider = GeminiEmbeddingProvider(
            api_key="custom_key",
            model="custom-model",
            timeout=60.0,
        )
        assert provider._api_key == "custom_key"
        assert provider._model == "custom-model"
        assert provider._timeout == 60.0

    @pytest.mark.asyncio
    async def test_generate_embedding_success(self, provider: GeminiEmbeddingProvider):
        """Should return Embedding with 768 floats, model gemini-embedding-001, provider gemini."""

        fake_response = MagicMock(spec=httpx.Response)
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "embedding": {
                "values": [0.1] * 768,
            }
        }

        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)
        fake_client.post = AsyncMock(return_value=fake_response)

        with patch.object(httpx, "AsyncClient", return_value=fake_client):
            embedding = await provider.generate_embedding("Test text")

        assert isinstance(embedding, Embedding)
        assert len(embedding.vector) == 768
        assert embedding.model == "gemini-embedding-001"
        assert embedding.provider == "gemini"

    @pytest.mark.asyncio
    async def test_sends_task_type_semantic_similarity(self, provider: GeminiEmbeddingProvider):
        """Should send taskType SEMANTIC_SIMILARITY and outputDimensionality 768."""

        captured_body: dict = {}

        async def capture_post(url: str, **kwargs) -> MagicMock:  # type: ignore[reportUnusedFunction]
            captured_body.update(kwargs.get("json", {}))
            fake_response = MagicMock(spec=httpx.Response)
            fake_response.status_code = 200
            fake_response.json.return_value = {"embedding": {"values": [0.0] * 768}}
            return fake_response

        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)
        fake_client.post = AsyncMock(side_effect=capture_post)

        with patch.object(httpx, "AsyncClient", return_value=fake_client):
            await provider.generate_embedding("CV: Senior Python Engineer")

        assert captured_body.get("taskType") == "SEMANTIC_SIMILARITY"
        assert captured_body.get("outputDimensionality") == 768
        assert "models/gemini-embedding-001" in captured_body.get("model", "")

    @pytest.mark.asyncio
    async def test_no_api_key_raises_value_error(self):
        """Should raise ValueError with coherent message when API key is missing."""

        with pytest.raises(ValueError) as exc_info:
            GeminiEmbeddingProvider(api_key="")

        assert "API key" in str(exc_info.value).lower() or "key" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_429_returns_rate_limit_error(self, provider: GeminiEmbeddingProvider):
        """Should raise typed error on 429 without leaking internals."""

        fake_response = MagicMock(spec=httpx.Response)
        fake_response.status_code = 429
        fake_response.text = "Rate limit exceeded"
        fake_response.headers = {"retry-after": "30"}

        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)
        fake_client.post = AsyncMock(return_value=fake_response)

        with patch.object(httpx, "AsyncClient", return_value=fake_client):
            with pytest.raises(Exception) as exc_info:
                await provider.generate_embedding("Test")

        error_msg = str(exc_info.value)
        assert "429" in error_msg or "rate limit" in error_msg.lower()
        # Should NOT expose raw response body or internal details
        assert "Rate limit exceeded" not in error_msg

    @pytest.mark.asyncio
    async def test_5xx_returns_typed_error(self, provider: GeminiEmbeddingProvider):
        """Should raise typed error on 5xx without leaking internals."""

        fake_response = MagicMock(spec=httpx.Response)
        fake_response.status_code = 500
        fake_response.text = "Internal server error details"
        fake_response.json.return_value = {"error": {"message": "Internal server error details"}}
        fake_response.is_success = False

        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)
        fake_client.post = AsyncMock(return_value=fake_response)

        with patch.object(httpx, "AsyncClient", return_value=fake_client):
            with pytest.raises(Exception) as exc_info:
                await provider.generate_embedding("Test")

        error_msg = str(exc_info.value)
        assert "500" in error_msg or "server error" in error_msg.lower()
        # Should NOT expose raw response body
        assert "Internal server error details" not in error_msg

    @pytest.mark.asyncio
    async def test_timeout_returns_typed_error(self, provider: GeminiEmbeddingProvider):
        """Should raise typed error on timeout."""

        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)
        fake_client.post = AsyncMock(
            side_effect=httpx.TimeoutException("Connection timeout")
        )

        with patch.object(httpx, "AsyncClient", return_value=fake_client):
            with pytest.raises(Exception) as exc_info:
                await provider.generate_embedding("Test")

        error_msg = str(exc_info.value)
        assert "timeout" in error_msg.lower()


class TestGeminiEmbeddingProviderConfiguration:
    """Tests for provider configuration."""

    def test_default_model_is_gemini_embedding_001(self):
        """Should use gemini-embedding-001 as default model."""
        provider = GeminiEmbeddingProvider(api_key="test")
        assert provider._model == "gemini-embedding-001"

    def test_custom_model(self):
        """Should allow custom model configuration."""
        provider = GeminiEmbeddingProvider(api_key="test", model="custom-model")
        assert provider._model == "custom-model"

    def test_expected_dimension(self):
        """Should have correct expected dimension."""
        assert EXPECTED_DIMENSION == 768


class TestGeminiEmbeddingProviderFactory:
    """Tests for Gemini provider integration with factory."""

    def test_factory_requires_api_key(self):
        """Should raise error if GEMINI_API_KEY is missing."""
        from app.llm.factory import get_llm_provider

        with patch("app.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "groq"
            mock_settings.return_value.groq_api_key = "some-key"
            mock_settings.return_value.groq_model = "qwen/qwen3.8-27b"
            mock_settings.return_value.embedding_provider = "gemini"
            mock_settings.return_value.gemini_api_key = None

            get_llm_provider.cache_clear()

            with pytest.raises(ValueError) as exc_info:
                get_llm_provider()

            assert "GEMINI_API_KEY" in str(exc_info.value)

            get_llm_provider.cache_clear()
