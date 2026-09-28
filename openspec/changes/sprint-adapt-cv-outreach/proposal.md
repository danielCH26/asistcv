# Proposal: Sprint 3 — Adaptación de CV a JD (Slice A de adapt-cv-outreach)

## Intent

Entregar la capacidad core del producto: adaptar un CV existente a una JD específica sin inventar experiencia. Sprint 2 entregó cuentas, CVs y billing; este cambio activa el segundo pilar de valor. La honestidad es un invariante no negociable: la adaptación reordena y reformula, nunca fabrica.

## Scope

### Recomendación de slicing

Estimación calibrada por historia (Sprint 1+2 reales ≈ 3× lo estimado inicialmente): **~9 semanas para el feature completo**. **Recomendación: sliced-a-b-c** — el valor core (CV a medida) se envía primero y honesto; outreach y brief son extensiones naturales sobre la misma infraestructura async y el mismo helper `_complete_json` de `groq_provider.py`.

- **Slice A (ESTE cambio)**: motor de adaptación + CV adaptado + guardrails de honestidad + enforcement de tier + componente frontend mínimo.
- **Slice B (follow-up, `sprint-outreach-generation`)**: cover letter + mensaje corto reutilizando la infra async de Slice A.
- **Slice C (follow-up, `sprint-company-brief`)**: brief de empresa — mayor riesgo de alucinación (sin web live), menor prioridad; llevará disclaimer explícito y secciones estructuradas (sector/cultura).

### In Scope (Slice A)

- `max_tokens` por operación en `groq_provider.py` (hoy 800 hardcodeado; adaptación exige 2000-4000+) sin regresar match/audit; reuso de `_complete_json`
- **Decisión de arquitectura (exploración)**: patrón **async + polling** — `POST /v1/adaptations` → 202 + `adaptation_id`; `GET /v1/adaptations/{id}` → status `pending/completed/failed`. Render free (~10s de timeout) vs LLM 5-15s lo **fuerza**; la convención ya existe (`audit_token` del funnel de auditoría)
- Migración aditiva: tabla nueva `CVAdaptation` con `parent_cv_id` FK → `UserCV` (**no** versiona `UserCV`; separación limpia original/adaptado)
- Servicio de adaptación: guardrails de honestidad en prompt ("solo hechos presentes en el CV") + **validación post-diff determinista** (skills/empresas/fechas del output ⊆ fuente; rechaza si aparece una skill nueva); JD tratada como input no confiable
- Dedupe: `jd_text_hash = sha256(jd_text[:500])` con TTL 24h — misma JD no re-procesa
- Recurso `adaptations_per_month` en `PLAN_LIMITS`: job_seeker_paid 5/mo, recruiter_starter 10/mo, recruiter_business 20/mo, recruiter_agency ilimitado; exceso → `402 PLAN_LIMIT_REACHED` con prompt de upgrade (patrón `check_limit`/`increment_usage` existente)
- Frontend: componente compartido `AdaptationResult` (reusa sub-componentes de `MatchResult`: ScoreCard, ReasoningBox) + integración en `/profile`

### Out of Scope

- Outreach (Slice B); company brief (Slice C); adaptación para roster reclutador (API + UI — cabalga sobre la misma infra, follow-up); export PDF del CV adaptado; streaming de tokens; tracking de pipeline (sprint futuro)

## Capabilities

> Contrato proposal → specs. Slices B/C quedan como cambios nombrados, sin specs aquí.

**New:** `cv-adaptation` (motor: prompts con guardrails, sanitización JD, validación post-diff, async 202+polling) · `adaptation-tracking` (persistencia `CVAdaptation`, linaje `parent_cv_id`, listado por CV, dedupe `jd_text_hash`)

**Modified:** `billing` — recurso `adaptations_per_month` por tier con 402 al exceder

## Approach

1. Refactor `groq_provider` primero: `max_tokens` por operación (default 800) — tests de paridad match/audit.
2. Migración aditiva validada en Neon branch; tabla propia evita tocar `user_cvs`/`recruiter_candidates`.
3. Doble defensa contra alucinación: guardrails en prompt + validador post-diff determinista con tests obligatorios.
4. Async + polling siguiendo la convención `audit_token` (background task + polling de status).
5. Frontend: `AdaptationResult` compartido para no crecer páginas de 700+ líneas.

