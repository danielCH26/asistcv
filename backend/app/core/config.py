"""
Configuration management using pydantic-settings.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "AsistCV Backend"
    environment: str = Field(default="development", validation_alias="APP_ENV")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:8000"]
    )
    api_prefix: str = "/v1"
    database_url: str = "postgresql+psycopg://asistcv:asistcv@localhost:5432/asistcv"
    llm_provider: str = Field(default="mock", validation_alias="LLM_PROVIDER")
    backend_api_key: str | None = Field(default=None, validation_alias="BACKEND_API_KEY")

    # Groq configuration
    groq_api_key: str | None = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", validation_alias="GROQ_MODEL")

    # HuggingFace configuration
    huggingface_api_key: str | None = Field(
        default=None, validation_alias="HUGGINGFACE_API_KEY"
    )
    hf_embedding_model: str = Field(
        default="BAAI/bge-m3", validation_alias="HF_EMBEDDING_MODEL"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings singleton."""
    return Settings()
