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
RUN uv sync --frozen --no-dev \
 && find app -name '*.py' -type f -exec sha256sum {} + | sort | sha256sum | cut -d' ' -f1 > .venv/.source-hash

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

# OJO con la cache de capas: `COPY --from=builder /app/.venv` puede salir
# CACHED y traerse el PAQUETE INSTALADO de una build anterior. Ese paquete
# (site-packages/app) es el que importa `uvicorn` cuando se lanza como script
# de consola, asi que el contenedor servia codigo viejo aunque /app/app
# tuviera el codigo nuevo: desplegar un fix no cambiaba nada y el sintoma era
# un traceback con numeros de linea del archivo anterior.
#
# Dos barreras:
#   1. `.venv/.source-hash` (arriba) cambia cuando cambia el codigo, asi que
#      el contenido del venv cambia y la capa COPY deja de estar cacheada.
#   2. El CMD usa `python -m ...`: eso mete el directorio de trabajo (/app)
#      al principio de sys.path, de modo que `import app` resuelve a
#      /app/app (el codigo copiado en esta imagen) y no al paquete del venv.
COPY --from=builder --chown=user:user /app/.venv ./.venv
COPY --chown=user:user pyproject.toml uv.lock alembic.ini ./
COPY --chown=user:user app ./app
COPY --chown=user:user alembic ./alembic

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 7860

# Las migraciones se aplican al arrancar el contenedor, no como paso manual:
# el contenedor ya tiene `DATABASE_URL` (lo inyecta la plataforma), así que
# no hace falta guardar el secreto de la base en ningún otro lado —ni en
# GitHub Actions— ni acordarse de correrlo.
#
# `alembic upgrade head` es idempotente: si no hay migraciones nuevas, no
# hace nada. Si una migración falla, el contenedor NO levanta: es preferible
# que no arranque a que sirva código contra un esquema que no corresponde.
#
# OJO con el autoescalado: dos contenedores arrancando a la vez podrían
# correr la misma migración en paralelo. Con una instancia (el plan actual)
# no puede pasar; si algún día se escala, hay que mover esto a un paso
# único (un job de despliegue o un lock).
#
# `python -m` y no el script de consola: ver la nota de la cache de capas
# arriba.
CMD ["sh", "-c", "uv run python -m alembic upgrade head && exec uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 7860"]
