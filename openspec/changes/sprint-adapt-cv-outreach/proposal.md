# Proposal: Sprint 3 — Adaptación de CV a JD (Slice A de adapt-cv-outreach)

## Intent

Entregar la capacidad core del producto: adaptar un CV existente a una JD específica sin inventar experiencia. Sprint 2 entregó cuentas, CVs y billing; este cambio activa el segundo pilar de valor. La honestidad es un invariante no negociable: la adaptación reordena y reformula, nunca fabrica.

## Scope

### Recomendación de slicing

Exploración estima rango honesto LARGE y el sprint anterior superó estimaciones 3x. **Recomendación: sliced-a-b-c** — el valor core envía pronto y el riesgo de alucinación queda aislado al final.

- **Slice A (ESTE cambio)**: adaptación de CV de punta a punta.
- **Slice B (follow-up, `sprint-outreach-generation`)**: mensajes de outreach.
- **Slice C (follow-up, `sprint-company-brief`)**: brief de empresa (mayor riesgo de alucinación, último).

### In Scope (Slice A)

- `max_tokens` por operación en `groq_provider.py` (hoy 800 hardcodeado; adaptación exige 2000-4000+) sin regresar match/audit
- Migración aditiva: `source` (enum) + `parent_cv_id` en `user_cvs` y `recruiter_candidates` (linaje de versiones)
- Servicio de adaptación role-agnóstico (seeker y roster): guardrails de honestidad en prompt, JD tratada como input no confiable, validación post-diff (toda afirmación del CV adaptado debe existir en el CV fuente)
- API `POST /v1/adaptations` con patrón asíncrono (202 + polling u alternativa — decide design)
- Recurso de billing `adaptations_per_month` (sugerido: seeker 5; recruiter 20/50/ilimitado — design define) con enforcement
- Frontend: componente compartido `AdaptationResult` + integración en `/profile`

### Out of Scope

- Outreach (Slice B); company brief (Slice C); UI de adaptación en `/recruiter` (follow-up); export PDF del CV adaptado; streaming de tokens; tracking de pipeline (sprint futuro)

## Capabilities

> Contrato proposal → specs. Slices B/C quedan como cambios nombrados, sin specs aquí.

**New:** `cv-adaptation` (adaptación core: prompts, honestidad, sanitización JD) · `adaptation-tracking` (linaje, versiones, persistencia)

**Modified:** `cv-management` — `source`/`parent_cv_id` + listado de versiones. `billing` — recurso `adaptations_per_month` por tier. `recruiter-roster` — linaje en CVs de candidatos.

## Approach

1. Refactor `groq_provider` primero: `max_tokens` como parámetro por operación (default 800) — tests de paridad match/audit.
2. Migración aditiva validada en Neon branch; linaje en ambas tablas (barato ahora, costoso después).
3. Doble defensa contra alucinación: guardrails en prompt + validador post-diff determinista (empresas/fechas/skills del output ⊆ fuente).
4. Latencia: patrón asíncrono — la decisión central se resuelve en design (ver Open Questions).
5. Frontend: `AdaptationResult` compartido para no crecer páginas de 700+ líneas.

## Affected Areas

| Área | Impacto |
|---|---|
| `backend/app/services/llm/groq_provider.py` | Mod — max_tokens por operación |
| `backend/app/db/models.py`, `backend/alembic/` | Mod — migración linaje |
| `backend/app/services/adaptation/`, `app/api/v1/` | New — servicio + endpoint |
| `backend/app/services/billing/` | Mod — enforcement adaptaciones |
| `frontend/src/lib/components/`, `routes/profile` | New/Mod — AdaptationResult |
| `mcp-adapter/` | Sin cambios |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| LLM 5-15s vs timeout Render ~10s | Alta | Patrón async (design decide); token budget acotado |
| Alucinación de experiencia | Media | Guardrails + validador post-diff con tests obligatorios |
| Prompt injection vía JD | Media | JD como dato no confiable; sanitización + tests con payloads maliciosos |
| Talla excede 600l/single-pr | Alta | Ver Rollout |
| Migración en tablas en uso | Baja | Aditiva, con downgrade, validada en Neon branch |
| Páginas 700+ líneas crecen | Media | Componente compartido; `/recruiter` intacto |

## Rollout — tensión de tamaño

Estimación honesta LARGE: ~800-1200 líneas / 3-4 PRs (provider ~80, migración+servicio ~400, billing ~150, UI ~250). **Excede single-pr/600**: sdd-tasks debe pronosticar y recomendar Feature Branch Chain; `size:exception` NO se asume (requiere aprobación del maintainer por ocurrencia).

## Rollback Plan

Endpoint detrás de feature flag; migración aditiva con `downgrade`; revert por PR; límites de billing vía config (recurso desactivable sin tocar Stripe); sin cambios en MCP/match/audit.

## Dependencies

Groq (modelo con `max_tokens` ≥ 4000 disponible); restricciones Render free tier; infra de billing de Sprint 2 operativa.

## Success Criteria

- [ ] **Honestidad (testable)**: validador post-diff automatizado — toda experiencia/skill/fecha del CV adaptado existe en el CV fuente; test con CV+JD adversarial pasa sin inventos
- [ ] `max_tokens` por operación sin regresión en match/audit (tests de paridad)
- [ ] Límites por tier enforced: seeker 5/mes → 402 con upgrade al exceder; recruiter según tier
- [ ] CV adaptado persistido con linaje (`source`, `parent_cv_id`) y listado como versión
- [ ] Ningún request bloquea >10s: patrón async de design implementado y verificado
- [ ] Payload de prompt injection en JD no altera las instrucciones del sistema (test dedicado)
- [ ] CI verde; `/profile` muestra la adaptación con `AdaptationResult`

## Open Questions (design)

1. **Latency/timeout (LA decisión central)**: ¿async con background task + polling, streaming SSE, o upgrade de host? Render free ~10s vs adaptación 5-15s.
2. ¿Token budget y modelo por operación (calidad vs latencia)?
3. ¿Límites exactos recruiter (20/50/ilimitado) y ventana de reset?
4. ¿Validador post-diff: diff estructural exacto vs validación LLM secundaria?
5. ¿Export PDF del CV adaptado en Slice A o diferido?
