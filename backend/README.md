# Backend

FastAPI application serving the AsistCV REST API.

## Stack

- Python 3.12+
- FastAPI
- UV (package manager)

## Commands

```bash
# Install dependencies
uv sync

# Run development server
uv run uvicorn app.main:app --reload

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

## Structure

```
backend/
├── app/           # Application code
├── tests/         # Test suite
├── alembic/       # Database migrations
└── pyproject.toml # Project configuration
```
