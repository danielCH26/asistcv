# Backend

FastAPI application serving the AsistCV REST API.

## Stack

- Python 3.12+
- FastAPI
- UV (package manager)

## Prerequisites

- Python 3.12 or higher
- UV package manager: https://github.com/astral-sh/uv

## Quick Start

```bash
# Install dependencies
cd backend
uv sync

# Run development server
uv run uvicorn app.main:app --reload

# Run tests
uv run pytest

# Run lint
uv run ruff check .

# Run type check
uv run mypy app/
```

## Commands (via Makefile)

From the repository root:

```bash
# Run backend dev server
make backend-run

# Run tests
make backend-test

# Run lint
make backend-lint

# Run type check
make backend-typecheck
```

## Environment Variables

Copy `.env.example` to `.env` and configure as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | Application environment |
| `LOG_LEVEL` | `INFO` | Logging level |
| `API_PREFIX` | `/v1` | API URL prefix |
| `DATABASE_URL` | `None` | PostgreSQL connection string |
| `LLM_PROVIDER` | `mock` | LLM provider (`mock` or `vertex`) |
| `BACKEND_API_KEY` | `None` | API key for MCP adapter |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/v1/ping` | Ping with timestamp |
| POST | `/v1/match` | Match JD to CV (placeholder) |
| GET | `/docs` | OpenAPI documentation |
| GET | `/redoc` | ReDoc documentation |

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── core/
│   │   ├── config.py        # Settings management
│   │   └── logging.py       # Structured logging
│   ├── api/
│   │   └── v1/
│   │       ├── health.py    # /health endpoint
│   │       ├── ping.py      # /v1/ping endpoint
│   │       └── match.py     # /v1/match endpoint (placeholder)
│   ├── db/                  # Database layer (Sprint 4)
│   └── llm/                 # LLM integration (PR 3)
├── tests/
│   ├── conftest.py          # Pytest fixtures
│   └── test_health.py      # Smoke tests
├── pyproject.toml          # Project configuration
└── .env.example            # Environment variables template
```

## Development

The backend uses:
- **FastAPI** for the web framework
- **Pydantic** for data validation
- **Structlog** for structured JSON logging
- **Uvicorn** as the ASGI server

## Testing

```bash
# Run all tests with coverage
uv run pytest --cov=app --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_health.py -v
```
