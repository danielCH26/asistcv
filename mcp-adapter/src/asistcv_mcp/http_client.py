"""Cliente HTTP para comunicarse con el backend AsistCV."""

import httpx
import structlog

from .config import get_settings

logger = structlog.get_logger(__name__)


class BackendError(Exception):
    """Error recibido del backend."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


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
        """Obtiene o crea el cliente HTTP."""
        if self._client is None:
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=self._timeout,
            )
        return self._client

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
            logger.error("Health check failed", status=e.response.status_code, detail=e.response.text)
            raise BackendError(
                f"Error del backend: {e.response.text}",
                status_code=e.response.status_code,
            )
        except httpx.TimeoutException:
            logger.error("Health check timeout")
            raise BackendTimeoutError()
        except httpx.ConnectError as e:
            logger.error("Health check connection error", error=str(e))
            raise BackendConnectionError()

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
            logger.error("Match evaluation failed", status=e.response.status_code, detail=e.response.text)
            raise BackendError(
                f"Error del backend: {e.response.text}",
                status_code=e.response.status_code,
            )
        except httpx.TimeoutException:
            logger.error("Match evaluation timeout")
            raise BackendTimeoutError()
        except httpx.ConnectError as e:
            logger.error("Match evaluation connection error", error=str(e))
            raise BackendConnectionError()

    async def close(self) -> None:
        """Cierra el cliente HTTP."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.debug("HTTP client closed")
