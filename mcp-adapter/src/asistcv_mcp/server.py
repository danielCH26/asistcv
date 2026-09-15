"""Servidor MCP para AsistCV."""

import structlog
from mcp.server import Server
from mcp.types import TextContent, Tool

from . import tools
from .http_client import BackendClient

logger = structlog.get_logger(__name__)


def create_server(client: BackendClient) -> Server:
    """Crea el servidor MCP con las tools registradas.

    Args:
        client: Cliente HTTP hacia el backend.

    Returns:
        Instancia del servidor MCP.
    """
    server = Server("asistcv-mcp")

    @server.list_tools()  # type: ignore[attr-defined,untyped-decorator]
    async def list_tools() -> list[Tool]:
        """Lista todas las tools disponibles."""
        return [
            Tool(
                name="ping",
                description="Health check del adapter. Devuelve 'pong' si todo funciona.",
                input_schema={"type": "object", "properties": {}},
            ),
            Tool(
                name="evaluate_match",
                description=(
                    "Evalúa el match entre una descripción de puesto (JD) y el perfil del usuario. "
                    "Devuelve score, strengths, gaps, energy_level y reasoning."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "jd_text": {
                            "type": "string",
                            "description": "Texto completo de la descripción del puesto",
                            "minLength": 50,
                        },
                        "profile_id": {
                            "type": "integer",
                            "description": "ID del perfil a usar",
                            "default": 1,
                        },
                    },
                    "required": ["jd_text"],
                },
            ),
            Tool(
                name="get_health",
                description="Llama al endpoint /health del backend y devuelve el status.",
                input_schema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()  # type: ignore[attr-defined,untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, object] | None) -> list[TextContent]:
        """Ejecuta una tool por nombre.

        Args:
            name: Nombre de la tool a ejecutar.
            arguments: Argumentos para la tool.

        Returns:
            Lista de resultados en formato TextContent.
        """
        logger.debug("Tool called", name=name, arguments=arguments)

        try:
            if name == "ping":
                result = await tools.ping()
                return [TextContent(type="text", text=result)]

            elif name == "get_health":
                result = await tools.get_health(client)
                return [TextContent(type="text", text=result)]

            elif name == "evaluate_match":
                jd_text = str(arguments.get("jd_text", "")) if arguments else ""
                profile_id_arg = arguments.get("profile_id", 1) if arguments else 1
                profile_id = int(profile_id_arg) if profile_id_arg else 1  # type: ignore[call-overload]
                result = await tools.evaluate_match(client, jd_text=jd_text, profile_id=profile_id)
                return [TextContent(type="text", text=result)]

            else:
                raise ValueError(f"Unknown tool: {name}")

        except ValueError as e:
            logger.error("Validation error in tool", name=name, error=str(e))
            raise
        except Exception as e:
            logger.error("Error executing tool", name=name, error=str(e))
            raise

    return server
