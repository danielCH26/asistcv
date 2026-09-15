"""Tests para el HTTP client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from asistcv_mcp.http_client import (
    BackendClient,
    BackendConnectionError,
    BackendError,
    BackendTimeoutError,
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
        """Test que el timeout se configura correctamente."""
        with patch("asistcv_mcp.http_client.get_settings") as mock_settings:
            mock_settings.return_value = settings

            client = BackendClient()
            http_client = await client._get_client()

            # Verificar que el timeout está configurado
            assert http_client.timeout == httpx.Timeout(30.0)

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
