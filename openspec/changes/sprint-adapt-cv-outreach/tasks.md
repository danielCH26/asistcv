# Tasks: Sprint 3 — Adaptación de CV a JD (Slice A)

Cadena de 3 PRs apilados a main (locked en design §10.3). Trazabilidad: cada tarea referencia
el requirement de spec que la origina (`cv-adaptation` = cvA, `adaptation-billing` = bill,
`adaptation-experience` = exp, `cv-management` = cvM).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~2.880 (PR1 ~430 + PR2 ~1.700 + PR3 ~750) |
| 600-line budget risk | High (PR2 y PR3 exceden; ver tabla por PR) |
| Chained PRs recommended | Yes (ya decidido: 3 PRs apilados) |
| Suggested split | PR1 foundation → PR2 backend → PR3 frontend |
| Delivery strategy | single-pr (equivale: cadena ya dimensionada) |
| Chain strategy | stacked-to-main |

```text
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High
```

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Migraciones 014–017 + modelos | PR1 | `uv run pytest tests/test_migrations.py tests/test_models.py -v` | `uv run alembic upgrade head` + `downgrade -1` ×4 en Neon branch | Downgrade encadenado 017→014; sin flag (nada consume las tablas aún) |
| 2 | Motor de adaptación backend | PR2 | `uv run pytest tests/test_adaptations_endpoint.py -v` | Suite adaptación completa (72 tests) | `git revert` del merge; kill-switch `ADAPTATION_ENABLED=false` → 503 sin redeploy |
| 3 | UI /profile + sweeper cron | PR3 | `npm run test -- src/lib/stores/adaptation.test.ts` | `npm run test && npm run build` | `git revert` del merge; sin cambios de DB; endpoint queda intacto |

---

## PR1 — foundation: migraciones + modelos (~430l)

**Depende de**: nada (primer eslabón). Merge a main antes de abrir PR2.
**Trazabilidad dominante**: cvA-R6 (modelo CVAdaptation + RLS), cvM-R2 (sin cascada destructiva), bill-R3/R4 (contador).

- [ ] **PR1.1** — Migración 014: `content_version` en `users_cvs` (~30l)
  - Columna `INT NOT NULL DEFAULT 1`; downgrade la elimina. Diseño §2.1 (D2: se bumpa en PATCH, la lee la cache).
  - Archivos: `backend/alembic/versions/014_users_cvs_content_version.py`. Depende de: —.
- [ ] **PR1.2** — Migración 015: tabla `cv_adaptations` (~90l)
  - 13 columnas: `parent_cv_id` FK **SET NULL**, `owner_user_id` FK CASCADE, `content_version` (snapshot), `jd_text_hash`, `jd_text` nullable, `adapted_cv_json` JSONB, `score_estimated`, `status`, `error_code`, `retry_attempts`, `created_at/started_at/completed_at/failed_at`. Índices: `(owner_user_id, created_at DESC)`, parcial cache `(parent_cv_id, content_version, jd_text_hash) WHERE status='completed'`, parcial sweeper `(status, created_at) WHERE status='pending'`. → cvA-R6, cvM-R2.
  - Archivos: `backend/alembic/versions/015_cv_adaptations.py`. Depende de: PR1.1.
- [ ] **PR1.3** — Migración 016: RLS en `cv_adaptations` (~45l)
  - `ENABLE`+`FORCE ROW LEVEL SECURITY`; política bypass service (`app.current_user_id = '0'`) para sweeper; 4 políticas owner (`select/insert/update/delete`) vía `app_current_user_id()`. Espejo del patrón 011. → cvA-R6 (RLS cross-user / cross-role).
  - Archivos: `backend/alembic/versions/016_cv_adaptations_rls.py`. Depende de: PR1.2.