## Affected Areas

| Área | Impacto |
|---|---|
| `backend/app/services/llm/groq_provider.py` | Mod — max_tokens por operación |
| `backend/app/db/models.py`, `backend/alembic/` | New — tabla `CVAdaptation` |
| `backend/app/services/adaptation/`, `app/api/v1/` | New — servicio + endpoints async |
| `backend/app/services/tier_limits.py` | Mod — `adaptations_per_month` en `PLAN_LIMITS` |
| `frontend/src/lib/components/`, `routes/profile` | New/Mod — `AdaptationResult` |
| `mcp-adapter/` | Sin cambios |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Alucinación de experiencia | Media | Guardrails + validador post-diff con tests obligatorios; rechazo explícito |
| Prompt injection vía JD | Media | JD como dato no confiable; sanitización + test con payload malicioso |
| Talla excede 600l/single-pr | Alta | Ver Rollout |
| Migración en DB en uso | Baja | Aditiva (tabla nueva), con downgrade, validada en Neon branch |
| Cache dedupe sirve resultado obsoleto tras editar CV | Media | Hash incluye `cv_id` + invalidación al editar el CV fuente (design define) |
| Páginas 700+ líneas crecen | Media | Componente compartido; `/recruiter` intacto |

## Rollout — tensión de tamaño

Feature completo calibrado ~9 semanas (3 llamadas LLM secuenciales: CV → outreach → brief). Slice A concentra el mayor bloque: **~800-1200 líneas / 3-4 PRs** (provider ~80, migración+servicio async ~400, billing ~150, UI ~250). **Excede single-pr/600**: sdd-tasks debe pronosticar y recomendar Feature Branch Chain; `size:exception` NO se asume (requiere aprobación del maintainer por ocurrencia).

## Rollback Plan

Endpoint detrás de feature flag; migración aditiva con `downgrade`; revert por PR; recurso de billing desactivable vía config sin tocar Stripe; cache y tabla `CVAdaptation` son aditivos; sin cambios en MCP/match/audit.

## Dependencies

Groq (modelo con `max_tokens` ≥ 4000 disponible); restricciones Render free tier (timeout ~10s — respetadas por diseño async); infra de billing/tier_limits de Sprint 2 operativa.

## Success Criteria

- [ ] **Honestidad (testable)**: validador post-diff automatizado — toda skill/empresa/fecha del CV adaptado existe en el CV fuente; test adversarial CV+JD pasa sin inventos; adaptación con skill nueva se rechaza
- [ ] Async verificado: ningún request bloquea >10s; 202 + `adaptation_id`; polling refleja `pending/completed/failed`
- [ ] Límites enforced: job_seeker_paid 5/mes → `402 PLAN_LIMIT_REACHED` en la 6.ª; recruiter_starter/business/agency 10/20/ilimitado
- [ ] `max_tokens` por operación sin regresión en match/audit (tests de paridad)
- [ ] `CVAdaptation` persistida con `parent_cv_id` (sin versionar `UserCV`) y listada por CV
- [ ] Dedupe: misma JD (hash igual) dentro de 24h reutiliza resultado cacheado (test)
- [ ] Payload de prompt injection en JD no altera las instrucciones del sistema (test dedicado)
- [ ] CI verde; `/profile` muestra la adaptación con `AdaptationResult`

## Open Questions (design)

1. ¿Token budget y modelo por operación (calidad vs latencia con `max_tokens` 2000-4000)?
2. ¿Mecánica exacta del validador post-diff (diff estructural vs verificación de subconjunto por campo)?
3. ¿Free tier recibe adaptaciones de prueba (p.ej. 1/mes) o el recurso es exclusivo de planes pagos?
4. ¿Invalidación de cache: incluir `cv_id` en la clave y TTL compartido con retención free 30d?
5. ¿Vinculación futura de adaptaciones del roster reclutador (FK vs `candidate_id`) — diferida a su habilitación?
