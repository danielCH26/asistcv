"""
LLM Provider interface definitions.
"""
from typing import Any, Protocol, runtime_checkable

from app.llm.schemas import AdaptedCV, CVAudit, Embedding, MatchAnalysis


@runtime_checkable
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

    async def generate_adaptation(
        self,
        cv_structured: dict[str, Any],
        jd_text: str,
        *,
        max_tokens: int = 4000,
    ) -> AdaptedCV:
        """
        Adapt a structured CV to a target job description.

        Slice A (sprint-adapt-cv-outreach, PR2): rewrites experience
        bullets to highlight JD relevance while preserving every fact
        present in the source. The provider is responsible for emitting
        strict JSON conforming to ``AdaptedCV``; the validator downstream
        enforces the no-honesty-violation contract.

        Args:
            cv_structured: Parsed CV in the same shape as
                ``UserCV.structured`` (full_name, experience[*], skills,
                education, languages).
            jd_text: Target job description (free text).
            max_tokens: Cap on response tokens. Default 4000 because a
                full adapted CV with rewritten bullets needs more
                headroom than a match analysis (800).

        Returns:
            AdaptedCV with rewritten experience[*].description and
            verbatim copies of metadata fields.

        Raises:
            ValueError: When the provider response cannot be parsed as
                valid ``AdaptedCV`` JSON after retries.
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
