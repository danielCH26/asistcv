"""
Composite provider that combines LLM and embedding providers.

This allows using different providers for LLM (Groq) and embeddings (HuggingFace).
"""
from typing import Any

from app.llm.base import LLMProvider
from app.llm.schemas import Embedding, MatchAnalysis


class CompositeProvider:
    """
    Composes separate LLM and embedding providers.

    This enables using:
    - Groq for LLM operations (generate_match)
    - HuggingFace for embedding operations (generate_embedding)
    """

    def __init__(self, llm_provider: LLMProvider, embedding_provider: LLMProvider):
        """
        Initialize the composite provider.

        Args:
            llm_provider: Provider for LLM operations (generate_match)
            embedding_provider: Provider for embedding operations (generate_embedding)
        """
        self._llm = llm_provider
        self._embeddings = embedding_provider

    async def generate_match(
        self,
        jd_text: str,
        profile_context: dict[str, Any],
    ) -> MatchAnalysis:
        """
        Generate match analysis using the LLM provider.

        Args:
            jd_text: The job description text
            profile_context: Context information about the candidate

        Returns:
            MatchAnalysis with score, strengths, gaps, energy level, and reasoning
        """
        return await self._llm.generate_match(jd_text, profile_context)

    async def generate_embedding(self, text: str) -> Embedding:
        """
        Generate embedding using the embedding provider.

        Args:
            text: Input text to embed

        Returns:
            Embedding with vector and model identifier
        """
        return await self._embeddings.generate_embedding(text)
