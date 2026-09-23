# Archive Report: Sprint 0 — Fundación técnica de AsistCV

## Resumen del Change

Sprint 0 estableció la base ejecutable del proyecto: monorepo con estructura `backend/`, `frontend/`, `mcp-adapter/`, `infra/`, `docs/`, esqueleto FastAPI con settings, logging y endpoints básicos, mock LLM determinista, y adapter MCP con tools `ping` y `evaluate_match`.

## Estado Final

| Métrica | Valor |
|---------|-------|
| PRs mergeados | 5 |
| Tests pasando al cierre | 44 |
| Issues cerradas | #6, #7, #9, #12, #13 |

## Artefactos

- ✅ proposal.md — creado
- ✅ tasks.md — creado (21 tareas implementadas, 12 completadas, 9 deferidas/verificación)

## Stack Técnica Establecido

- **Backend**: FastAPI + Python 3.12 + UV
- **Mock LLM**: Proveedor determinista con fixtures
- **Database**: Alembic + SQLModel + Postgres local (docker-compose)
- **MCP Adapter**: Servidor stdio con SDK `mcp`
- **Monorepo**: Estructura con Makefile y .gitignore

## Notas de Archive

Este change fue el foundation del proyecto. Las tareas deferidas (4.x, 5.x, 6.x) correspondían a:
- Alembic + Postgres local completo (posteriormente implementado en Sprint 0.5 con Neon)
- MCP adapter completo (implementado y funcional en producción)
- Verificación end-to-end del sprint

El cambio fue archivado con conocimiento de que las tareas deferidas fueron cerradas en sprints posteriores.

## Próximos Pasos

- Sprint 0.5: Migración a free tier (GCP → Neon + Render)
- Sprint 1: Match JD ↔ Perfil con persistencia y frontend

## Fecha de Archive

2026-09-23
