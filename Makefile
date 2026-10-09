# AsistCV - Makefile
# Quick reference: make <target>

.PHONY: help setup test lint \
	backend-install backend-run backend-test backend-lint \
	frontend-install frontend-run frontend-build frontend-test frontend-lint \
	mcp-install mcp-run mcp-test \
	db-up db-down migrate migrate-down

help:
	@echo "AsistCV - Available targets:"
	@echo ""
	@echo "=== Global ==="
	@echo "  setup          Install all dependencies and start the local DB"
	@echo "  test           Run all test suites (backend + frontend + MCP)"
	@echo "  lint           Run all linters (backend + frontend)"
	@echo ""
	@echo "=== Backend (FastAPI) ==="
	@echo "  backend-install    Install backend dependencies (uv sync)"
	@echo "  backend-run        Run backend dev server"
	@echo "  backend-test       Run backend tests (pytest)"
	@echo "  backend-lint       Lint backend code (ruff)"
	@echo ""
	@echo "=== Frontend (SvelteKit) ==="
	@echo "  frontend-install   Install frontend dependencies (npm install)"
	@echo "  frontend-run       Run frontend dev server"
	@echo "  frontend-build     Build frontend for production"
	@echo "  frontend-test      Run frontend tests (vitest)"
	@echo "  frontend-lint      Lint frontend code (svelte-check)"
	@echo ""
	@echo "=== MCP Adapter ==="
	@echo "  mcp-install        Install MCP adapter dependencies"
	@echo "  mcp-run            Run MCP adapter (stdio)"
	@echo "  mcp-test           Run MCP adapter tests"
	@echo ""
	@echo "=== Database ==="
	@echo "  db-up              Start local PostgreSQL (docker compose)"
	@echo "  db-down            Stop local PostgreSQL"
	@echo "  migrate            Run database migrations (upgrade + seed)"
	@echo "  migrate-down       Rollback last migration"
	@echo ""
	@echo "=== Deploy ==="
	@echo "  Deploy is platform-managed: backend -> Render (manual deploy of the latest commit),"
	@echo "  frontend -> Cloudflare Pages (build from GitHub). See docs/DEPLOY.md."

# Compose the high-level targets so a wrapper script sees a meaningful exit
# code instead of a TODO echo. Each line calls the working sub-target below.
setup:
	@echo "Installing backend dependencies..."
	cd backend && uv sync
	@echo "Installing frontend dependencies..."
	cd frontend && npm install
	@echo "Installing MCP adapter dependencies..."
	cd mcp-adapter && uv sync
	@echo "Starting local database..."
	docker compose -f infra/docker-compose.yml up -d db
	@echo ""
	@echo "AsistCV setup complete."
	@echo "Next: copy infra/.env.example -> infra/.env, backend/.env.example -> backend/.env,"
	@echo "      frontend/.env.example -> frontend/.env, then \`make migrate\`."

test:
	@echo "Running backend tests..."
	cd backend && uv run pytest
	@echo "Running frontend tests..."
	cd frontend && npm run test
	@echo "Running MCP adapter tests..."
	cd mcp-adapter && uv run pytest

lint:
	@echo "Linting backend (ruff)..."
	cd backend && uv run ruff check .
	@echo "Linting frontend (svelte-check)..."
	cd frontend && npm run check

# Backend targets
backend-install:
	@echo "Installing backend dependencies..."
	cd backend && uv sync

backend-run:
	@echo "Running backend..."
	cd backend && uv run uvicorn app.main:app --reload

backend-test:
	@echo "Running backend tests..."
	cd backend && uv run pytest

backend-lint:
	@echo "Linting backend code..."
	cd backend && uv run ruff check .

# Frontend targets
frontend-install:
	@echo "Installing frontend dependencies..."
	cd frontend && npm install

frontend-run:
	@echo "Running frontend..."
	cd frontend && npm run dev

frontend-build:
	@echo "Building frontend..."
	cd frontend && npm run build

frontend-test:
	@echo "Running frontend tests..."
	cd frontend && npm run test

frontend-lint:
	@echo "Linting frontend (svelte-check)..."
	cd frontend && npm run check

# MCP Adapter targets
mcp-install:
	@echo "Installing MCP adapter dependencies..."
	cd mcp-adapter && uv sync

mcp-run:
	@echo "Running MCP adapter (stdio)..."
	cd mcp-adapter && uv run asistcv-mcp

mcp-test:
	@echo "Running MCP adapter tests..."
	cd mcp-adapter && uv run pytest

# Database targets
db-up:
	@echo "Starting local database..."
	docker compose -f infra/docker-compose.yml up -d db

db-down:
	@echo "Stopping local database..."
	docker compose -f infra/docker-compose.yml down

migrate:
	@echo "Running migrations..."
	cd backend && uv run alembic upgrade head && uv run python -m app.db.seed

migrate-down:
	@echo "Rolling back migration..."
	cd backend && uv run alembic downgrade -1
