# AsistCV

[![CI](https://github.com/danielCH26/asistcv/actions/workflows/ci.yml/badge.svg)](https://github.com/danielCH26/asistcv/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Asistente agéntico de búsqueda de empleo. Hoy entrega **Match JD ↔ perfil** y **Adaptación de CV** (reorganiza bullets del CV del usuario contra una JD, sin inventar experiencia). Outreach y Tracking Pipeline están diferidos a v2.0. Diseñado para ayudar a aplicar mejor a los 5–10 puestos que valen la pena, no a auto-aplicar a 100.

## Capacidades actuales

- **Match JD ↔ perfil** — análisis semántico del puesto contra el perfil del usuario. Devuelve score honesto, razones, skills faltantes y energía recomendada para invertir.
- **Adaptación de CV** — reescribe los bullets del CV para los puestos que pasaron el filtro anterior. El usuario revisa y aprueba antes de cualquier envío; el LLM no inventa experiencia.
- **Adapter MCP** — Claude Desktop o Cursor pueden llamar `evaluate_match` contra el backend.

Fuera de alcance por ahora: outreach (mensaje de primer contacto), tracking pipeline (kanban de aplicaciones), landing pública. Ver [ROADMAP.md](ROADMAP.md) para el plan v2.0.

## Stack

- **Backend**: FastAPI (Python 3.12, uv)
- **Frontend**: SvelteKit (TypeScript, npm)
- **MCP Adapter**: Python con SDK `mcp` oficial
- **Base de datos**: PostgreSQL con pgvector (Neon en prod, docker-compose en local)
- **Cloud**: backend auto-deployado en **Render**, frontend auto-deployado en **Cloudflare Pages**
- **LLM**: Groq (Llama 3.x) en prod, mock determinista en dev
- **Embeddings**: HuggingFace Inference API (BGE-M3) en prod, mock en dev

## Prerequisitos

- Python 3.12+ con [uv](https://docs.astral.sh/uv/)
- Node.js 20+ con npm
- Docker y Docker Compose (para la DB local con pgvector)

## Quick start

```bash
# Instalar todas las dependencias (backend + frontend + MCP + DB local)
make setup

# Copiá los archivos de env de ejemplo y completá los valores
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
cp infra/.env.example infra/.env

# Aplicar migraciones
make migrate

# Correr servidores de desarrollo
make backend-run   # API en http://localhost:8000
make frontend-run  # UI en http://localhost:5173

# Correr los tests (backend + frontend + MCP)
make test
```

`make help` lista todos los comandos. Para deploy a staging o producción, ver [docs/DEPLOY.md](docs/DEPLOY.md) — el deploy es automático desde `main` (Render + Cloudflare Pages lo gestionan).

## Estructura del proyecto

```
asistcv/
├── backend/      # API REST con FastAPI
├── frontend/     # Web app con SvelteKit
├── mcp-adapter/  # Integración con Claude Desktop / Cursor vía MCP
├── infra/        # docker-compose.yml + .env.example para DB local
└── docs/         # Documentación técnica (DEPLOY, CI_SETUP, audit)
```

## Documentación

Para documentación detallada del proyecto:

- [PROJECT.md](PROJECT.md) — documento integrador (qué es, estado actual, links)
- [STACK.md](STACK.md) — decisiones arquitectónicas y tradeoffs del stack
- [ROADMAP.md](ROADMAP.md) — plan de implementación por milestones (v1.0, v2.0)
- [job-search-assistant.md](job-search-assistant.md) — PRD fundacional
- [docs/DEPLOY.md](docs/DEPLOY.md) — cómo desplegar a staging/producción
- [docs/CI_SETUP.md](docs/CI_SETUP.md) — pipeline de CI y secretos
- [docs/audit/](docs/audit/) — auditoría de seguridad y remediación

Para detalle de cada componente:

- [backend/README.md](backend/README.md) — Backend FastAPI
- [frontend/README.md](frontend/README.md) — Frontend SvelteKit
- [mcp-adapter/README.md](mcp-adapter/README.md) — Adapter MCP
- [infra/README.md](infra/README.md) — docker-compose y env de la DB local

## Estado

v1.0 — MVP Early Adopters (release target: 14 oct 2026). Cubre las fases 0/1/2/3 del audit de remediación y las features críticas de match + adaptación + billing Stripe para early adopters manuales invitados uno-a-uno. Sin landing pública, sin pasarela Colombia, sin Claymorphism full. Ver el [milestone v1.0 en GitHub](https://github.com/danielCH26/asistcv/milestone/7) y [ROADMAP.md](ROADMAP.md).

## Licencia

Apache 2.0. Ver [LICENSE](LICENSE).