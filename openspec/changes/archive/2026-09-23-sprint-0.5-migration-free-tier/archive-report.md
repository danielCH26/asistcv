# Archive Report: Sprint 0.5 — Migración a Free Tier

## Resumen del Change

Sprint 0.5 migró toda la infraestructura de GCP (Cloud SQL, Cloud Build, Cloud Run) a servicios free tier: Neon (Postgres + pgvector), Render (backend), HuggingFace Inference (embeddings), y Groq (LLM). Este sprint no utilizó el workflow OpenSpec formal — fue una migración directa de infraestructura.

## Estado Final

| Métrica | Valor |
|---------|-------|
| Issues cerradas | #38, #39, #40, #41, #43 (5 de 6) |
| Issues obsoletas cerradas | #8 (Cloud SQL), #10 (Cloud Build), #11 (Cloud Run), #35 (licencia) |
| Pendiente | #42 (para Sprint 4) |

## Servicios Migrados

| Servicio | Antes | Después |
|----------|-------|---------|
| Database | Cloud SQL (GCP) | Neon (Postgres 18 + pgvector) |
| Backend | Cloud Run (GCP) | Render (free tier) |
| Embeddings | Vertex AI (GCP) | HuggingFace Inference (BAAI/bge-m3) |
| LLM | Vertex AI (GCP) | Groq (qwen/qwen3.8-27b) |
| Frontend | — | Cloudflare Pages |

## Bugs Críticos Descubiertos y Arreglados

1. **match.py no cargaba perfil de la DB** — El endpoint intentaba usar datos hardcodeados en lugar de consultar Neon
2. **Puerto 5432 ocupado** — Otro proyecto usaba el puerto; migrado a 5433
3. **Async/sync mismatch en SQLAlchemy** — Driver asíncrono con código síncrono causaba bloqueos
4. **Endpoint HF deprecado** — `api-inference.huggingface.co` cambió a `inference.huggingface.co`
5. **numpy.ndarray vs list** — SDK de HF retornaba array, código esperaba list
6. **sslmode/channel_binding rechazado** — asyncpg rechazaba opciones de conexión legacy
7. **CORS_ORIGINS parsing** — pydantic-settings parseaba JSON antes del field validator
8. **CI lockfile path resolution** — Rutas relativas fallaban en GitHub Actions

## Métricas de Producción

- **Backend**: https://asistcv-backend.onrender.com
- **Frontend**: https://asistcv-frontend.pages.dev
- **DB**: Neon con pgvector, migraciones 001 y 002 aplicadas
- **LLM**: Groq qwen3.8-27b, score 95 en match real
- **Embeddings**: BGE-M3 (1024 dim), cross-lingual ES↔EN 0.9876
- **Auth**: API key activada (modo protegido en Render)

## Notas de Archive

Este cambio NO tiene artefactos OpenSpec formales (proposal, tasks, specs). El trabajo fue realizado directamente como migración de infraestructura. El usuario solicitó documentar este archive para mantener trazabilidad histórica.

## Próximos Pasos

- Sprint 1: Match JD ↔ Perfil (vector persistence + auth + retrieval + frontend)
- Sprint 2: CV adaptation + outreach (pendiente)
- Sprint 3: Pipeline tracking (pendiente)
- Sprint 4: Cierre de #42 y optimizaciones

## Fecha de Archive

2026-09-23
