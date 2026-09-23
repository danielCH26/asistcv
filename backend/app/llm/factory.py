"""
Factory for creating LLM provider instances based on configuration.
"""
from functools import lru_cache

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.composite import CompositeProvider
from app.llm.groq_provider import GroqProvider
from app.llm.huggingface_provider import HuggingFaceProvider
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
        ValueError: If the configured provider is not supported or credentials are missing
    """
    settings = get_settings()
    provider_name = settings.llm_provider.lower()

    if provider_name == "mock":
        return MockProvider()
    elif provider_name == "groq":
        if not settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is required when LLM_PROVIDER=groq. "
                "Set the GROQ_API_KEY environment variable."
            )
        if not settings.huggingface_api_key:
            raise ValueError(
                "HUGGINGFACE_API_KEY is required when LLM_PROVIDER=groq. "
                "Set the HUGGINGFACE_API_KEY environment variable for embeddings."
            )

        # Create composite provider: Groq for LLM, HuggingFace for embeddings
        llm = GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
        )
        embeddings = HuggingFaceProvider(
            api_key=settings.huggingface_api_key,
            embedding_model=settings.hf_embedding_model,
        )
        return CompositeProvider(llm_provider=llm, embedding_provider=embeddings)
    elif provider_name == "huggingface":
        if not settings.huggingface_api_key:
            raise ValueError(
                "HUGGINGFACE_API_KEY is required when LLM_PROVIDER=huggingface. "
                "Set the HUGGINGFACE_API_KEY environment variable."
            )
        return HuggingFaceProvider(
            api_key=settings.huggingface_api_key,
            embedding_model=settings.hf_embedding_model,
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider_name}'. "
            f"Supported providers: 'mock', 'groq', 'huggingface'. "
            f"Set LLM_PROVIDER environment variable."
        )


def get_llm_provider_cached() -> LLMProvider:
    """
    Get a cached LLM provider instance.

    This is an alias for get_llm_provider() to maintain backwards compatibility.
    """
    return get_llm_provider()
