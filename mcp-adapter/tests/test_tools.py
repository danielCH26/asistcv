"""Tests para las tools MCP."""

import pytest

from asistcv_mcp import tools


class TestPing:
    """Tests para la tool ping."""

    async def test_ping_returns_pong(self):
        """Test que ping devuelve 'pong'."""
        result = await tools.ping()
        assert result == "pong"


class TestEvaluateMatch:
    """Tests para la tool evaluate_match."""

    async def test_evaluate_match_calls_backend(self, mock_backend_client):
        """Test que evaluate_match llama al backend con los argumentos correctos."""
        jd_text = "We are looking for a Python developer with FastAPI experience"
        profile_id = 2

        result = await tools.evaluate_match(
            mock_backend_client,
            jd_text=jd_text,
            profile_id=profile_id,
        )

        # Verificar que se llamó al backend con los argumentos correctos
        mock_backend_client.evaluate_match.assert_called_once_with(
            jd_text=jd_text,
            profile_id=profile_id,
        )
        # Verificar que el resultado es un JSON string
        assert '"score"' in result

    async def test_evaluate_match_validates_min_length(self, mock_backend_client):
        """Test que evaluate_match valida que jd_text tenga mínimo 50 caracteres."""
        jd_text = "Too short"  # Menos de 50 caracteres

        with pytest.raises(ValueError, match="jd_text debe tener al menos 50 caracteres"):
            await tools.evaluate_match(mock_backend_client, jd_text=jd_text)

    async def test_evaluate_match_handles_backend_error(self, mock_backend_client):
        """Test que evaluate_match maneja errores del backend."""
        from asistcv_mcp.http_client import BackendError

        mock_backend_client.evaluate_match.side_effect = BackendError(
            "Backend error",
            status_code=500,
        )

        jd_text = "We are looking for a Python developer with FastAPI experience"

        with pytest.raises(RuntimeError, match="Error del backend: Backend error"):
            await tools.evaluate_match(mock_backend_client, jd_text=jd_text)

    async def test_evaluate_match_handles_timeout(self, mock_backend_client):
        """Test que evaluate_match maneja timeout."""
        from asistcv_mcp.http_client import BackendTimeoutError

        mock_backend_client.evaluate_match.side_effect = BackendTimeoutError()

        jd_text = "We are looking for a Python developer with FastAPI experience"

        with pytest.raises(RuntimeError, match="Timeout al comunicarse con el backend"):
            await tools.evaluate_match(mock_backend_client, jd_text=jd_text)

    async def test_evaluate_match_handles_connection_error(self, mock_backend_client):
        """Test que evaluate_match maneja errores de conexión."""
        from asistcv_mcp.http_client import BackendConnectionError

        mock_backend_client.evaluate_match.side_effect = BackendConnectionError()

        jd_text = "We are looking for a Python developer with FastAPI experience"

        with pytest.raises(RuntimeError, match="Error de conexión"):
            await tools.evaluate_match(mock_backend_client, jd_text=jd_text)


class TestGetHealth:
    """Tests para la tool get_health."""

    async def test_get_health_calls_endpoint(self, mock_backend_client):
        """Test que get_health llama al endpoint correcto."""
        result = await tools.get_health(mock_backend_client)

        # Verificar que se llamó al backend
        mock_backend_client.get_health.assert_called_once()
        # Verificar que el resultado es un JSON string
        assert '"status"' in result

    async def test_get_health_handles_backend_error(self, mock_backend_client):
        """Test que get_health maneja errores del backend."""
        from asistcv_mcp.http_client import BackendError

        mock_backend_client.get_health.side_effect = BackendError(
            "Service unavailable",
            status_code=503,
        )

        with pytest.raises(RuntimeError, match="Error del backend: Service unavailable"):
            await tools.get_health(mock_backend_client)

    async def test_get_health_handles_timeout(self, mock_backend_client):
        """Test que get_health maneja timeout."""
        from asistcv_mcp.http_client import BackendTimeoutError

        mock_backend_client.get_health.side_effect = BackendTimeoutError()

        with pytest.raises(RuntimeError, match="Timeout al comunicarse con el backend"):
            await tools.get_health(mock_backend_client)

    async def test_get_health_handles_connection_error(self, mock_backend_client):
        """Test que get_health maneja errores de conexión."""
        from asistcv_mcp.http_client import BackendConnectionError

        mock_backend_client.get_health.side_effect = BackendConnectionError()

        with pytest.raises(RuntimeError, match="Error de conexión"):
            await tools.get_health(mock_backend_client)