- [ ] **PR1.4** — Migración 017: `adaptations_used` en `usage_counters` (~20l)
  - `INT NOT NULL DEFAULT 0`; coexiste con `matches_used`/`analyses_used`; reset mensual heredado del rollover de Sprint 2. → bill-R3, bill-R4.
  - Archivos: `backend/alembic/versions/017_usage_counters_adaptations.py`. Depende de: —.
- [ ] **PR1.5** — Modelos SQLAlchemy (~70l)
  - Modelo `CVAdaptation`; `content_version` en `UserCV`; `adaptations_used` en `UsageCounter`. → cvA-R6.
  - Archivos: `backend/app/db/models.py`. Depende de: PR1.2, PR1.4.
- [ ] **PR1.6** — Kill-switch en config (~5l)
  - `ADAPTATION_ENABLED: bool = True` (diseño §10.4); el router de PR2 devolverá 503 `FEATURE_DISABLED` si está en `False`.
  - Archivos: `backend/app/core/config.py`. Depende de: —.
- [ ] **PR1.7** — Tests de migraciones y modelos (~120l)
  - `test_migrations.py`: roundtrip upgrade/downgrade 014–017, índices parciales presentes, políticas RLS creadas. `test_models.py`: columnas de `CVAdaptation`, FK `ON DELETE SET NULL` (borrar CV deja fila huérfana con `parent_cv_id=null`), defaults de server. → cvA-R6, cvM-R2.
  - Archivos: `backend/tests/test_migrations.py`, `backend/tests/test_models.py`. Depende de: PR1.1–PR1.5.
- [ ] **PR1.8** — Validación en Neon branch (~0l, operación)
  - `alembic upgrade head` y roundtrip `downgrade -1` ×4 sobre branch de Neon contra DB en uso; sin errores. Diseño §10.2. Depende de: PR1.1–PR1.4.

**Tests requeridos PR1**: roundtrip 014–017, DDL de índices parciales y RLS, modelo + FK SET NULL (~8–10 tests).
**Verificación** (desde `backend/`):
- `uv run ruff check app tests`
- `uv run mypy app`
- `uv run pytest tests/test_migrations.py tests/test_models.py -v`
- `uv run alembic upgrade head && uv run alembic downgrade -1` (×4, Neon branch)
**Rollback**: cada migración revierte con `alembic downgrade -1` (orden 017→016→015→014). Sin feature flag necesario: nada consume las tablas todavía.

---

## PR2 — backend logic: motor de adaptación (~1.700l)

**Depende de**: PR1 mergeado (tablas, modelos, flag). Merge a main antes de abrir PR3. Tras merge, el endpoint existe pero la UI no lo invoca.
**Trazabilidad dominante**: cvA-R1–R8, bill-R1–R5, cvM-R1.

- [ ] **PR2.1** — RED: tests de paridad match/audit con `max_tokens` explícito (~30l)
  - Extender `test_match_regression.py` y `test_audit_runner_regression.py`: assert de que `_complete_json` recibe `max_tokens=800` en el payload mockeado. Falla al inicio (la firma aún no acepta el parámetro). → cvA-R8.
  - Archivos: `backend/tests/test_match_regression.py`, `backend/tests/test_audit_runner_regression.py`. Depende de: —.
- [ ] **PR2.2** — GREEN: `max_tokens` por operación en el provider (~40l)
  - `_complete_json(..., max_tokens: int = 800)`; `match` y `audit` pasan 800 explícito; sin cambio de comportamiento para ellos. → cvA-R8.
  - Archivos: `backend/app/llm/base.py`, `backend/app/llm/groq_provider.py`. Depende de: PR2.1.
- [ ] **PR2.3** — RED: tests unitarios del validador (~190l, 28 tests)
  - Normalizador D1 (15), `validate_adaptation` subset (8), `sanitize_jd` (5). Incluye casos de spec: skill nueva → rechazo, empresa inventada → rechazo, fecha modificada → rechazo, reformulación permitida → acepta, payload de inyección neutralizado. → cvA-R4.
  - Archivos: `backend/tests/test_adaptation_validator.py`. Depende de: —.
