"""
Composite provider that combines LLM and embedding providers.

This allows using different providers for LLM (Groq) and embeddings (HuggingFace).
"""
from typing import Any

from app.llm.base import LLMProvider
from app.llm.schemas import AdaptedCV, CVAudit, Embedding, MatchAnalysis


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

    async def generate_cv_audit(self, cv_text: str) -> CVAudit:
        """
        Generate CV quality audit using the LLM provider.

        Args:
            cv_text: The CV text to audit

        Returns:
            CVAudit with score, problematicas, recomendaciones, and fortalezas
        """
        return await self._llm.generate_cv_audit(cv_text)

    async def generate_adaptation(
        self,
        cv_structured: dict[str, Any],
        jd_text: str,
        *,
        max_tokens: int = 4000,
    ) -> AdaptedCV:
        """
        Generate CV -> JD adaptation using the LLM provider.

        Embeddings and LLM adaptation share the same provider in the
        composite (Groq + HF composite has the LLM side handle this).

        Args:
            cv_structured: Parsed CV in the same shape as ``UserCV.structured``.
            jd_text: Target job description.
            max_tokens: Per-call response token cap (default 4000).

        Returns:
            AdaptedCV instance.
        """
        return await self._llm.generate_adaptation(
            cv_structured, jd_text, max_tokens=max_tokens
        )

    async def generate_embedding(self, text: str) -> Embedding:
        """
        Generate embedding using the embedding provider.

        Args:
            text: Input text to embed

        Returns:
            Embedding with vector and model identifier
        """
        return await self._embeddings.generate_embedding(text)
