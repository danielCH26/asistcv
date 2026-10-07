"""Tests del cliente Tavily y del cache TTL (T1 de feat-mcp-web-search).

El proveedor se mockea con ``httpx.MockTransport`` — convención del repo (no
hay ``respx``). La forma de la respuesta es el criterio de aceptación del
issue #59: snippet + link + fecha, con ``published_date`` tolerante a null.
"""

from __future__ import annotations

import json

import httpx
import pytest

from asistcv_mcp.config import Settings
from asistcv_mcp.search_client import (
    SearchAuthError,
    SearchConnectionError,
    SearchError,
    SearchRateLimitError,
    SearchTimeoutError,
    TavilyClient,
)
from asistcv_mcp.ttl_cache import TTLCache


def _settings_with_key() -> Settings:
    return Settings(tavily_api_key="tvly-test-key", web_search_provider="tavily")


def _tavily_response_payload() -> dict[str, object]:
    return {
        "query": "python frameworks 2026",
        "results": [
            {
                "title": "FastAPI release notes",
                "url": "https://fastapi.tiangolo.com/release-notes/",
                "content": "FastAPI 0.200 adds…",
                "score": 0.93,
                "published_date": "2026-09-01",
            },
            {
                "title": "No-date result",
                "url": "https://example.com/no-date",
                "content": "Tavily often omits the date.",
                "score": 0.71,
                "published_date": None,
            },
        ],
    }


def _mock_client(handler) -> TavilyClient:
    """Construye un TavilyClient cuyo httpx.AsyncClient usa MockTransport."""
    import asistcv_mcp.search_client as search_client_module

    # Si get_settings todavía es el original cacheado, limpiar el cache; si
    # ya fue reemplazado por el monkeypatch del fixture, es una función plana.
    cache_clear = getattr(search_client_module.get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    client = TavilyClient()
    client._client = httpx.AsyncClient(  # noqa: SLF001 — inyección de test
        base_url="https://api.tavily.com",
        transport=httpx.MockTransport(handler),
    )
    return client


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "asistcv_mcp.search_client.get_settings", _settings_with_key
    )


class TestTavilyClientShape:
    async def test_search_returns_normalized_shape_with_null_date(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_tavily_response_payload())

        client = _mock_client(handler)
        result = await client.search("python frameworks 2026", max_results=2)

        assert set(result.keys()) == {"query", "provider", "results"}
        assert result["provider"] == "tavily"
        assert result["query"] == "python frameworks 2026"
        results = result["results"]
        assert isinstance(results, list) and len(results) == 2
        first = results[0]
        assert set(first.keys()) == {"title", "url", "content", "score", "published_date"}
        assert first["published_date"] == "2026-09-01"
        assert results[1]["published_date"] is None

        # Auth de Tavily: api_key en el body (método canónico documentado).
        body = captured["body"]
        assert isinstance(body, dict)
        assert body["api_key"] == "tvly-test-key"
        assert body["query"] == "python frameworks 2026"
        assert body["max_results"] == 2

    async def test_401_maps_to_search_auth_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "invalid api key"})

        client = _mock_client(handler)
        with pytest.raises(SearchAuthError):
            await client.search("query", max_results=5)

    async def test_429_maps_to_search_rate_limit_error_with_retry_after(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429, json={"detail": "rate limited"}, headers={"Retry-After": "120"}
            )

        client = _mock_client(handler)
        with pytest.raises(SearchRateLimitError) as exc_info:
            await client.search("query", max_results=5)
        assert exc_info.value.retry_after == 120

    async def test_500_maps_to_generic_search_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "boom"})

        client = _mock_client(handler)
        with pytest.raises(SearchError) as exc_info:
            await client.search("query", max_results=5)
        assert not isinstance(exc_info.value, SearchAuthError | SearchRateLimitError)

    async def test_timeout_maps_to_search_timeout_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        client = _mock_client(handler)
        with pytest.raises(SearchTimeoutError):
            await client.search("query", max_results=5)

    async def test_connect_error_maps_to_search_connection_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        client = _mock_client(handler)
        with pytest.raises(SearchConnectionError):
            await client.search("query", max_results=5)


class TestTavilyClientKeyGuard:
    async def test_missing_api_key_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "asistcv_mcp.search_client.get_settings",
            lambda: Settings(tavily_api_key=None),
        )
        client = TavilyClient()
        with pytest.raises(ValueError, match="TAVILY_API_KEY"):
            await client.search("query", max_results=5)


class TestTTLCache:
    def _cache(self, ttl: float = 3600.0) -> TTLCache:
        return TTLCache(ttl_seconds=ttl, max_entries=128)

    def test_miss_returns_none_hit_returns_value(self) -> None:
        cache = self._cache()
        assert cache.get("query") is None
        value = {"provider": "tavily", "results": []}
        cache.set("query", value)
        assert cache.get("query") == value

    def test_expired_entry_is_a_miss(self) -> None:
        current = {"t": 1000.0}
        cache = TTLCache(ttl_seconds=60.0, max_entries=8, now_fn=lambda: current["t"])
        cache.set("q", {"results": []})
        current["t"] = 1061.0  # > ttl
        assert cache.get("q") is None

    def test_exact_query_keying_distinct_strings(self) -> None:
        cache = self._cache()
        cache.set("Python", {"n": 1})
        cache.set("python", {"n": 2})
        assert cache.get("Python") == {"n": 1}
        assert cache.get("python") == {"n": 2}

    def test_evicts_oldest_beyond_capacity(self) -> None:
        cache = TTLCache(ttl_seconds=3600.0, max_entries=2, now_fn=lambda: 1000.0)
        cache.set("a", {"v": "a"})
        cache.set("b", {"v": "b"})
        cache.set("c", {"v": "c"})  # expulsa a "a"
        assert cache.get("a") is None
        assert cache.get("b") == {"v": "b"}
        assert cache.get("c") == {"v": "c"}