- [ ] **PR2.4** — GREEN: `adaptation_validator.py` (~190l)
  - `sanitize_jd` (escape de delimitadores, longitud limitada), pipeline de normalización (lowercase/trim/canonicalización), `validate_adaptation`: `skills ⊆ source.skills`, `experience[].company ⊆ source ∪ aliases`, fechas ISO 8601 inmutables. → cvA-R4.
  - Archivos: `backend/app/services/adaptation_validator.py`. Depende de: PR2.3.
- [ ] **PR2.5** — Schemas Pydantic de adaptación (~90l)
  - `AdaptationCreate` (`cv_id`, `jd_text` ≥ 50 chars), `AdaptationStatusResponse` (`adapted_cv`, `outreach: null`, `brief: null` reservados Slice B/C, `error`), `AdaptationListItem`. → cvA-R1/R2, cvM-R1.
  - Archivos: `backend/app/schemas/adaptation.py`. Depende de: —.
- [ ] **PR2.6** — Interfaz LLM `generate_adaptation` (~40l)
  - Contrato en `base.py`, `AdaptationOutput` en `schemas.py`, implementación en `mock.py` para tests. → cvA-R8.
  - Archivos: `backend/app/llm/base.py`, `backend/app/llm/schemas.py`, `backend/app/llm/mock.py`. Depende de: PR2.5.
- [ ] **PR2.7** — Prompts con guardrails + `generate_adaptation` en Groq (~120l)
  - System prompt con instrucciones literales de honestidad y campo `gaps[]`; user template con CV structured + JD saneada entre delimitadores; invoca `_complete_json` con `max_tokens=3000`. → cvA-R4, cvA-R8.
  - Archivos: `backend/app/llm/groq_provider.py`. Depende de: PR2.2, PR2.4, PR2.6.
- [ ] **PR2.8** — Cache por hash de JD (~60l)
  - Clave `(parent_cv_id, content_version, jd_text_hash)`, hash `sha256(jd_text[:500])`, TTL 24 h, lookup sobre índice parcial. → cvA-R5.
  - Archivos: `backend/app/services/adaptation_cache.py`. Depende de: PR2.5.
- [ ] **PR2.9** — RED: tests del runner (~130l, 12 tests)
  - LLM mockeado: retry de validador con prompt reforzado, backoff 5xx, 429 con `Retry-After`, agotamiento → `INVALID_HONESTY`, `LLM_UNAVAILABLE`, path de completion. → cvA-R3.
  - Archivos: `backend/tests/test_adaptation_runner.py`. Depende de: PR2.7.
- [ ] **PR2.10** — GREEN: `adaptation_runner.py` (~180l)
  - Lifecycle pending→started→completed/failed con RLS service context; 1 reintento por honestidad (prompt reforzado), backoff exponencial con jitter (hasta 3), 429 respeta `Retry-After`; `increment_usage("adaptation")` **sólo al completar**; logging de incidentes con `adaptation_id`+`cv_id`. → cvA-R3, bill-R3.
  - Archivos: `backend/app/services/adaptation_runner.py`. Depende de: PR2.7, PR2.9.
- [ ] **PR2.11** — `adaptations_per_month` en `PLAN_LIMITS` (~50l)
  - free 0, seeker_monthly 5, recruiter_starter 10, recruiter_business 20, recruiter_agency `null`; reuso `check_limit`/`increment_usage` sin duplicar enforcement. → bill-R1, bill-R4, bill-R5.
  - Archivos: `backend/app/services/tier_limits.py`. Depende de: —.
- [ ] **PR2.12** — Tests de tier limits (~60l, 6 tests)
  - Valores por tier, `increment_usage("adaptation")`, independencia con `matches_this_month`, reset mensual heredado. → bill-R1/R3/R5.
  - Archivos: `backend/tests/test_tier_limits_adaptation.py`. Depende de: PR2.11.
