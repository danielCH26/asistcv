"""
HuggingFace provider implementation for embedding operations.

Uses the official `huggingface_hub` SDK with the new `InferenceClient`
(which routes through `router.huggingface.co`). This replaces the
deprecated `api-inference.huggingface.co` endpoint.
"""
import asyncio
import logging
from typing import Any

from huggingface_hub import InferenceClient

from app.llm.schemas import Embedding, MatchAnalysis

logger = logging.getLogger(__name__)

# Expected embedding dimension for BGE-M3
EXPECTED_DIMENSION = 1024


class HuggingFaceProvider:
    """
    Embedding provider using HuggingFace Inference API (via InferenceClient).

    This provider only implements generate_embedding.
    For LLM operations, use GroqProvider.
    """

    def __init__(
        self,
        api_key: str,
        embedding_model: str = "BAAI/bge-m3",
        timeout: float = 30.0,
    ):
        """
        Initialize the HuggingFace provider.

        Args:
            api_key: HuggingFace API token (with inference permissions)
            embedding_model: Model to use for embeddings (default: BAAI/bge-m3)
            timeout: Request timeout in seconds (default: 30.0)
        """
        self._api_key = api_key
        self._embedding_model = embedding_model
        self._timeout = timeout
        self._client = InferenceClient(token=api_key, timeout=timeout)

    async def generate_embedding(self, text: str) -> Embedding:
        """
        Generate embedding using HuggingFace Inference API.

        Args:
            text: Input text to embed

        Returns:
            Embedding with 1024-dimensional vector

        Raises:
            ValueError: If the API response is invalid
            RuntimeError: If all retries fail
        """
        last_error: Exception | None = None
        max_retries = 3

        for attempt in range(max_retries + 1):
            try:
                # InferenceClient.feature_extraction is sync; run in thread
                vector = await asyncio.to_thread(
                    self._client.feature_extraction,
                    text=text,
                    model=self._embedding_model,
                )

                # Handle different response formats
                # feature_extraction may return:
                # - numpy.ndarray (flat or 2D)
                # - list (flat or 2D)
                if hasattr(vector, "tolist"):
                    vector = vector.tolist()

                # If 2D (one row per input text), take the first row
                if isinstance(vector, list) and vector and isinstance(vector[0], list):
                    vector = vector[0]

                if not isinstance(vector, list):
                    raise ValueError(f"Unexpected embedding type: {type(vector)}")

                if len(vector) != EXPECTED_DIMENSION:
                    raise ValueError(
                        f"Embedding dimension mismatch: expected {EXPECTED_DIMENSION}, "
                        f"got {len(vector)}"
                    )

                logger.info(
                    "HF embedding generated",
                    extra={
                        "model": self._embedding_model,
                        "dimension": len(vector),
                    },
                )

                return Embedding(
                    vector=vector,
                    model=self._embedding_model,
                    provider="huggingface",
                )

            except Exception as e:
                last_error = e
                error_msg = str(e).lower()

                # Detect rate limit / service unavailable for backoff
                if "429" in error_msg or "rate" in error_msg or "503" in error_msg or "loading" in error_msg:
                    wait_time = 2**attempt + 5
                    logger.warning(
                        "HF service issue, retrying",
                        extra={
                            "attempt": attempt + 1,
                            "wait_seconds": wait_time,
                            "error": str(e)[:200],
                        },
                    )
                else:
                    wait_time = 2**attempt
                    logger.warning(
                        "HF request error, retrying",
                        extra={
                            "attempt": attempt + 1,
                            "wait_seconds": wait_time,
                            "error": str(e)[:200],
                        },
                    )

                if attempt < max_retries:
                    await asyncio.sleep(wait_time)

        raise RuntimeError(f"HF API call failed after {max_retries + 1} attempts: {last_error}")

    async def generate_match(
        self,
        jd_text: str,
        profile_context: dict[str, Any],
    ) -> MatchAnalysis:
        """
        Generate match analysis is not supported by HuggingFace provider.

        Raises:
            NotImplementedError: Always, use GroqProvider for LLM operations
        """
        raise NotImplementedError(
            "HuggingFaceProvider only supports embeddings. Use GroqProvider for LLM operations."
        )
