"""Entry point del adapter MCP."""

import asyncio
import signal

import mcp.server.stdio
import structlog

from .config import get_settings
from .http_client import BackendClient
from .server import create_server

# Configurar structlog
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(structlog, get_settings().log_level.upper(), structlog.INFO)
    ),
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
        # Iniciar con transporte stdio (estándar para MCP)
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            logger.info("MCP server running on stdio")
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
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
