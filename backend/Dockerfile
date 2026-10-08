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

# Bake the local embedding model into the image (issue #101):
# downloading at build time keeps cold starts off the HF Hub. The default
# model is paraphrase-multilingual-MiniLM-L12-v2 (384-dim, ~220MB ONNX).
# Override with --build-arg EMBEDDING_MODEL=<name> if EMBEDDING_MODEL changes;
# keep it in sync with the runtime EMBEDDING_MODEL env.
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    HF_HOME=/hf-cache
RUN uv run python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='${EMBEDDING_MODEL}')"

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
COPY --from=builder --chown=user:user /hf-cache /hf-cache
COPY --chown=user:user pyproject.toml uv.lock alembic.ini ./
COPY --chown=user:user app ./app
COPY --chown=user:user alembic ./alembic

# Model cache baked in the builder stage; the app user only needs read.
ENV HF_HOME=/hf-cache

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 7860

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
