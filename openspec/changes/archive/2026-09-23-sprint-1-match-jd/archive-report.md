# Archive Report: Sprint 1 — Match JD ↔ Perfil (Slice 1)

## Resumen del Change

Sprint 1 cerró el flujo end-to-end de match entre Job Description y Perfil: persistencia vectorial con pgvector, autenticación por API key, retrieval semántico con umbral, MCP en producción, y frontend SvelteKit estático con i18n ES/EN.

## Estado Final

| Métrica | Valor |
|---------|-------|
| PRs mergeados | 6 (A, B, C, D1, E, D2) |
| Tests backend | 117 |
| Tests MCP | 30 |
| Issues cerradas | #14, #15, #16, #17, #18, #19, #20 |

## Artefactos

- ✅ proposal.md — creado
- ✅ design.md — creado
- ✅ specs/match-analysis/spec.md — creado (delta sync a main)
- ✅ specs/semantic-retrieval/spec.md — creado (delta sync a main)
- ✅ specs/match-ui/spec.md — creado (delta sync a main)
- ✅ tasks.md — creado (26 tareas)

## Capabilities Implementadas

### match-analysis
- `POST /v1/match` con persistencia transaccional
- `GET /v1/analyses` historial paginado
- `GET /v1/analyses/{id}` detalle
- Autenticación por API key (modo protegido / abierto)
- Embeddings persistidos con BGE-M3

### semantic-retrieval
- Columnas vector(1024) en profiles, job_descriptions, analyses
- Índices HNSW con vector_cosine_ops
- Umbral de retrieval (3000 chars)
- Fallback a perfil completo

### match-ui
- Frontend SvelteKit + adapter-static
- Formulario de JD + vista de resultado
- Historial de análisis
- i18n ES/EN con svelte-i18n
- API key vía build-time env

## Métricas de Producción

- **Backend**: https://asistcv-backend.onrender.com
- **Frontend**: https://asistcv-frontend.pages.dev
- **Auth**: API key activada
- **MCP**: Apunta a producción, timeout 60s
- **CI**: 6 jobs verdes (lint, typecheck, test-backend, test-mcp, i18n-parity, docker-build)
- **Licencia**: Apache 2.0 con patent grant

## Lecciones Aprendidas (Bugs durante validación)

1. **Match no cargaba perfil** — El endpoint usaba datos hardcodeados en lugar de consultar la DB
2. **Puerto 5432 ocupado** — Conflicto con otro proyecto; moverse a 5433
3. **Async/sync mismatch** — SQLAlchemy async con código sync
4. **Endpoint HuggingFace deprecado** — Cambio de API
5. **numpy.ndarray vs list** — Tipo incompatible en respuesta del SDK
6. **sslmode/channel_binding** — Opciones legacy rechazadas por asyncpg
7. **CORS_ORIGINS** — Pydantic-settings parseaba antes del validator

## Specs Sincronizadas a Main

Las siguientes specs fueron movidas de delta a specs principales:
- `openspec/specs/match-analysis/spec.md`
- `openspec/specs/semantic-retrieval/spec.md`
- `openspec/specs/match-ui/spec.md`

## Próximos Pasos

- Sprint 2: CV adaptation + outreach
- Sprint 3: Pipeline tracking
- Sprint 4: Cierre de #42 y optimizaciones

## Fecha de Archive

2026-09-23
