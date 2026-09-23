# AsistCV

[![CI](https://github.com/danielCH26/asistcv/actions/workflows/ci.yml/badge.svg)](https://github.com/danielCH26/asistcv/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Asistente agéntico de búsqueda de empleo. Match JD ↔ perfil, adaptar CV + outreach, tracking pipeline. Diseñado para ayudar a aplicar mejor a los 5–10 puestos que valen la pena, no a auto-aplicar a 100.

## Stack

- **Backend**: FastAPI (Python 3.12, UV)
- **Frontend**: SvelteKit (TypeScript, npm)
- **MCP Adapter**: Python con SDK `mcp` oficial
- **Base de datos**: PostgreSQL con pgvector
- **Cloud**: GCP (Cloud Run, Cloud SQL)

## Prerequisitos

- Python 3.12+ con UV
- Node.js 20+ con npm
- Docker y Docker Compose
- Google Cloud SDK (para deploy)

## Quick start

```bash
# Instalar todas las dependencias
make setup

# O instalar individualmente
make backend-install
make frontend-install

# Levantar base de datos local
make db-up

# Correr servidores de desarrollo
make backend-run   # API en http://localhost:8000
make frontend-run  # UI en http://localhost:5173

# Correr tests
make test
```

## Estructura del proyecto

```
asistcv/
├── backend/      # API REST con FastAPI
├── frontend/     # Web app con SvelteKit
├── mcp-adapter/  # Integración con Claude Desktop via MCP
├── infra/        # Configuración de GCP
└── docs/         # Documentación técnica
```

## Documentación

Para documentación detallada del proyecto:

- `PROJECT.md` — documento integrador (qué es, estado actual, links)
- `STACK.md` — decisiones arquitectónicas y tradeoffs
- `ROADMAP.md` — plan de implementación por slices
- `job-search-assistant.md` — PRD fundacional

Para detalle de cada componente:

- `backend/README.md` — Backend FastAPI
- `frontend/README.md` — Frontend SvelteKit
- `mcp-adapter/README.md` — Adapter MCP
- `infra/README.md` — Infraestructura GCP
- `docs/README.md` — Documentación técnica complementaria

## Comandos disponibles

Corré `make help` para ver todos los targets.

## Estado

Proyecto en desarrollo. Sprint 0 en curso. Ver [ROADMAP.md](ROADMAP.md) y las [issues del repo](https://github.com/danielCH26/asistcv/issues) para más detalle.

## Licencia

TBD (ver issue #35).
