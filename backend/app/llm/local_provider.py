"""
Local embedding provider using fastembed / ONNX.

Fastembed runs entirely offline — no API keys, no network calls, no downloads
at runtime once the ONNX model is cached. This makes it the preferred local
option for CI, local dev, and edge deployments.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.llm.schemas import AdaptedCV, CVAudit, Embedding, MatchAnalysis

if TYPE_CHECKING:
    from fastembed import TextEmbedding as TextEmbeddingType

    from app.core.config import Settings

logger = logging.getLogger(__name__)

# Default dimension for paraphrase-multilingual-MiniLM-L12-v2
EXPECTED_DIMENSION = 384


def _get_TextEmbedding():  # noqa: N802
    """
    Lazy import of fastembed.TextEmbedding.

    Importing at call time (not module level) ensures that the patch applied
    by ``unittest.mock.patch`` in tests is active when the import resolves.
    Importing at module level causes the class to be bound to the module
    namespace before test fixtures run, making the patch ineffective.
    """
    from fastembed import TextEmbedding  # noqa: PLC0415

    return TextEmbedding


class LocalEmbeddingProvider:
    """
    Embedding provider using fastembed (ONNX).

    Supports any model from the fastembed model registry, including
    ``sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`` which
    produces 384-dimensional vectors and handles multilingual input.

    The model is loaded lazily: ``TextEmbedding`` is not instantiated in
    ``__init__`` — only when the first ``generate_embedding`` call occurs.
    This keeps startup fast and avoids loading a ~60 MB ONNX file when the
    provider is injected but never used.
    """

    def __init__(
        self,
        embedding_model: str | None = None,
        settings: Settings | None = None,
    ):
        """
        Initialize the local embedding provider.

        Args:
            embedding_model: Model name or HuggingFace path. If omitted, read
                from ``settings.embedding_model``.
            settings: Optional Settings instance. If omitted, imported lazily
                to avoid a circular import at module level.
        """
        self._embedding_model = embedding_model
        self._settings = settings
        self._model: TextEmbeddingType | None = None

    @property
    def _resolved_model_name(self) -> str:
        """Resolve the model name from settings or the explicit constructor arg."""
        if self._embedding_model:
            return self._embedding_model
        if self._settings:
            return self._settings.embedding_model
        # Lazy import to avoid the circular dependency at import time
        from app.core.config import get_settings

        return get_settings().embedding_model

    def _ensure_model(self) -> TextEmbeddingType:
        """
        Ensure the fastembed model is loaded.

        The model is instantiated once and cached in ``self._model``.
        Subsequent calls return the same instance.
        """
        if self._model is None:
            model_name = self._resolved_model_name
            logger.info("Loading fastembed model", extra={"model": model_name})
            self._model = _get_TextEmbedding()(model_name=model_name)
        return self._model

    def _sync_embed(self, text: str) -> list[float]:
        """
        Synchronous embedding call to fastembed.

        Args:
            text: Input text to embed.

        Returns:
            List of floats representing the embedding vector.

        Raises:
            ValueError: If the text is empty or the response is malformed.
            RuntimeError: If fastembed itself raises.
        """
        if not text or not text.strip():
            raise ValueError("Cannot generate embedding for empty text")

        model = self._ensure_model()

        # ``model.embed`` accepts an iterable of strings and returns an iterator
        # of lists of floats (one list per input string).
        results: list[list[float]] = list(model.embed([text]))

        if not results or not results[0]:
            raise ValueError(
                "Fastembed returned an empty embedding vector for the given text"
            )

        vector = results[0]

        if len(vector) != EXPECTED_DIMENSION:
            logger.warning(
                "Fastembed dimension mismatch",
                extra={
                    "expected": EXPECTED_DIMENSION,
                    "actual": len(vector),
                },
            )

        return vector

    async def generate_embedding(self, text: str) -> Embedding:
        """
        Generate embedding for the given text.

        The sync fastembed call is offloaded to a thread pool via
        ``asyncio.to_thread`` so it never blocks the async event loop.

        Args:
            text: Input text to embed.

        Returns:
            Embedding with vector and model identifier.

        Raises:
            ValueError: If the text is empty or the response is invalid.
            RuntimeError: If fastembed fails.
        """
        try:
            vector = await asyncio.to_thread(self._sync_embed, text)
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Fastembed embedding failed: {exc}"
            ) from exc

        model_name = self._resolved_model_name

        logger.info(
            "Local embedding generated",
            extra={
                "model": model_name,
                "dimension": len(vector),
            },
        )

        return Embedding(
            vector=vector,
            model=model_name,
            provider="local",
        )

    # ── LLM stub (satisfies LLMProvider protocol) ────────────────────────────

    async def generate_match(
        self,
        jd_text: str,
        profile_context: dict[str, Any],
    ) -> MatchAnalysis:
        raise NotImplementedError(
            "LocalEmbeddingProvider only supports embeddings. "
            "Use GroqProvider for LLM operations."
        )

    async def generate_cv_audit(self, cv_text: str) -> CVAudit:
        raise NotImplementedError(
            "LocalEmbeddingProvider only supports embeddings. "
            "Use GroqProvider for LLM operations."
        )

    async def generate_adaptation(
        self,
        cv_structured: dict[str, Any],
        jd_text: str,
        *,
        max_tokens: int = 4000,
    ) -> AdaptedCV:
        raise NotImplementedError(
            "LocalEmbeddingProvider only supports embeddings. "
            "Use GroqProvider for LLM operations."
        )
