"""
Configuration management using pydantic-settings.

NOTE on list-type env vars (cors_origins, etc.): pydantic-settings parses
env vars as JSON for list types, BEFORE any field validator runs.
So `CORS_ORIGINS` must be set as a JSON array string:
  CORS_ORIGINS='["http://localhost:5173","http://localhost:8000"]'
NOT as CSV. The default below is used when the env var is not set.
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
        default=["http://localhost:5173", "http://localhost:8000"],
    )
    api_prefix: str = "/v1"
    database_url: str = "postgresql://asistcv:asistcv@localhost:5433/asistcv"
    llm_provider: str = Field(default="mock", validation_alias="LLM_PROVIDER")
    backend_api_key: str | None = Field(default=None, validation_alias="BACKEND_API_KEY")

    # Groq configuration
    groq_api_key: str | None = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_model: str = Field(default="qwen/qwen3.8-27b", validation_alias="GROQ_MODEL")

    # HuggingFace configuration
    huggingface_api_key: str | None = Field(
        default=None, validation_alias="HUGGINGFACE_API_KEY"
    )
    hf_embedding_model: str = Field(
        default="BAAI/bge-m3", validation_alias="HF_EMBEDDING_MODEL"
    )

    # Retrieval configuration (PR-C, issue #16)
    retrieval_size_threshold_chars: int = Field(
        default=3000, validation_alias="RETRIEVAL_SIZE_THRESHOLD_CHARS"
    )
    retrieval_top_k: int = Field(default=8, validation_alias="RETRIEVAL_TOP_K")
    retrieval_fragment_target_chars: int = Field(
        default=500, validation_alias="RETRIEVAL_FRAGMENT_TARGET_CHARS"
    )

    # JWT configuration
    jwt_secret: str = Field(default="dev-secret-change-in-production", validation_alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    jwt_access_ttl: int = Field(default=900, validation_alias="JWT_ACCESS_TTL")  # 15 minutes
    jwt_refresh_ttl: int = Field(default=2592000, validation_alias="JWT_REFRESH_TTL")  # 30 days

    # Audit configuration (PR3)
    audit_cleanup_token: str | None = Field(default=None, validation_alias="AUDIT_CLEANUP_TOKEN")

    # Stripe billing configuration (PR5)
    stripe_secret_key: str | None = Field(default=None, validation_alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, validation_alias="STRIPE_WEBHOOK_SECRET")
    frontend_url: str = Field(default="http://localhost:5173", validation_alias="FRONTEND_URL")

    # Stripe price IDs for plans
    stripe_price_job_seeker_monthly: str = Field(
        default="price_job_seeker_monthly", validation_alias="STRIPE_PRICE_JOB_SEEKER_MONTHLY"
    )
    stripe_price_recruiter_starter: str = Field(
        default="price_recruiter_starter", validation_alias="STRIPE_PRICE_RECRUITER_STARTER"
    )
    stripe_price_recruiter_business: str = Field(
        default="price_recruiter_business", validation_alias="STRIPE_PRICE_RECRUITER_BUSINESS"
    )
    stripe_price_recruiter_agency: str = Field(
        default="price_recruiter_agency", validation_alias="STRIPE_PRICE_RECRUITER_AGENCY"
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
