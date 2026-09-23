# syntax=docker/dockerfile:1

############################
# Stage 1: builder
############################
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias primero para aprovechar la caché de capas de Docker
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copiar el resto del proyecto e instalarlo en el venv
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

############################
# Stage 2: runtime
############################
FROM python:3.12-slim AS runtime

# uv para lanzar la app con `uv run` (sin re-sincronizar el venv)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# HuggingFace Spaces corre el contenedor como UID 1000
RUN useradd -m -u 1000 user

ENV PYTHONUNBUFFERED=1 \
    UV_NO_SYNC=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=builder --chown=user:user /app/.venv ./.venv
COPY --chown=user:user pyproject.toml uv.lock alembic.ini ./
COPY --chown=user:user app ./app
COPY --chown=user:user alembic ./alembic

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 7860

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
