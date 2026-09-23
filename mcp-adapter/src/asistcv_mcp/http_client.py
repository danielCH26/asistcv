"""Cliente HTTP para comunicarse con el backend AsistCV."""

from typing import NoReturn

import httpx
import structlog

from .config import get_settings

logger = structlog.get_logger(__name__)

_SENSITIVE_HEADERS = frozenset({"authorization"})


def _sanitize_headers(headers: httpx.Headers | dict[str, str] | None) -> dict[str, str]:
    """Devuelve una copia de los headers sin valores sensibles (Authorization, etc.).

    Usar antes de loggear headers para evitar filtrar la API key.
    """
    if headers is None:
        return {}
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in _SENSITIVE_HEADERS:
            sanitized[key] = "***REDACTED***"
        else:
            sanitized[key] = value
    return sanitized


class BackendError(Exception):
    """Error recibido del backend."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class BackendAuthError(BackendError):
    """Error de autenticación con el backend (401).

    Se levanta cuando el backend rechaza la petición por credenciales
    ausentes o inválidas. El mensaje es seguro de exponer al usuario
    porque NO incluye la API key enviada.
    """

    def __init__(
        self,
        message: str = "API key inválida o ausente",
        status_code: int = 401,
    ) -> None:
        super().__init__(message, status_code=status_code)


class BackendTimeoutError(BackendError):
    """Timeout al comunicarse con el backend."""

    def __init__(self) -> None:
        super().__init__("Timeout al comunicarse con el backend")


class BackendConnectionError(BackendError):
    """Error de conexión con el backend."""

    def __init__(self, message: str = "No se pudo conectar con el backend") -> None:
        super().__init__(message)


class BackendClient:
    """Cliente HTTP async para el backend AsistCV."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.backend_url
        self._api_key = settings.backend_api_key
        self._timeout = settings.timeout_seconds
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Obtiene o crea el cliente HTTP.

        El header ``Authorization`` se aplica a nivel de cliente, de modo que
        TODOS los métodos (``get_health``, ``evaluate_match`` y cualquier
        método futuro) lo envían automáticamente sin tener que repetir la
        lógica.
        """
        if self._client is None:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=self._timeout,
            )
        return self._client

    @staticmethod
    def _raise_for_status_error(
        exc: httpx.HTTPStatusError,
        endpoint: str,
    ) -> NoReturn:
        """Traduce ``HTTPStatusError`` a la excepción de dominio apropiada.

        - 401 → ``BackendAuthError`` con mensaje claro y seguro.
        - Otros → ``BackendError`` con el detalle del backend.
        """
        status_code = exc.response.status_code
        if status_code == 401:
            logger.error(
                "Backend auth error",
                endpoint=endpoint,
                status=status_code,
            )
            raise BackendAuthError()
        logger.error(
            "Backend error",
            endpoint=endpoint,
            status=status_code,
            detail=exc.response.text,
        )
        raise BackendError(
            f"Error del backend: {exc.response.text}",
            status_code=status_code,
        )

    async def get_health(self) -> dict[str, object]:
        """Llama al endpoint /health del backend."""
        client = await self._get_client()
        try:
            logger.debug("Calling backend health endpoint")
            response = await client.get("/health")
            response.raise_for_status()
            logger.debug("Health check successful", status=response.status_code)
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e, endpoint="get_health")
        except httpx.TimeoutException:
            logger.error("Health check timeout")
            raise BackendTimeoutError() from None
        except httpx.ConnectError as e:
            logger.error("Health check connection error", error=str(e))
            raise BackendConnectionError() from None

    async def evaluate_match(self, jd_text: str, profile_id: int = 1) -> dict[str, object]:
        """Evalúa el match entre un JD y el perfil del usuario."""
        client = await self._get_client()
        try:
            logger.debug("Calling evaluate_match", profile_id=profile_id, jd_length=len(jd_text))
            response = await client.post(
                "/v1/match",
                json={"jd_text": jd_text, "profile_id": profile_id},
            )
            response.raise_for_status()
            logger.debug("Match evaluation successful", status=response.status_code)
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            self._raise_for_status_error(e, endpoint="evaluate_match")
        except httpx.TimeoutException:
            logger.error("Match evaluation timeout")
            raise BackendTimeoutError() from None
        except httpx.ConnectError as e:
            logger.error("Match evaluation connection error", error=str(e))
            raise BackendConnectionError() from None

    async def close(self) -> None:
        """Cierra el cliente HTTP."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.debug("HTTP client closed")

    def _debug_safe_headers(self) -> dict[str, str]:
        """Devuelve los headers del cliente con valores sensibles redactados.

        Útil para diagnóstico (debug); nunca se debe loggear
        ``self._client.headers`` directamente porque contiene la API key.
        """
        if self._client is None:
            return {}
        return _sanitize_headers(self._client.headers)
