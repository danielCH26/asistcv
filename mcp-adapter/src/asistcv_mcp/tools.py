"""Herramientas MCP expuestas por el adapter."""

import json
import time

import structlog

from .config import get_settings
from .http_client import (
    BackendClient,
    BackendConnectionError,
    BackendError,
    BackendTimeoutError,
)
from .search_client import TavilyClient
from .ttl_cache import TTLCache

logger = structlog.get_logger(__name__)


async def ping() -> str:
    """Health check del adapter.

    Returns:
        'pong' si todo funciona correctamente.
    """
    logger.debug("ping called")
    return "pong"


async def get_health(client: BackendClient) -> str:
    """Llama al endpoint /health del backend.

    Args:
        client: Cliente HTTP hacia el backend.

    Returns:
        JSON string con la respuesta del backend.
    """
    logger.debug("get_health called")
    try:
        result = await client.get_health()
        return json.dumps(result)
    except BackendTimeoutError:
        logger.error("Timeout in get_health")
        raise RuntimeError("Timeout al comunicarse con el backend")
    except BackendConnectionError as e:
        logger.error("Connection error in get_health", error=e.message)
        raise RuntimeError(f"Error de conexión: {e.message}")
    except BackendError as e:
        logger.error("Backend error in get_health", error=e.message)
        raise RuntimeError(f"Error del backend: {e.message}")


async def evaluate_match(client: BackendClient, jd_text: str, profile_id: int = 1) -> str:
    """Evalúa el match entre una descripción de puesto y el perfil del usuario.

    Args:
        client: Cliente HTTP hacia el backend.
        jd_text: Texto completo de la descripción del puesto (mínimo 50 caracteres).
        profile_id: ID del perfil a usar (default 1).

    Returns:
        JSON string con score, strengths, gaps, energy_level y reasoning.
    """
    logger.debug("evaluate_match called", profile_id=profile_id, jd_length=len(jd_text))

    # Validar que jd_text tenga mínimo 50 caracteres
    if len(jd_text) < 50:
        raise ValueError("jd_text debe tener al menos 50 caracteres")

    try:
        result = await client.evaluate_match(jd_text=jd_text, profile_id=profile_id)
        return json.dumps(result)
    except BackendTimeoutError:
        logger.error("Timeout in evaluate_match")
        raise RuntimeError("Timeout al comunicarse con el backend")
    except BackendConnectionError as e:
        logger.error("Connection error in evaluate_match", error=e.message)
        raise RuntimeError(f"Error de conexión: {e.message}")
    except BackendError as e:
        logger.error("Backend error in evaluate_match", error=e.message)
        raise RuntimeError(f"Error del backend: {e.message}")


async def web_search(
    search_client: TavilyClient,
    query: str,
    max_results: int = 5,
    cache: TTLCache | None = None,
) -> str:
    """Busca en la web para grounding temporal del LLM (issue #59).

    Args:
        search_client: Cliente del proveedor de búsqueda (Tavily).
        query: Consulta literal para el proveedor (clave exacta del cache).
        max_results: Cantidad de resultados (1-10; se recorta al rango).
        cache: Cache TTL compartido en proceso; None desactiva el cache.

    Returns:
        JSON string con query, provider y results (cada uno con title, url,
        content, score, published_date — este último frecuentemente null en
        búsquedas generales).
    """
    provider = get_settings().web_search_provider
    if provider != "tavily":
        raise ValueError(
            f"WEB_SEARCH_PROVIDER={provider!r} no soportado en v1.0; use 'tavily'."
        )

    clamped = max(1, min(10, int(max_results)))
    started = time.monotonic()
    cache_hit = False
    result: dict[str, object] | None = cache.get(query) if cache is not None else None
    if result is not None:
        cache_hit = True
    else:
        result = await search_client.search(query, max_results=clamped)
        if cache is not None:
            cache.set(query, result)

    latency_ms = round((time.monotonic() - started) * 1000, 1)
    results = result.get("results", [])
    logger.info(
        "web_search_call",
        query=query,
        provider=result.get("provider", "tavily"),
        latency_ms=latency_ms,
        num_results=len(results) if isinstance(results, list) else 0,
        cache_hit=cache_hit,
    )
    return json.dumps(result, ensure_ascii=False)
