"""Tests para el HTTP client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from asistcv_mcp.http_client import (
    BackendAuthError,
    BackendClient,
    BackendConnectionError,
    BackendError,
    BackendTimeoutError,
    _sanitize_headers,
)


class TestBackendClient:
    """Tests para BackendClient."""

    @pytest.mark.asyncio
    async def test_adds_bearer_token_when_configured(self, settings_with_api_key):
        """Test que el cliente agrega Bearer token si está configurado."""
        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings_with_api_key

            client = BackendClient()
            http_client = await client._get_client()

            # Verificar que se agregó el header de Authorization
            assert http_client.headers.get("Authorization") == "Bearer test-api-key"

    @pytest.mark.asyncio
    async def test_no_bearer_token_when_not_configured(self, settings):
        """Test que NO agrega Bearer si no está configurado."""
        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings

            client = BackendClient()
            http_client = await client._get_client()

            # Verificar que NO hay header de Authorization
            assert "Authorization" not in http_client.headers

    @pytest.mark.asyncio
    async def test_timeout_is_configured(self, settings):
        """Test que el timeout se configura correctamente desde settings."""
        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings

            client = BackendClient()
            http_client = await client._get_client()

            # El timeout del cliente debe coincidir con el setting
            # (no hardcodeado en el cliente).
            assert http_client.timeout == httpx.Timeout(settings.timeout_seconds)

    @pytest.mark.asyncio
    async def test_http_error_raises_backend_error(self, settings):
        """Test que errores HTTP se traducen a BackendError."""
        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings

            client = BackendClient()

            # Mock del cliente HTTP interno
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal server error"

            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
                "Server error",
                request=MagicMock(),
                response=mock_response,
            ))
            client._client = mock_http_client

            with pytest.raises(BackendError) as exc_info:
                await client.get_health()

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_timeout_raises_backend_timeout_error(self, settings):
        """Test que timeout se traduce a BackendTimeoutError."""
        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings

            client = BackendClient()

            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            client._client = mock_http_client

            with pytest.raises(BackendTimeoutError):
                await client.get_health()

    @pytest.mark.asyncio
    async def test_connection_error_raises_backend_connection_error(self, settings):
        """Test que errores de conexión se traducen a BackendConnectionError."""
        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings

            client = BackendClient()

            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
            client._client = mock_http_client

            with pytest.raises(BackendConnectionError):
                await client.get_health()

    @pytest.mark.asyncio
    async def test_close_cleans_up_client(self, settings):
        """Test que close() cierra el cliente correctamente."""
        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings

            client = BackendClient()
            await client._get_client()  # Crear el cliente

            await client.close()

            # Verificar que se cerró el cliente
            assert client._client is None


class TestBackendClientAuth:
    """Tests específicos del header Authorization en TODOS los métodos."""

    @pytest.mark.asyncio
    async def test_no_auth_header_in_get_health_request(self, settings):
        """Sin api_key, el request de get_health NO debe llevar Authorization.
        """
        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings

            client = BackendClient()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value={"status": "ok"})

            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            client._client = mock_http_client

            await client.get_health()

            # Verificar el request enviado por el cliente
            call_kwargs = mock_http_client.get.call_args.kwargs
            assert "headers" not in call_kwargs or (
                "Authorization" not in call_kwargs.get("headers", {})
            )

            # Y verificar que en el cliente subyacente tampoco está
            assert "Authorization" not in mock_http_client.headers

    @pytest.mark.asyncio
    async def test_no_auth_header_in_evaluate_match_request(self, settings):
        """Sin api_key, el request de evaluate_match NO debe llevar Authorization.
        """
        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings

            client = BackendClient()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value={"score": 0.5})

            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            client._client = mock_http_client

            await client.evaluate_match(jd_text="x" * 60, profile_id=1)

            call_kwargs = mock_http_client.post.call_args.kwargs
            assert "headers" not in call_kwargs or (
                "Authorization" not in call_kwargs.get("headers", {})
            )

    @pytest.mark.asyncio
    async def test_auth_header_in_get_health_request(self, settings_with_api_key):
        """Con api_key, el request real de get_health lleva Authorization."""
        captured: dict[str, dict[str, str]] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = dict(request.headers)
            return httpx.Response(200, json={"status": "ok"})

        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings_with_api_key

            client = BackendClient()
            await client._get_client()  # Construye el AsyncClient con headers
            # Reemplazar el transport por MockTransport para capturar el request
            client._client._transport = httpx.MockTransport(handler)  # type: ignore[attr-defined]

            await client.get_health()

            assert captured["headers"]["authorization"] == "Bearer test-api-key"

    @pytest.mark.asyncio
    async def test_auth_header_in_evaluate_match_request(self, settings_with_api_key):
        """Con api_key, el request real de evaluate_match lleva Authorization."""
        captured: dict[str, dict[str, str]] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = dict(request.headers)
            return httpx.Response(200, json={"score": 0.5})

        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings_with_api_key

            client = BackendClient()
            await client._get_client()  # Construye el AsyncClient con headers
            client._client._transport = httpx.MockTransport(handler)  # type: ignore[attr-defined]

            await client.evaluate_match(jd_text="x" * 60, profile_id=1)

            assert captured["headers"]["authorization"] == "Bearer test-api-key"


class TestBackendAuthError:
    """Tests para la excepción BackendAuthError (401)."""

    @pytest.mark.asyncio
    async def test_401_on_get_health_raises_backend_auth_error(self, settings):
        """Un 401 en /health debe levantar BackendAuthError con mensaje útil."""
        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Invalid API key"

            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
                "Unauthorized",
                request=MagicMock(),
                response=mock_response,
            ))
            client._client = mock_http_client

            with pytest.raises(BackendAuthError) as exc_info:
                await client.get_health()

            assert exc_info.value.status_code == 401
            assert "API key" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_401_on_evaluate_match_raises_backend_auth_error(self, settings):
        """Un 401 en /v1/match debe levantar BackendAuthError con mensaje útil."""
        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings

            client = BackendClient()

            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Missing Authorization header"

            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(side_effect=httpx.HTTPStatusError(
                "Unauthorized",
                request=MagicMock(),
                response=mock_response,
            ))
            client._client = mock_http_client

            with pytest.raises(BackendAuthError) as exc_info:
                await client.evaluate_match(jd_text="x" * 60, profile_id=1)

            assert exc_info.value.status_code == 401
            assert "API key" in exc_info.value.message

    def test_backend_auth_error_is_a_backend_error(self):
        """BackendAuthError debe ser subclase de BackendError."""
        assert issubclass(BackendAuthError, BackendError)


class TestBackendClientTimeoutFromSettings:
    """Tests que el timeout viene de settings, no está hardcodeado."""

    @pytest.mark.asyncio
    async def test_timeout_uses_configured_setting_value(self):
        """Un timeout no-default en settings debe propagarse al cliente."""
        custom_settings = MagicMock()
        custom_settings.backend_url = "http://localhost:8000"
        custom_settings.backend_api_key = None
        custom_settings.timeout_seconds = 12.5

        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = custom_settings

            client = BackendClient()
            http_client = await client._get_client()

            assert http_client.timeout == httpx.Timeout(12.5)

    @pytest.mark.asyncio
    async def test_timeout_uses_default_when_settings_default(self):
        """El default de settings.timeout_seconds debe propagarse al cliente."""
        default_settings = MagicMock()
        default_settings.backend_url = "https://asistcv-backend.onrender.com"
        default_settings.backend_api_key = None
        default_settings.timeout_seconds = 60.0

        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = default_settings

            client = BackendClient()
            http_client = await client._get_client()

            assert http_client.timeout == httpx.Timeout(60.0)


class TestSanitizeHeaders:
    """Tests del helper _sanitize_headers."""

    def test_redacts_authorization_header(self):
        """Authorization debe aparecer redactada en la salida."""
        sanitized = _sanitize_headers({"Authorization": "Bearer secret-key"})
        assert sanitized["Authorization"] == "***REDACTED***"

    def test_redacts_authorization_case_insensitive(self):
        """La sanitización ignora mayúsculas/minúsculas del nombre."""
        sanitized = _sanitize_headers({"authorization": "Bearer secret-key"})
        assert sanitized["authorization"] == "***REDACTED***"

    def test_keeps_other_headers_intact(self):
        """Headers no sensibles deben pasar tal cual."""
        sanitized = _sanitize_headers(
            {"Authorization": "Bearer secret", "Content-Type": "application/json"}
        )
        assert sanitized["Content-Type"] == "application/json"
        assert sanitized["Authorization"] == "***REDACTED***"

    def test_none_returns_empty_dict(self):
        """None debe devolver un dict vacío."""
        assert _sanitize_headers(None) == {}
