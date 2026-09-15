"""
Vertex AI provider stub.

This is a placeholder for future implementation in Sprint 1 (issue #15).
Currently raises NotImplementedError to indicate the provider is not yet available.
"""
from typing import Any

from app.llm.schemas import Embedding, MatchAnalysis


class VertexAIProvider:
    """
    Stub implementation for Vertex AI provider.

    This provider will be implemented in Sprint 1 (issue #15) when
    GCP credentials and billing are available.
    """

    def __init__(self):
        """Initialize the Vertex AI provider stub."""
        # In the future, this will initialize the Vertex AI client
        # For now, we just raise an error to indicate it's not implemented
        raise NotImplementedError(
            "VertexAIProvider will be implemented in Sprint 1 issue #15. "
            "Use LLM_PROVIDER=mock for local development without GCP credentials."
        )

    async def generate_match(
        self,
        jd_text: str,
        profile_context: dict[str, Any],
    ) -> MatchAnalysis:
        """Generate match analysis using Vertex AI (not implemented)."""
        raise NotImplementedError(
            "VertexAIProvider will be implemented in Sprint 1 issue #15. "
            "Use LLM_PROVIDER=mock for local development."
        )

    async def generate_embedding(self, text: str) -> Embedding:
        """Generate embedding using Vertex AI (not implemented)."""
        raise NotImplementedError(
            "VertexAIProvider will be implemented in Sprint 1 issue #15. "
            "Use LLM_PROVIDER=mock for local development."
        )
