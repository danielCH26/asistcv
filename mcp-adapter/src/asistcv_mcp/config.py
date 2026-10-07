"""Configuración del adapter MCP."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración del adapter MCP."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    backend_url: str = "https://asistcv-backend.onrender.com"
    backend_api_key: str | None = None
    log_level: str = "INFO"
    timeout_seconds: float = 60.0

    # Búsqueda web (issue #59). Proveedor único en v1.0: "tavily".
    web_search_provider: str = "tavily"
    tavily_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Retorna la configuración cacheada."""
    return Settings()
