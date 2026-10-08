"""Servidor MCP para AsistCV (MCPServer del SDK mcp 2.x).

El SDK mcp 2.2.0 eliminó la API de decoradores del ``Server`` low-level
(el atributo ``list_tools`` ya no existe y los ``type: ignore`` lo ocultaban:
el adapter no podía construirse con el lock actual). La API high-level
bendecida en 2.x es ``MCPServer`` (el renombre de FastMCP), que registra
tools desde funciones tipadas y acepta ``instructions`` en el constructor —
que usamos para el grounding de fecha del issue #59.
"""

from datetime import UTC, datetime

import structlog
from mcp.server import MCPServer
from pydantic import Field

from . import tools
from .http_client import BackendClient
from .search_client import TavilyClient
from .ttl_cache import TTLCache

logger = structlog.get_logger(__name__)

# Cache en proceso compartido por todas las llamadas a web_search (issue #59):
# clave exacta de query, TTL 1h, tope de entradas en ttl_cache.TTLCache.
_WEB_SEARCH_CACHE = TTLCache(ttl_seconds=3600.0, max_entries=128)


def create_server(
    client: BackendClient,
    search_client: TavilyClient | None = None,
) -> MCPServer:
    """Crea el servidor MCP con las tools registradas.

    Args:
        client: Cliente HTTP hacia el backend.
        search_client: Cliente del proveedor de búsqueda web. Si es None se
            crea uno nuevo (lee TAVILY_API_KEY del entorno al primer uso).

    Returns:
        Instancia de MCPServer lista para correr sobre stdio.
    """
    search = search_client if search_client is not None else TavilyClient()
    today = datetime.now(UTC).date().isoformat()

    mcp = MCPServer(
        name="asistcv-mcp",
        instructions=(
            "Adapter MCP de AsistCV. "
            f"Fecha de hoy: {today}. "
            "Usá web_search cuando la consulta dependa de información que "
            "pudo cambiar después de tu fecha de corte de conocimiento."
        ),
    )

    @mcp.tool()
    async def ping() -> str:
        """Health check del adapter. Devuelve 'pong' si todo funciona."""
        return await tools.ping()

    @mcp.tool()
    async def get_health() -> str:
        """Llama al endpoint /health del backend y devuelve el status."""
        return await tools.get_health(client)

    @mcp.tool()
    async def evaluate_match(jd_text: str, profile_id: int = 1) -> str:
        """Evalúa el match entre una descripción de puesto (JD) y el perfil del usuario.

        Devuelve score, strengths, gaps, energy_level y reasoning.
        """
        return await tools.evaluate_match(client, jd_text=jd_text, profile_id=profile_id)

    @mcp.tool()
    async def web_search(
        query: str = Field(description="Consulta de búsqueda (ej: 'python frameworks 2026')"),
        max_results: int = Field(default=5, ge=1, le=10),
    ) -> str:
        """Busca en la web información actual (fechas, versiones, novedades).

        Compensa el corte de conocimiento del modelo. Devuelve resultados con
        título, snippet, link, score y fecha de publicación (puede ser nula).
        """
        return await tools.web_search(
            search,
            query=query,
            max_results=max_results,
            cache=_WEB_SEARCH_CACHE,
        )

    return mcp
