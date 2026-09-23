"""
HuggingFace provider implementation for embedding operations.

This provider uses the HuggingFace Inference API for embeddings.
"""
import asyncio
import logging
from typing import Any

import httpx

from app.llm.schemas import Embedding, MatchAnalysis

logger = logging.getLogger(__name__)

# HF Inference API endpoint for BGE-M3
HF_EMBEDDING_URL = "https://api-inference.huggingface.co/models/BAAI/bge-m3"

# Expected embedding dimension for BGE-M3
EXPECTED_DIMENSION = 1024


class HuggingFaceProvider:
    """
    Embedding provider using HuggingFace Inference API.

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
            api_key: HuggingFace API token (with Read permission)
            embedding_model: Model to use for embeddings (default: BAAI/bge-m3)
            timeout: Request timeout in seconds (default: 30.0)
        """
        self._api_key = api_key
        self._embedding_model = embedding_model
        self._timeout = timeout
        self._max_retries = 3

    async def generate_embedding(self, text: str) -> Embedding:
        """
        Generate embedding using HuggingFace Inference API.

        Args:
            text: Input text to embed

        Returns:
            Embedding with 1024-dimensional vector

        Raises:
            ValueError: If the API response is invalid
            httpx.HTTPStatusError: If the API returns an error
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {"inputs": text}

        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        HF_EMBEDDING_URL,
                        headers=headers,
                        json=payload,
                    )

                    if response.status_code == 429:
                        # Rate limit - exponential backoff
                        wait_time = 2**attempt
                        logger.warning(
                            "HF rate limit hit, retrying",
                            extra={"attempt": attempt + 1, "wait_seconds": wait_time},
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    response.raise_for_status()

                    # httpx 0.28+ may return a coroutine for .json()
                    data = response.json()
                    # Check if it's a coroutine and await it
                    if asyncio.iscoroutine(data):
                        data = await data

                    # BGE-M3 returns a list of embeddings (we sent one text)
                    if not isinstance(data, list) or len(data) == 0:
                        raise ValueError(f"Invalid HF response format: {type(data)}")

                    embedding_data = data[0]

                    # Extract the embedding vector
                    if isinstance(embedding_data, dict):
                        vector = embedding_data.get("embedding")
                        if vector is None:
                            raise ValueError("No embedding found in response")
                    elif isinstance(embedding_data, list):
                        vector = embedding_data
                    else:
                        raise ValueError(f"Unexpected embedding format: {type(embedding_data)}")

                    # Validate dimension
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

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 503:
                    # Service unavailable - model might be loading
                    wait_time = 2**attempt + 5  # Extra wait for model loading
                    logger.warning(
                        "HF service unavailable, retrying",
                        extra={"attempt": attempt + 1, "wait_seconds": wait_time},
                    )
                    await asyncio.sleep(wait_time)
                    last_error = e
                else:
                    raise

            except httpx.RequestError as e:
                last_error = e
                wait_time = 2**attempt
                logger.warning(
                    "HF request error, retrying",
                    extra={"attempt": attempt + 1, "wait_seconds": wait_time, "error": str(e)},
                )
                await asyncio.sleep(wait_time)

        raise last_error or RuntimeError("HF API call failed after retries")

    async def generate_match(
        self,
        jd_text: str,
        profile_context: dict[str, Any],
    ) -> MatchAnalysis:
        """
        Generate match analysis is not supported by HuggingFace provider.

        Args:
            jd_text: The job description text
            profile_context: Context information about the candidate

        Raises:
            NotImplementedError: Always, use GroqProvider for LLM operations
        """
        raise NotImplementedError(
            "HuggingFaceProvider only supports embeddings. Use GroqProvider for LLM operations."
        )
