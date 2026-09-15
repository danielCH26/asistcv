# AsistCV - Makefile
# Quick reference: make <target>

.PHONY: help setup test lint deploy \
	backend-install backend-run backend-test backend-lint \
	frontend-install frontend-run frontend-build frontend-test \
	mcp-install mcp-run mcp-test \
	db-up db-down migrate migrate-down

help:
	@echo "AsistCV - Available targets:"
	@echo ""
	@echo "=== Global ==="
	@echo "  setup          Run full project setup (placeholder)"
	@echo "  test           Run all tests (placeholder)"
	@echo "  lint           Run linters (placeholder)"
	@echo "  deploy         Deploy to GCP (placeholder)"
	@echo ""
	@echo "=== Backend (FastAPI) ==="
	@echo "  backend-install    Install backend dependencies"
	@echo "  backend-run       Run backend dev server"
	@echo "  backend-test      Run backend tests"
	@echo "  backend-lint      Lint backend code"
	@echo ""
	@echo "=== Frontend (SvelteKit) ==="
	@echo "  frontend-install  Install frontend dependencies"
	@echo "  frontend-run      Run frontend dev server"
	@echo "  frontend-build    Build frontend for production"
	@echo "  frontend-test     Run frontend tests"
	@echo ""
	@echo "=== MCP Adapter ==="
	@echo "  mcp-install       Install MCP adapter dependencies"
	@echo "  mcp-run           Run MCP adapter (stdio)"
	@echo "  mcp-test          Run MCP adapter tests"
	@echo ""
	@echo "=== Database ==="
	@echo "  db-up             Start local PostgreSQL (docker compose)"
	@echo "  db-down           Stop local PostgreSQL"
	@echo "  migrate           Run database migrations (upgrade)"
	@echo "  migrate-down      Rollback last migration"

setup:
	@echo "Setting up AsistCV..."
	@echo "TODO: Implement full project setup"

test:
	@echo "Running all tests..."
	@echo "TODO: Implement test runner"

lint:
	@echo "Running linters..."
	@echo "TODO: Implement lint runner"

deploy:
	@echo "Deploying to GCP..."
	@echo "TODO: Implement deployment"

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
