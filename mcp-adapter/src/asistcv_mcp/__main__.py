"""Entry point del adapter MCP."""

import asyncio
import signal
import sys

import structlog

from .config import get_settings
from .http_client import BackendClient
from .server import create_server

# Configurar structlog. CRÍTICO: el stdout de este proceso ES el canal stdio
# del protocolo MCP — loguear ahí corrompe los mensajes JSON-RPC. Los logs
# van a stderr como JSON (issue #59: web_search_call con query, provider,
# latency_ms, num_results, cache_hit).
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(structlog, get_settings().log_level.upper(), structlog.INFO)
    ),
    logger_factory=structlog.WriteLoggerFactory(file=sys.stderr),
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger(__name__)


async def main() -> None:
    """Main entry point del servidor MCP."""
    logger.info("Starting AsistCV MCP adapter")

    # Crear cliente HTTP al backend
    client = BackendClient()

    # Crear servidor MCP
    server = create_server(client)

    # Manejo de shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(sig: int, frame: object) -> None:
        logger.info("Received shutdown signal", signal=sig)
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Iniciar con transporte stdio (estándar para MCP). MCPServer (2.x)
        # gestiona los streams internamente en run_stdio_async.
        logger.info("MCP server running on stdio")
        await server.run_stdio_async()
    except asyncio.CancelledError:
        logger.info("Server cancelled")
    except Exception as e:
        logger.error("Server error", error=str(e))
        raise
    finally:
        # Limpieza: cerrar cliente HTTP
        await client.close()
        logger.info("Adapter shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
