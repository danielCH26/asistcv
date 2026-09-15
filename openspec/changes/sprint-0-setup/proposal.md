# Proposal: Sprint 0 — Fundación técnica de AsistCV

## Intent

Greenfield: PRD, stack y roadmap cerrados. Sprint 0 crea la base ejecutable — monorepo, FastAPI, migraciones, mock LLM, adapter MCP — para construir el Slice 1 sobre infra verificada. Desarrollo local sin credenciales GCP; presupuesto ($10-20/mes) intacto hasta tener GCP.

## Scope

### In Scope (5 issues locales)

| Issue | Entregable | Deps |
|---|---|---|
| #6 | Monorepo (`backend/ frontend/ mcp-adapter/ infra/ docs/`), READMEs, Makefile, `.gitignore` | — |
| #7 | FastAPI: `/health`, `/v1/ping`, `/docs`, placeholder `POST /v1/match`, pydantic-settings, structlog JSON | #6 |
| #12 | `LLMProvider` + `MockProvider` determinista (fixtures) + `VertexAIProvider` + factory por `LLM_PROVIDER` | #7 |
| #9 | Alembic + SQLModel, migración inicial (tablas placeholder), `make migrate`; Postgres local vía docker-compose `pgvector` | #7 |
| #13 | MCP adapter stdio (SDK `mcp`): tools `ping` y `evaluate_match` → `/v1/match`; docs Claude Desktop | #7, #12 |

### Deferred (GCP con billing; scope congelado)

- #8 Cloud SQL + pgvector (DB).
- #10 CI/CD Cloud Build (Artifact Registry).
- #11 Deploy Cloud Run + secrets (#8, #10).

Implementación futura sin re-plan.

### Out of Scope

Features (Slices 1-3), schema de dominio real, auth completa, deploy frontend, Vertex AI en local, automatización de envío (anti-patrón PRD).

## Capabilities

**None.** Scaffolding sin cambios de requirements; stack ya cerrado (STACK.md) justifica el flujo **SDD liviano**: omitir `sdd-spec`/`sdd-design`; ir a `sdd-tasks`.

## Approach

Orden: #6 → #7 → (#12, #9 en paralelo) → #13. Backend y adapter: proyectos UV independientes; `LLM_PROVIDER=mock` en dev.

## Affected Areas

| Área | Impacto | Cambio |
|---|---|---|
| `backend/` | New | App FastAPI, settings, logging, `llm/`, `alembic/` |
| `frontend/` | New | Scaffold SvelteKit adapter-static |
| `mcp-adapter/` | New | Servidor stdio, 2 tools |
| `infra/` | New | docker-compose Postgres + pgvector |
| `docs/`, raíz | New/Mod | READMEs, Makefile, `.gitignore` |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| AC de #9 referencia Cloud SQL | Alta | Verificar en Postgres local; Cloud SQL difiere con #8 |
| Tablas placeholder ≠ schema Slice 1 (ROADMAP) | Alta | Slice 1 es dueño del schema; Alembic migra |
| Diff total >> 600 líneas | Alta | PR encadenado por issue; forecast en sdd-tasks |
| `/v1/match` sin auth efectiva | Media | Auth antes de #11; sin deploy público hasta entonces |
| Drift Mock vs Vertex real | Media | Contrato `LLMProvider` + fixtures reproducibles |

## Rollback Plan

Sprint aditivo sin datos ni infra: revert de PRs; `alembic downgrade` revierte schema local.

## Dependencies

Locales: Python 3.12 + UV, Node 20+, Docker. Diferidas: GCP con billing (#8, #10, #11).

## Success Criteria

- [ ] Backend levanta con `LLM_PROVIDER=mock` sin credenciales
- [ ] `/health`, `/v1/ping`, `/docs` OK; logs JSON
- [ ] `alembic upgrade head` / `downgrade -1` OK en Postgres local
- [ ] `uv run asistcv-mcp`: `ping` → "pong"; `evaluate_match` → mock
- [ ] `make` lista tasks; `.gitignore`: Python + SvelteKit + secrets
- [ ] #8/#10/#11 con scope congelado

## Next Steps

`sdd-tasks`: breakdown por issue; forecast de PRs encadenados (budget 600).
