"""
Tests for LocalEmbeddingProvider (fastembed/ONNX).
"""
from unittest.mock import MagicMock, patch

import pytest

from app.llm.local_provider import LocalEmbeddingProvider
from app.llm.schemas import Embedding

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_text_embedding_model():
    """
    Fake TextEmbedding that returns a 384-dim vector.
    Never downloads anything — suitable for CI.
    """
    fake_model = MagicMock()
    fake_model.embed = MagicMock(return_value=[[0.1] * 384])
    return fake_model


@pytest.fixture
def mock_local_provider(mock_text_embedding_model):
    """
    Fully-mocked LocalEmbeddingProvider for async tests.

    Patches:
    - _get_TextEmbedding  → returns mock TextEmbedding (no ONNX download)
    - asyncio.to_thread  → runs callable inline (no thread blocking)
    - get_settings       → returns embedding_model from test context

    Note: get_settings is imported lazily inside _resolved_model_name, so we
    patch it at its definition site (app.core.config).
    """
    with (
        patch(
            "app.llm.local_provider._get_TextEmbedding",
            return_value=lambda model_name=None: mock_text_embedding_model,
        ),
        patch("app.llm.local_provider.asyncio.to_thread", side_effect=lambda fn, *a, **kw: fn(*a, **kw)),
        patch("app.core.config.get_settings") as mock_settings,
    ):
        mock_settings.return_value.embedding_model = (
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        yield mock_text_embedding_model


# ─── Lazy init ────────────────────────────────────────────────────────────────


class TestLazyInit:
    """LocalEmbeddingProvider must not instantiate the model in __init__."""

    def test_no_model_instantiated_on_construction(self, mock_text_embedding_model):
        """Creating the provider must not call _get_TextEmbedding."""
        with patch(
            "app.llm.local_provider._get_TextEmbedding",
            return_value=lambda model_name=None: mock_text_embedding_model,
        ):
            provider = LocalEmbeddingProvider()
            # _get_TextEmbedding is only called when _ensure_model runs
            assert provider._model is None

    def test_model_instantiated_on_first_embed(self, mock_text_embedding_model):
        """The model is loaded only on the first generate_embedding call."""
        with patch(
            "app.llm.local_provider._get_TextEmbedding",
            return_value=lambda model_name=None: mock_text_embedding_model,
        ) as mock_get_te:
            provider = LocalEmbeddingProvider(embedding_model="test-model")
            mock_get_te.assert_not_called()

            provider._ensure_model()
            mock_get_te.assert_called_once()


# ─── generate_embedding ───────────────────────────────────────────────────────


class TestGenerateEmbedding:
    """Core embedding contract."""

    @pytest.mark.asyncio
    async def test_returns_embedding_with_384_dim_vector(self, mock_local_provider):
        """generate_embedding returns Embedding with vector of 384 floats."""
        provider = LocalEmbeddingProvider(embedding_model="test-model")
        result = await provider.generate_embedding("Hola mundo")

        assert isinstance(result, Embedding)
        assert len(result.vector) == 384
        assert all(isinstance(v, float) for v in result.vector)

    @pytest.mark.asyncio
    async def test_returns_embedding_with_model_from_settings(self, mock_local_provider):
        """Embedding.model reflects the configured embedding_model."""
        provider = LocalEmbeddingProvider()
        result = await provider.generate_embedding("Test")

        assert result.model == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    @pytest.mark.asyncio
    async def test_provider_identifier_is_local(self, mock_local_provider):
        """Embedding.provider is 'local'."""
        provider = LocalEmbeddingProvider()
        result = await provider.generate_embedding("Text")

        assert result.provider == "local"

    @pytest.mark.asyncio
    async def test_deterministic_same_text_same_vector(self, mock_text_embedding_model):
        """Same text always produces the same vector (fastembed is deterministic)."""
        with (
            patch(
                "app.llm.local_provider._get_TextEmbedding",
                return_value=lambda model_name=None: mock_text_embedding_model,
            ),
            patch(
                "app.llm.local_provider.asyncio.to_thread",
                side_effect=lambda fn, *a, **kw: fn(*a, **kw),
            ),
            patch("app.core.config.get_settings") as mock_settings,
        ):
            mock_settings.return_value.embedding_model = "test-model"
            provider = LocalEmbeddingProvider()

            r1 = await provider.generate_embedding("Hello world")
            r2 = await provider.generate_embedding("Hello world")

        assert r1.vector == r2.vector

    @pytest.mark.asyncio
    async def test_different_texts_produce_different_vectors(self, mock_text_embedding_model):
        """Different inputs produce different vectors."""
        mock_text_embedding_model.embed = MagicMock(
            side_effect=[
                [[0.1] * 384],
                [[0.2] * 384],
            ]
        )
        with (
            patch(
                "app.llm.local_provider._get_TextEmbedding",
                return_value=lambda model_name=None: mock_text_embedding_model,
            ),
            patch(
                "app.llm.local_provider.asyncio.to_thread",
                side_effect=lambda fn, *a, **kw: fn(*a, **kw),
            ),
            patch("app.core.config.get_settings") as mock_settings,
        ):
            mock_settings.return_value.embedding_model = "test-model"
            provider = LocalEmbeddingProvider()

            r1 = await provider.generate_embedding("Text A")
            r2 = await provider.generate_embedding("Text B")

        assert r1.vector != r2.vector


# ─── Error handling ───────────────────────────────────────────────────────────


class TestErrorHandling:
    """Errors from fastembed are surfaced as typed exceptions."""

    @pytest.mark.asyncio
    async def test_empty_text_raises_value_error(self, mock_text_embedding_model):
        """Empty text raises ValueError (mirrors huggingface_provider pattern)."""
        mock_model = MagicMock()
        mock_model.embed = MagicMock(return_value=[[]])

        with (
            patch(
                "app.llm.local_provider._get_TextEmbedding",
                return_value=lambda model_name=None: mock_model,
            ),
            patch(
                "app.llm.local_provider.asyncio.to_thread",
                side_effect=lambda fn, *a, **kw: fn(*a, **kw),
            ),
            patch("app.core.config.get_settings") as mock_settings,
        ):
            mock_settings.return_value.embedding_model = "test-model"
            provider = LocalEmbeddingProvider()

            with pytest.raises(ValueError) as exc_info:
                await provider.generate_embedding("")

            assert "empty" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_fastembed_error_propagates(self, mock_text_embedding_model):
        """Runtime errors from fastembed are propagated, not swallowed."""
        mock_model = MagicMock()
        mock_model.embed = MagicMock(side_effect=RuntimeError("fastembed failure"))

        with (
            patch(
                "app.llm.local_provider._get_TextEmbedding",
                return_value=lambda model_name=None: mock_model,
            ),
            patch(
                "app.llm.local_provider.asyncio.to_thread",
                side_effect=lambda fn, *a, **kw: fn(*a, **kw),
            ),
            patch("app.core.config.get_settings") as mock_settings,
        ):
            mock_settings.return_value.embedding_model = "test-model"
            provider = LocalEmbeddingProvider()

            with pytest.raises(RuntimeError) as exc_info:
                await provider.generate_embedding("test")

            assert "fastembed failure" in str(exc_info.value)


# ─── Concurrency / asyncio.to_thread ─────────────────────────────────────────


class TestConcurrency:
    """generate_embedding uses asyncio.to_thread so it does not block the loop."""

    @pytest.mark.asyncio
    async def test_embed_runs_in_thread(self, mock_text_embedding_model):
        """The sync fastembed call must be offloaded to a thread, not run inline."""
        with (
            patch(
                "app.llm.local_provider._get_TextEmbedding",
                return_value=lambda model_name=None: mock_text_embedding_model,
            ),
            patch(
                "app.llm.local_provider.asyncio.to_thread",
                side_effect=lambda fn, *a, **kw: fn(*a, **kw),
            ) as mock_thread,
            patch("app.core.config.get_settings") as mock_settings,
        ):
            mock_settings.return_value.embedding_model = "test-model"
            provider = LocalEmbeddingProvider()

            await provider.generate_embedding("concurrent test")

            mock_thread.assert_called_once()
            # The callable passed to to_thread must be the bound _sync_embed method
            _, args, _ = mock_thread.mock_calls[0]
            assert callable(args[0])


# ─── Factory wiring ───────────────────────────────────────────────────────────


class TestFactoryWiring:
    """Factory returns LocalEmbeddingProvider when embedding_provider=local."""

    def test_factory_returns_local_provider(self):
        """get_llm_provider with LLM_PROVIDER=groq + EMBEDDING_PROVIDER=local."""
        from app.llm.factory import get_llm_provider
        from app.llm.local_provider import LocalEmbeddingProvider

        with patch("app.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "groq"
            mock_settings.return_value.groq_api_key = "test_key"
            mock_settings.return_value.groq_model = "test-model"
            mock_settings.return_value.huggingface_api_key = None
            mock_settings.return_value.embedding_provider = "local"
            mock_settings.return_value.embedding_model = (
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            )
            mock_settings.return_value.hf_embedding_model = "BAAI/bge-m3"

            get_llm_provider.cache_clear()

            provider = get_llm_provider()

            # Should be CompositeProvider wrapping LocalEmbeddingProvider
            assert hasattr(provider, "_embeddings")
            assert isinstance(provider._embeddings, LocalEmbeddingProvider)

            get_llm_provider.cache_clear()

    def test_factory_groq_with_huggingface_embedding_provider(self):
        """LLM_PROVIDER=groq + EMBEDDING_PROVIDER=huggingface still works."""
        from app.llm.factory import get_llm_provider
        from app.llm.huggingface_provider import HuggingFaceProvider

        with patch("app.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "groq"
            mock_settings.return_value.groq_api_key = "test_key"
            mock_settings.return_value.groq_model = "test-model"
            mock_settings.return_value.huggingface_api_key = "hf_key"
            mock_settings.return_value.embedding_provider = "huggingface"
            mock_settings.return_value.embedding_model = "BAAI/bge-m3"
            mock_settings.return_value.hf_embedding_model = "BAAI/bge-m3"

            get_llm_provider.cache_clear()

            provider = get_llm_provider()

            assert hasattr(provider, "_embeddings")
            assert isinstance(provider._embeddings, HuggingFaceProvider)

            get_llm_provider.cache_clear()

    def test_factory_groq_with_mock_embedding_provider(self):
        """LLM_PROVIDER=groq + EMBEDDING_PROVIDER=mock."""
        from app.llm.factory import get_llm_provider
        from app.llm.mock import MockProvider

        with patch("app.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "groq"
            mock_settings.return_value.groq_api_key = "test_key"
            mock_settings.return_value.groq_model = "test-model"
            mock_settings.return_value.huggingface_api_key = None
            mock_settings.return_value.embedding_provider = "mock"
            mock_settings.return_value.embedding_model = "mock-model"
            mock_settings.return_value.hf_embedding_model = "BAAI/bge-m3"

            get_llm_provider.cache_clear()

            provider = get_llm_provider()

            assert hasattr(provider, "_embeddings")
            assert isinstance(provider._embeddings, MockProvider)

            get_llm_provider.cache_clear()
