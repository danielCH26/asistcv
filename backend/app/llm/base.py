"""
LLM Provider interface definitions.
"""
from typing import Any, Protocol

from app.llm.schemas import CVAudit, Embedding, MatchAnalysis


class LLMProvider(Protocol):
    """
    Protocol defining the interface for LLM providers.

    This enables duck typing: any class implementing these methods
    can be used as an LLM provider without inheritance.
    """

    async def generate_match(
        self,
        jd_text: str,
        profile_context: dict[str, Any],
    ) -> MatchAnalysis:
        """
        Generate match analysis between a job description and a profile.

        Args:
            jd_text: The job description text
            profile_context: Context information about the candidate profile

        Returns:
            MatchAnalysis with score, strengths, gaps, energy level, and reasoning
        """
        ...

    async def generate_cv_audit(self, cv_text: str) -> CVAudit:
        """
        Generate a CV quality audit without a job description.

        Args:
            cv_text: The CV text to audit

        Returns:
            CVAudit with score, problematicas, recomendaciones, and fortalezas
        """
        ...

    async def generate_embedding(self, text: str) -> Embedding:
        """
        Generate embedding vector for the given text.

        Args:
            text: Input text to embed

        Returns:
            Embedding with vector and model identifier
        """
        ...