- [ ] **PR2.13** — Router `adaptations.py` (~150l)
  - `POST /v1/adaptations` → 202 `{adaptation_id, status, poll_url}` (<1s, `asyncio.create_task`); check read-only de límite **antes** de persistir → 402 `PLAN_LIMIT_REACHED` con `{current_tier, limit, upgrade_url}`; `GET /v1/adaptations/{id}`; `GET /v1/cvs/{id}/adaptations` (desc); `POST /internal/adaptations/cleanup` con token HMAC; gate `ADAPTATION_ENABLED`→503; binding `bind_rls_context` como `cvs.py`. Registro en `main.py`. → cvA-R1/R2/R7, bill-R2, cvM-R1.
  - Archivos: `backend/app/api/v1/adaptations.py`, `backend/app/main.py`. Depende de: PR2.5, PR2.8, PR2.10, PR2.11, PR2.14.
- [ ] **PR2.14** — Sweeper service (~30l)
  - `fail_stale_pending(max_age_minutes=10)` → `failed/TIMEOUT`; usa índice parcial de pendings. Diseño §5.4.
  - Archivos: `backend/app/services/adaptation_sweeper.py`. Depende de: PR1 (merge).
- [ ] **PR2.15** — Tests de integración de endpoints (~150l, 10 tests)
  - POST 202 con fila pending, validación 422, 404 `CV_NOT_FOUND` cross-user, 402 sin fila ni incremento, 401 sin tocar DB, GET pending/completed/failed (payloads con `outreach`/`brief` null), listing propio/vacío/ajeno, huérfanas consultables tras borrar CV. Fixtures `mock_llm_provider`/`mock_tier_limits` en conftest. → cvA-R1/R2/R7, bill-R2, cvM-R1/R2.
  - Archivos: `backend/tests/test_adaptations_endpoint.py`, `backend/tests/conftest.py`. Depende de: PR2.13.
- [ ] **PR2.16** — Tests de integración de cache (~100l, 8 tests)
  - Hit dentro de TTL (mismo `adaptation_id`, sin llamada al LLM, sin incremento de contador), miss por JD distinto, miss por CV distinto, miss por CV editado (`content_version` bump), expiración a 25 h. → cvA-R5, bill-R3.
  - Archivos: `backend/tests/test_adaptations_cache.py`. Depende de: PR2.8, PR2.13.
- [ ] **PR2.17** — Tests RLS (~70l, 5 tests)
  - Cross-user SELECT filtrado, cross-role (recruiter) vacío, owner CRUD permitido, bypass service para sweeper. → cvA-R6.
  - Archivos: `backend/tests/test_adaptations_rls.py`. Depende de: PR2.13.
- [ ] **PR2.18** — E2E en staging (~40l, 3 tests)
  - POST → poll → `pending`/`completed` con LLM real; latencia de respuesta 202 < 1s. → cvA-R1/R2/R8.
  - Archivos: `backend/tests/e2e/test_full_adaptation_e2e.py`. Depende de: PR2.13.

**Tests requeridos PR2**: 72 (28 validador + 12 runner + 6 tier + 10 endpoints + 8 cache + 5 RLS + 3 e2e). Paridad match/audit en verde.
**Verificación** (desde `backend/`):
- `uv run ruff check app tests`
- `uv run mypy app`
- `uv run pytest tests/test_adaptation_validator.py tests/test_adaptation_runner.py tests/test_tier_limits_adaptation.py -v`
- `uv run pytest tests/test_adaptations_endpoint.py tests/test_adaptations_cache.py tests/test_adaptations_rls.py -v`
- `uv run pytest tests/test_match_regression.py tests/test_audit_runner_regression.py -v`
- `uv run pytest tests/ -v` (suite completa verde)
**Rollback**: PR2 no contiene migraciones (las tablas ya están en main desde PR1). Rollback = `git revert` del merge. Kill-switch en runtime: `ADAPTATION_ENABLED=false` → 503 `FEATURE_DISABLED` sin redeploy de código.

