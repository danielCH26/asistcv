"""
Offer search client using Tavily API — issue #55.

POST https://api.tavily.com with api_key in the body (not Bearer).
Error taxonomy mirrors the MCP adapter pattern but lives in this package
to avoid cross-package imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

import httpx

_TAVILY_BASE_URL = "https://api.tavily.com"
_DEFAULT_TIMEOUT = 12.0  # seconds


@dataclass
class OfferSearchResult:
    """Normalized search result for job offers."""

    title: str
    url: str
    snippet: str
    published_date: str | None


class OfferSearchError(Exception):
    """Base error from the offer search provider."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class OfferSearchAuthError(OfferSearchError):
    """API key invalid or missing (401)."""

    def __init__(
        self,
        message: str = "API key del proveedor de búsqueda inválida",
        status_code: int = 401,
    ) -> None:
        super().__init__(message, status_code=status_code)


class OfferSearchRateLimitError(OfferSearchError):
    """Rate limit from provider (429)."""

    def __init__(
        self,
        message: str = "Límite de búsquedas alcanzado",
        status_code: int = 429,
        retry_after: int | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, status_code=status_code)


class OfferSearchTimeoutError(OfferSearchError):
    """Timeout communicating with the provider."""

    def __init__(self) -> None:
        super().__init__("Timeout al comunicarse con el proveedor de búsqueda")


class OfferSearchConnectionError(OfferSearchError):
    """Connection error with the provider."""

    def __init__(self, message: str = "No se pudo conectar con el proveedor de búsqueda") -> None:
        super().__init__(message)


class TavilyOfferSearchClient:
    """Async client for Tavily offer search API."""

    def __init__(self, api_key: str, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._api_key = api_key
        self._timeout = timeout
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
            raise OfferSearchAuthError() from None
        if status_code == 429:
            retry_after: int | None = None
            raw = exc.response.headers.get("Retry-After")
            if raw is not None:
                try:
                    retry_after = int(raw)
                except ValueError:
                    retry_after = None
            raise OfferSearchRateLimitError(retry_after=retry_after) from None
        raise OfferSearchError(
            f"Error del proveedor de búsqueda: {exc.response.text}",
            status_code=status_code,
        )

    async def search(self, query: str, max_results: int = 10) -> list[OfferSearchResult]:
        """Search for job offers and return normalized results."""
        if not self._api_key:
            raise ValueError("offer_search no configurado: falta TAVILY_API_KEY.")
        client = await self._get_client()
        try:
            response = await client.post(
                "/search",
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    "include_answer": False,
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e)
        except httpx.TimeoutException:
            raise OfferSearchTimeoutError() from None
        except httpx.ConnectError as e:
            raise OfferSearchConnectionError(str(e)) from None

        data = response.json()
        return [
            OfferSearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                published_date=item.get("published_date"),
            )
            for item in data.get("results", [])
        ]

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
