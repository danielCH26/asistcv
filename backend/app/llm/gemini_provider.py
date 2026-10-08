"""
Gemini embedding provider implementation using REST API via httpx.

Uses the Google Generative Language API (REST) for text embeddings.
"""
import logging
from typing import Any

import httpx

from app.llm.schemas import AdaptedCV, CVAudit, Embedding, MatchAnalysis

logger = logging.getLogger(__name__)

# Expected embedding dimension for gemini-embedding-001
EXPECTED_DIMENSION = 768

# Gemini Embedding REST API base URL
_GEMINI_EMBED_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiEmbeddingProvider:
    """
    Embedding provider using Gemini Embedding REST API via httpx.

    This provider only implements generate_embedding.
    For LLM operations, use GroqProvider.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-001",
        timeout: float = 30.0,
    ):
        """
        Initialize the Gemini embedding provider.

        Args:
            api_key: Google Gemini API key.
            model: Model to use for embeddings (default: gemini-embedding-001).
            timeout: Request timeout in seconds (default: 30.0).

        Raises:
            ValueError: If api_key is empty or whitespace.
        """
        if not api_key or not api_key.strip():
            raise ValueError(
                "GEMINI_API_KEY is required for GeminiEmbeddingProvider. "
                "Set the GEMINI_API_KEY environment variable."
            )
        self._api_key = api_key.strip()
        self._model = model
        self._timeout = timeout

    async def generate_embedding(self, text: str) -> Embedding:
        """
        Generate embedding using Gemini Embedding REST API.

        Args:
            text: Input text to embed.

        Returns:
            Embedding with 768-dimensional vector.

        Raises:
            httpx.TimeoutException: On request timeout.
            httpx.HTTPStatusError: On non-2xx response.
        """
        url = f"{_GEMINI_EMBED_BASE}/{self._model}:embedContent"
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": f"models/{self._model}",
            "content": {
                "parts": [{"text": text}],
            },
            "taskType": "SEMANTIC_SIMILARITY",
            "outputDimensionality": EXPECTED_DIMENSION,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 429:
                retry_after = response.headers.get("retry-after", "unknown")
                raise httpx.HTTPStatusError(
                    f"Gemini API rate limit exceeded (429). Retry after: {retry_after}s",
                    request=response.request,
                    response=response,
                )

            if not response.is_success:
                # Surface a typed error without leaking raw response body
                raise httpx.HTTPStatusError(
                    f"Gemini API returned {response.status_code}. "
                    f"Request failed; check GEMINI_API_KEY and quota.",
                    request=response.request,
                    response=response,
                )

            data = response.json()
            embedding_values = data.get("embedding", {}).get("values")

            if not embedding_values or not isinstance(embedding_values, list):
                raise ValueError(
                    f"Unexpected Gemini API response shape: expected "
                    f"'embedding.values' list, got: {data!r}"
                )

            if len(embedding_values) != EXPECTED_DIMENSION:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {EXPECTED_DIMENSION}, "
                    f"got {len(embedding_values)}"
                )

            logger.info(
                "Gemini embedding generated",
                extra={
                    "model": self._model,
                    "dimension": len(embedding_values),
                },
            )

            return Embedding(
                vector=embedding_values,
                model=self._model,
                provider="gemini",
            )

    async def generate_match(
        self,
        jd_text: str,
        profile_context: dict[str, Any],
    ) -> MatchAnalysis:
        """
        Generate match analysis is not supported by GeminiEmbeddingProvider.

        Raises:
            NotImplementedError: Always, use GroqProvider for LLM operations.
        """
        raise NotImplementedError(
            "GeminiEmbeddingProvider only supports embeddings. "
            "Use GroqProvider for LLM operations."
        )

    async def generate_cv_audit(self, cv_text: str) -> CVAudit:
        """
        Generate CV quality audit is not supported by GeminiEmbeddingProvider.

        Raises:
            NotImplementedError: Always, use GroqProvider for LLM operations.
        """
        raise NotImplementedError(
            "GeminiEmbeddingProvider only supports embeddings. "
            "Use GroqProvider for LLM operations."
        )

    async def generate_adaptation(
        self,
        cv_structured: dict[str, Any],
        jd_text: str,
        *,
        max_tokens: int = 4000,
    ) -> AdaptedCV:
        """
        Generate CV adaptation is not supported by GeminiEmbeddingProvider.

        Raises:
            NotImplementedError: Always, use GroqProvider for LLM operations.
        """
        raise NotImplementedError(
            "GeminiEmbeddingProvider only supports embeddings. "
            "Use GroqProvider for LLM operations."
        )