---

## PR3 — frontend: UI /profile + sweeper cron (~750l)

**Depende de**: PR2 mergeado (contrato de API estable). Último eslabón: tras merge el feature es utilizable.
**Trazabilidad dominante**: exp-R1–R6, cvA-R2 (payload consumido).

- [ ] **PR3.1** — Tipos de API (~35l)
  - `AdaptationStatus`, `AdaptationResultPayload`, `AdaptationListItem` tipados según schema de PR2.
  - Archivos: `frontend/src/lib/api/types.ts`. Depende de: PR2 (merge).
- [ ] **PR3.2** — Cliente HTTP (~55l)
  - `postAdaptation`, `getAdaptation`, `listAdaptations` en `client.ts`; propagación de 401/402/404 con códigos para la UI. → exp-R5.
  - Archivos: `frontend/src/lib/api/client.ts`. Depende de: PR3.1.
- [ ] **PR3.3** — Store de adaptación con polling (~140l)
  - `start()` → pending → completed/failed; schedule **2s×15 → 5s×6 → 30s×2**, abort a los 95s con banner + botones "Reintentar"/"Verificar estado" (poll manual); 3 errores de red consecutivos → mensaje y reintento manual; el poll no aborta por un error aislado. → exp-R3, exp-R4.
  - Archivos: `frontend/src/lib/stores/adaptation.ts`. Depende de: PR3.2.
- [ ] **PR3.4** — Componente `AdaptationResult.svelte` (~170l)
  - Reusa `ScoreCard`, `StrengthsGapsList`, `ReasoningBox` de `MatchResult`; pending = spinner neutro sin secciones vacías; completed = score + strengths/gaps propias + reasoning + sección "Cambios sugeridos"; failed = banner localizado por `error_code` (`INVALID_HONESTY`/`LLM_UNAVAILABLE`/`LLM_RATE_LIMITED`/`TIMEOUT`) + botón "Reintentar" (nuevo POST). → exp-R1.
  - Archivos: `frontend/src/lib/components/AdaptationResult.svelte`. Depende de: PR3.3.
- [ ] **PR3.5** — Slot en `/profile` (~110l)
  - Textarea + botón "Adaptar mi CV"; validación cliente < 50 chars sin HTTP; botón deshabilitado durante envío (doble POST bloqueado); zona reservada para `AdaptationResult`; 402 → upgrade card con `upgrade_url`; 404 → mensaje `CV_NOT_FOUND`; 401 → limpieza de tokens + redirect `/login`. `/recruiter` **no** se toca. → exp-R2/R3/R5.
  - Archivos: `frontend/src/routes/profile/+page.svelte`. Depende de: PR3.3, PR3.4.
- [ ] **PR3.6** — i18n ES/EN (~55l)
  - Bloque `adapt.*` (~25 claves, diseño §9.5) insertado tras `audit.*` en `es.json` y su par en `en.json`; sin strings hardcodeados. → exp-R6.
  - Archivos: `frontend/src/lib/i18n/locales/es.json`, `frontend/src/lib/i18n/locales/en.json`. Depende de: —.
- [ ] **PR3.7** — Workflow del sweeper (~25l)
  - `.github/workflows/adaptation-sweeper.yml`: cron `*/15 * * * *` + `workflow_dispatch`; POST a `/internal/adaptations/cleanup` con `ADAPTATION_CLEANUP_TOKEN`; espejo de `audit-retention.yml`. Diseño §5.4.
  - Archivos: `.github/workflows/adaptation-sweeper.yml`. Depende de: PR2.14 (merge).
