"""
Factory for creating LLM provider instances based on configuration.
"""
from functools import lru_cache

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.mock import MockProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    """
    Get the configured LLM provider instance.

    The provider is cached using lru_cache to ensure the same
    instance is reused across requests.

    Returns:
        An LLMProvider implementation based on settings.llm_provider

    Raises:
        ValueError: If the configured provider is not supported
    """
    settings = get_settings()
    provider_name = settings.llm_provider.lower()

    if provider_name == "mock":
        return MockProvider()
    elif provider_name == "vertex":
        # Import here to allow the module to load even without GCP SDK
        from app.llm.vertex import VertexAIProvider
        return VertexAIProvider()
    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider_name}'. "
            f"Supported providers: 'mock', 'vertex'. "
            f"Set LLM_PROVIDER environment variable."
        )
