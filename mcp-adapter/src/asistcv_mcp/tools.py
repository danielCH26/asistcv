"""Herramientas MCP expuestas por el adapter."""

import json

import structlog

from .http_client import (
    BackendClient,
    BackendConnectionError,
    BackendError,
    BackendTimeoutError,
)

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
