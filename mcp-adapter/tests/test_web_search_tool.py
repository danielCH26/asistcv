"""Tests de la tool ``web_search`` (T2 de feat-mcp-web-search).

Capa de tools: el cliente de búsqueda se mockea con ``AsyncMock`` (convención
del repo); el cache es el ``TTLCache`` real con instancia propia por test.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from asistcv_mcp import tools
from asistcv_mcp.config import Settings
from asistcv_mcp.ttl_cache import TTLCache


def _search_client() -> AsyncMock:
    client = AsyncMock()
    client.search.return_value = {
        "query": "python frameworks 2026",
        "provider": "tavily",
        "results": [
            {
                "title": "FastAPI release notes",
                "url": "https://fastapi.tiangolo.com/release-notes/",
                "content": "FastAPI 0.200 adds…",
                "score": 0.93,
                "published_date": "2026-09-01",
            }
        ],
    }
    return client


@pytest.fixture(autouse=True)
def _tavily_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "asistcv_mcp.tools.get_settings",
        lambda: Settings(web_search_provider="tavily", tavily_api_key="tvly-test-key"),
    )


class TestWebSearchTool:
    async def test_returns_json_shape_with_provider_and_results(self) -> None:
        client = _search_client()
        out = await tools.web_search(client, "python frameworks 2026", 5, cache=TTLCache(3600))

        data = json.loads(out)
        assert set(data.keys()) == {"query", "provider", "results"}
        assert data["provider"] == "tavily"
        assert data["results"][0]["url"] == "https://fastapi.tiangolo.com/release-notes/"

    async def test_cache_hit_skips_second_provider_call(self) -> None:
        client = _search_client()
        cache = TTLCache(3600)

        await tools.web_search(client, "misma query", 5, cache=cache)
        await tools.web_search(client, "misma query", 5, cache=cache)

        assert client.search.call_count == 1

    async def test_different_queries_call_provider_each_time(self) -> None:
        client = _search_client()
        cache = TTLCache(3600)

        await tools.web_search(client, "query uno", 5, cache=cache)
        await tools.web_search(client, "query dos", 5, cache=cache)

        assert client.search.call_count == 2

    async def test_max_results_clamped_to_schema_bounds(self) -> None:
        client = _search_client()
        cache = TTLCache(3600)

        await tools.web_search(client, "q alta", 99, cache=cache)
        assert client.search.call_args.kwargs["max_results"] == 10

        await tools.web_search(client, "q baja", 0, cache=cache)
        assert client.search.call_args.kwargs["max_results"] == 1

    async def test_missing_api_key_error_propagates_as_value_error(self) -> None:
        client = _search_client()
        client.search.side_effect = ValueError(
            "web_search no configurado: falta TAVILY_API_KEY."
        )
        cache = TTLCache(3600)

        with pytest.raises(ValueError, match="TAVILY_API_KEY"):
            await tools.web_search(client, "q", 5, cache=cache)

    async def test_unknown_provider_raises_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "asistcv_mcp.tools.get_settings",
            lambda: Settings(web_search_provider="brave"),
        )
        client = _search_client()

        with pytest.raises(ValueError, match="tavily"):
            await tools.web_search(client, "q", 5, cache=TTLCache(3600))


class TestWebSearchRegistration:
    async def test_registered_tools_include_web_search_with_schema(self) -> None:
        from asistcv_mcp.server import create_server

        server = create_server(AsyncMock(), _search_client())
        registered = await server.list_tools()
        tools_list = registered.tools if hasattr(registered, "tools") else registered
        names = [t.name for t in tools_list]
        for expected in ("ping", "evaluate_match", "get_health", "web_search"):
            assert expected in names

        schema = next(t for t in tools_list if t.name == "web_search").input_schema
        assert schema is not None
        assert "query" in schema["properties"]
        assert schema["required"] == ["query"]

    def test_server_instructions_carry_today_date(self) -> None:
        """S6: el grounding de fecha viaja en las instructions del server."""
        from datetime import UTC, datetime

        from asistcv_mcp.server import create_server

        server = create_server(AsyncMock(), _search_client())
        today = datetime.now(UTC).date().isoformat()
        assert today in (server.instructions or "")
