"""Cliente HTTP para el proveedor de búsqueda web (Tavily) — issue #59.

Dedicado (no reutiliza ``BackendClient``): otra base URL, otra autenticación
(``api_key`` en el body, no Bearer), y otra taxonomía de errores. Tavily
devuelve ``published_date`` con frecuencia nula en búsquedas generales, así
que la forma normalizada la trata como ``str | None``.
"""

from __future__ import annotations

from typing import NoReturn

import httpx
import structlog

from .config import get_settings

logger = structlog.get_logger(__name__)

_TAVILY_BASE_URL = "https://api.tavily.com"


class SearchError(Exception):
    """Error recibido del proveedor de búsqueda."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SearchAuthError(SearchError):
    """API key ausente o inválida (401)."""

    def __init__(
        self,
        message: str = "API key del proveedor de búsqueda inválida",
        status_code: int = 401,
    ) -> None:
        super().__init__(message, status_code=status_code)


class SearchRateLimitError(SearchError):
    """Límite de tasa del proveedor (429)."""

    def __init__(
        self,
        message: str = "Límite de búsquedas alcanzado",
        status_code: int = 429,
        retry_after: int | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, status_code=status_code)


class SearchTimeoutError(SearchError):
    """Timeout al comunicarse con el proveedor."""

    def __init__(self) -> None:
        super().__init__("Timeout al comunicarse con el proveedor de búsqueda")


class SearchConnectionError(SearchError):
    """Error de conexión con el proveedor."""

    def __init__(self, message: str = "No se pudo conectar con el proveedor de búsqueda") -> None:
        super().__init__(message)


class TavilyClient:
    """Cliente HTTP async para la API de Tavily."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.tavily_api_key
        self._timeout = settings.timeout_seconds
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=_TAVILY_BASE_URL,
                timeout=self._timeout,
            )
        return self._client

    @staticmethod
    def _raise_for_status_error(exc: httpx.HTTPStatusError) -> NoReturn:
        status_code = exc.response.status_code
        if status_code == 401:
            logger.error("Search auth error", status=status_code)
            raise SearchAuthError() from None
        if status_code == 429:
            retry_after: int | None = None
            raw = exc.response.headers.get("Retry-After")
            if raw is not None:
                try:
                    retry_after = int(raw)
                except ValueError:
                    retry_after = None
            logger.error("Search rate limited", status=status_code, retry_after=retry_after)
            raise SearchRateLimitError(retry_after=retry_after) from None
        logger.error("Search error", status=status_code, detail=exc.response.text)
        raise SearchError(
            f"Error del proveedor de búsqueda: {exc.response.text}",
            status_code=status_code,
        )

    async def search(self, query: str, max_results: int = 5) -> dict[str, object]:
        """Busca en Tavily y devuelve la forma normalizada de la tool."""
        if not self._api_key:
            raise ValueError("web_search no configurado: falta TAVILY_API_KEY.")
        client = await self._get_client()
        try:
            logger.debug("Calling tavily search", query_length=len(query), max_results=max_results)
            response = await client.post(
                "/search",
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e)
        except httpx.TimeoutException:
            logger.error("Search timeout")
            raise SearchTimeoutError() from None
        except httpx.ConnectError as e:
            logger.error("Search connection error", error=str(e))
            raise SearchConnectionError() from None

        data = response.json()
        normalized: list[dict[str, object]] = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score"),
                "published_date": item.get("published_date"),
            }
            for item in data.get("results", [])
        ]
        return {
            "query": data.get("query", query),
            "provider": "tavily",
            "results": normalized,
        }

    async def close(self) -> None:
        """Cierra el cliente HTTP."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.debug("Search client closed")
