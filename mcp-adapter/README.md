# MCP Adapter

Model Context Protocol adapter for AsistCV (Claude Desktop integration).

## Description

Este adapter expone las tools del backend AsistCV a clientes MCP como Claude Desktop. Permite evaluar matches entre descripciones de puestos y perfiles de candidatos directamente desde Claude.

## Requirements

- Python 3.12+
- UV (package manager)
- Backend AsistCV corriendo en `http://localhost:8000`

## Installation

```bash
cd mcp-adapter
uv sync
```

## Configuration

El adapter se configura mediante variables de entorno. Copia `.env.example` a `.env` y ajusta los valores:

```bash
cp .env.example .env
```

Variables disponibles:
- `BACKEND_URL`: URL del backend FastAPI (default: `http://localhost:8000`)
- `BACKEND_API_KEY`: Clave API opcional para autenticación
- `LOG_LEVEL`: Nivel de logging (DEBUG, INFO, WARNING, ERROR)
- `TIMEOUT_SECONDS`: Timeout para llamadas HTTP (default: 30.0)

## Running

```bash
# Con la configuración por defecto (backend en localhost:8000)
uv run asistcv-mcp

# Con variables de entorno personalizadas
BACKEND_URL=http://localhost:8000 uv run asistcv-mcp
```

El servidor usa transporte stdio (entrada/salida estándar), que es el estándar para clientes MCP.

## Claude Desktop Configuration

Para usar este adapter en Claude Desktop, agrega esta configuración al archivo de configuración de Claude Desktop:

```json
{
  "mcpServers": {
    "asistcv": {
      "command": "uv",
      "args": ["--directory", "/path/to/asistcv/mcp-adapter", "run", "asistcv-mcp"],
      "env": {
        "BACKEND_URL": "http://localhost:8000",
        "BACKEND_API_KEY": "optional-key-here"
      }
    }
  }
}
```

Reemplaza `/path/to/asistcv` con la ruta absoluta al directorio del proyecto.

## Available Tools

### ping

Health check del adapter. Devuelve 'pong' si todo funciona.

**Args:** none

**Returns:** `"pong"`

### evaluate_match

Evalúa el match entre una descripción de puesto (JD) y el perfil del usuario.

**Args:**
- `jd_text` (string, required): Texto completo de la descripción del puesto (mínimo 50 caracteres)
- `profile_id` (integer, optional): ID del perfil a usar (default: 1)

**Returns:** JSON string con:
- `score`: Puntuación de match (0-1)
- `strengths`: Lista de fortalezas identificadas
- `gaps`: Lista de brechas identificadas
- `energy_level`: Nivel de energía (high, medium, low)
- `reasoning`: Explicación del análisis

### get_health

Llama al endpoint /health del backend y devuelve el status.

**Args:** none

**Returns:** JSON string con `{"status": "ok"}` si el backend está saludable

## Troubleshooting

Si las tools no aparecen en Claude Desktop:

1. Verifica que el backend esté corriendo: `curl http://localhost:8000/health`
2. Verifica que el adapter arranca sin errores: `uv run asistcv-mcp`
3. Revisa los logs en la terminal donde corre el adapter
4. Verifica que la configuración en Claude Desktop sea correcta (ruta absoluta)
5. Reinicia Claude Desktop después de cambiar la configuración

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Run type checker
uv run mypy src/
```