- [ ] **PR3.8** — Tests de componente (~70l, 4 tests)
  - Render pending (spinner), completed (todos los sub-componentes + cambios sugeridos), failed ×3 códigos. → exp-R1.
  - Archivos: `frontend/src/lib/components/AdaptationResult.test.ts`. Depende de: PR3.4.
- [ ] **PR3.9** — Tests de store (~45l, 5 tests)
  - start → pending → completed con fake timers + `apiClient` mockeado; manejo 402/404. → exp-R3/R5.
  - Archivos: `frontend/src/lib/stores/adaptation.test.ts`. Depende de: PR3.3.
- [ ] **PR3.10** — Tests de polling (~50l, 4 tests)
  - Fase 1 (2s×15), fase 2 (5s×6), fase 3 (30s×2), give-up a 95s con "Verificar estado". → exp-R4.
  - Archivos: `frontend/src/lib/stores/adaptation.poll.test.ts`. Depende de: PR3.3.
- [ ] **PR3.11** — Test de cobertura i18n + verificación de bundle (~10l, 1 test + check)
  - Extensión del test de cobertura existente: claves `adapt.*` presentes en ambos catálogos. Verificar que el bundle de `/recruiter` no incluye `AdaptationResult` (artefacto de build). → exp-R2, exp-R6.
  - Archivos: test de cobertura i18n existente. Depende de: PR3.6.

**Tests requeridos PR3**: 14 (4 componente + 5 store + 4 polling + 1 i18n). CI de cobertura i18n en verde.
**Verificación** (desde `frontend/`):
- `npm run test` (vitest run)
- `npm run check` (svelte-check)
- `npm run build` + inspección del bundle de `/recruiter` (exp-R2)
**Rollback**: `git revert` del merge de PR3. Sin cambios de DB ni de backend; el endpoint queda operativo aunque sin consumidor. No requiere flag.

---

## Cross-cutting

### Dependencias entre PRs

| Orden | PR | Depende de | Gate de merge |
|---|---|---|---|
| 1 | PR1 foundation | — | Migraciones validadas en Neon; suite de migraciones/modelos verde |
| 2 | PR2 backend | PR1 mergeado a main | 72 tests nuevos + paridad match/audit verde; flag operativo |
| 3 | PR3 frontend | PR2 mergeado a main | 14 tests frontend + build verde; bundle de `/recruiter` sin `AdaptationResult` |

Cada PR mergea a main antes de abrir el siguiente (stacked-to-main). PR2 no abre hasta que las migraciones de PR1 estén en main; PR3 consume el contrato de API de PR2.

### Review Workload Forecast por PR vs presupuesto 600l

| PR | Est. líneas | Presupuesto 600l | Nota |
|---|---|---|---|
| PR1 | ~430 | ✅ dentro | Migraciones aditivas + modelos; diff mecánico, revisión rápida |
| PR2 | ~1.700 | ⚠️ excede (~2,8×) | ~1.090l son tests (72); lógica productiva neta ~600l. Exceso aceptado en design (§10.3); cadena ya dimensionada |
| PR3 | ~750 | ⚠️ excede levemente | ~175l de tests; componente + slot; sin cambios de DB |

**Decision needed before apply: No** — la cadena de 3 PRs quedó dimensionada y bloqueada en el design; el exceso de PR2 (test-dominated) y el exceso leve de PR3 son conocidos y aceptados.

### Constraints

- Toda tarea trazable a un requirement de spec (mapa arriba; `cvA/bill/exp/cvM-Rn`).
- IDs de tarea: `PR1.1…PR1.8`, `PR2.1…PR2.18`, `PR3.1…PR3.11` (37 tareas).
- TDD en PR2: tareas RED preceden a las GREEN del validador y del runner; paridad match/audit primero.
- Invariantes no negociables: honestidad (validador post-diff obligatorio), RLS en toda lectura, slot cobrado sólo al completar, `/recruiter` intacto, `outreach`/`brief` como `null` en Slice A.
