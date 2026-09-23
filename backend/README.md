# Backend

FastAPI application serving the AsistCV REST API.

## Stack

- Python 3.12+
- FastAPI
- SQLModel + SQLAlchemy (async)
- Alembic (migrations)
- PostgreSQL + pgvector
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
# Start local PostgreSQL database
make db-up

# Stop database
make db-down

# Run migrations
make migrate

# Rollback last migration
make migrate-down

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
| `DATABASE_URL` | `postgresql://asistcv:asistcv@localhost:5433/asistcv` | PostgreSQL connection string |
| `LLM_PROVIDER` | `mock` | LLM provider (`mock` or `groq`) |
| `BACKEND_API_KEY` | `None` | API key for MCP adapter |

## Switching between local and production DB

The backend reads the connection string from the `DATABASE_URL` environment variable.

### Local development (default)

Uses the PostgreSQL from `infra/docker-compose.yml`, exposed on host port **5433**:

```bash
make db-up                     # start local Postgres on port 5433
uv run alembic upgrade head
```

No extra configuration needed: when `DATABASE_URL` is unset, the app falls back to
`postgresql://asistcv:asistcv@localhost:5433/asistcv`.

### Production (Neon Postgres)

```bash
export DATABASE_URL="postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require"
```

- `sslmode=require` is mandatory: Neon only accepts TLS connections.
- Both `postgresql://...` and `postgresql+asyncpg://...` URLs work; the app
  (`app/db/session.py`) and Alembic (`alembic/env.py`) normalize the URL to the
  async driver automatically.
- Verify the connection and the pgvector extension before running migrations:

```bash
uv run python scripts/test_neon_connection.py
```

### Running migrations against Neon

```bash
export DATABASE_URL="postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require"
uv run alembic upgrade head
```

`alembic/env.py` reads the same `DATABASE_URL` and rewrites it to
`postgresql+asyncpg://` under the hood.

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
│   ├── db/                  # Database layer (SQLModel)
│   │   ├── models.py        # SQLModel definitions
│   │   ├── session.py       # Session management
│   │   └── seed.py          # Seed data
│   └── llm/                 # LLM integration
├── alembic/                 # Database migrations
│   ├── versions/            # Migration files
│   └── env.py               # Alembic configuration
├── tests/
│   ├── conftest.py          # Pytest fixtures
│   ├── test_health.py       # Smoke tests
│   ├── test_models.py       # Model tests
│   └── test_migrations.py   # Migration tests
├── alembic.ini              # Alembic configuration
├── pyproject.toml           # Project configuration
└── .env.example             # Environment variables template
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
uv run pytest tests/test_models.py -v
uv run pytest tests/test_migrations.py -v
```
