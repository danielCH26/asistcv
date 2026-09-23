# Tasks: Sprint 1 — Match JD ↔ Perfil (Slice 1)

## Review Workload Forecast

| Campo | Valor |
|---|---|
| Líneas estimadas totales | ~1280–1380 en 6 PRs |
| Budget por PR (config: `review_budget_lines`) | 600 |
| Riesgo de budget | Low — PR máximo ~350 líneas |
| PRs encadenados recomendados | Yes |
| Split sugerido | Backend: A ∥ B → C → E · Frontend: D1 → D2 |
| Delivery strategy | ask-on-risk |
| Estrategia de cadena | Feature Branch Chain (cerrada en proposal/design) |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

Nota: el budget del proyecto es 600 líneas/PR (config.yaml); la guard default de 400 queda cubierta por el split en 6 PRs. Decisiones de naming ya cerradas: historial = `GET /v1/analyses` + `GET /v1/analyses/{id}` (REST sobre el recurso); env del frontend = `PUBLIC_BACKEND_API_KEY`.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Migración vectores + persistencia transaccional + historial | PR-A | `pytest backend/tests -k "migration or match or analyses"` | Alembic up/down en Neon branch + `POST /v1/match` en dev | Revert PR-A + `alembic downgrade -1` (aditivo, sin pérdida) |
| 2 | Auth por API key | PR-B | `pytest backend/tests -k auth` | Arranque con y sin `BACKEND_API_KEY` | Revert PR-B (independiente de A) |
| 3 | Retrieval semántico con umbral | PR-C | `pytest backend/tests -k retrieval` | Perfil >3000 chars + JD real en dev | Revert PR-C (sin C, el match usa perfil completo) |
| 4 | MCP a producción | PR-E | Smoke del adapter contra Render | Adapter local + JD real vía MCP | Revert PR-E (solo config) |
| 5 | Frontend core | PR-D1 | `npm run build && npm run check` (frontend/) | Build con `PUBLIC_BACKEND_API_KEY` + UI contra Render | Revert PR-D1 (directorio frontend/) |
| 6 | Frontend historial + i18n CI | PR-D2 | `npm run build && npm run test` (frontend/) | Navegación `/history` y `/history/[id]` contra prod | Revert PR-D2 |

## Resumen de tasks

| ID | Task | Issue | PR | Depende | Tamaño |
|---|---|---|---|---|---|
| A1 | Agregar `pgvector` a `backend/pyproject.toml` | #14 | A | — | S |
| A2 | Migración 002: vectores + HNSW + FK `analyses.profile_id` | #14 | A | A1 | M |
| A3 | Modelos `app/db/models.py`: `Vector(1024)` + `profile_id` | #14 | A | A2 | S |
| A4 | `GET /v1/analyses` + `GET /v1/analyses/{id}` | #17 | A | A3 | M |
| A5 | Persistencia transaccional en `POST /v1/match` | #17 | A | A3 | L |
| A6 | Re-embedding on-demand del perfil en flujo match | #17 | A | A3 | M |
| A7 | Tests de migración up/down | #20 | A | A2 | S |
| A8 | Tests persistencia + historial (matriz escenarios) | #20 | A | A4, A5 | M |
| B1 | `app/api/deps.py` con `verify_api_key` | #15 | B | — | S |
| B2 | Wiring en `main.py` + root + docs condicional | #15 | B | B1, B3 | S |
| B3 | `backend_api_key` en `app/core/config.py` | #15 | B | — | S |
| B4 | Tests de auth (modos protegido/abierto, exenciones) | #20 | B | B2 | S |
| C1 | `RETRIEVAL_SIZE_THRESHOLD_CHARS=3000` + `RETRIEVAL_TOP_K=8` | #16 | C | — | S |
| C2 | `app/services/retrieval.py`: segmentación + ranking coseno + caché | #16 | C | C1 | L |
| C3 | Fallbacks: embedding ausente / error pgvector | #16 | C | C2 | M |
| C4 | Conectar retrieval en `match.py` + logging estructurado | #16 | C | C2 | S |
| C5 | Tests retrieval + fallbacks + snapshot de prompts | #20 | C | C3, C4 | M |
| E1 | MCP: `backend_url` → Render + timeout 60 s | #18 | E | B deployado | S |
| E2 | MCP: `backend_api_key` + formatos | #18 | E | E1 | S |
| E3 | Smoke del adapter contra Render | #20 | E | E2 | S |
| D1.1 | Scaffold SvelteKit + `adapter-static` | #19 | D1 | — | M |
| D1.2 | i18n `svelte-i18n` + catálogos ES/EN + `LanguageToggle` | #19 | D1 | D1.1 | M |
| D1.3 | Cliente API + guard de env + tipos | #19 | D1 | D1.1 | M |
| D1.4 | Stores `analysisStore` / `historyStore` | #19 | D1 | D1.3 | S |
| D1.5 | Ruta `/`: `JdForm` + vista resultado + estados | #19 | D1 | D1.4 | L |
| D2.1 | Ruta `/history`: `HistoryList` | #19 | D2 | D1.5 | M |
| D2.2 | Ruta `/history/[id]`: detalle | #19 | D2 | D2.1 | M |
| D2.3 | Paridad de claves i18n en CI | #19, #20 | D2 | D1.2 | S |
| D2.4 | Integración prod: CORS en Render + env en Cloudflare Pages | #19 | D2 | D1.3 | S |

## Breakdown por PR

### PR-A — Migración vectores + persistencia + historial (~350 l) — Issues #14, #17, #20

- [ ] A1. Agregar `pgvector` a `backend/pyproject.toml`
  - AC: dependencia instalada en CI; `from pgvector.sqlalchemy import Vector` importa sin error; stub de mypy ya declarado sigue vigente.
- [ ] A2. Crear `backend/alembic/versions/002_add_vector_columns.py` (100% aditiva)
  - AC: `embedding vector(1024)` + `embedding_model varchar(100)` en `job_descriptions`, `analyses` y `profiles`; FK NULLable `analyses.profile_id → profiles(id)` (delta incorporado, ya va en esta migración); 3 índices HNSW con `vector_cosine_ops`; `alembic upgrade head` y `downgrade -1` validados en Neon branch sin pérdida de datos.
  - Escenarios: semantic-retrieval — "Índice HNSW presente post-migración".
- [ ] A3. Actualizar `backend/app/db/models.py`
  - AC: columnas tipadas `Vector(1024)` + `analyses.profile_id`; modelos reflejan mig 002; mypy pasa; roundtrip ORM guarda y lee un vector de 1024 floats.
- [ ] A4. Crear `backend/app/api/v1/analyses.py` — historial (delta incorporado: `GET /v1/analyses/{id}`)
  - AC listado: orden `created_at DESC`; `[]` si vacío; `?profile_id=` filtra; `limit` default 20 (max 100), `offset` default 0; items con `id`, `profile_id`, `job_description_id`, `score`, `created_at`.
  - AC detalle: análisis completo + título del JD; 404 si el id no existe.
  - Escenarios: match-analysis — "Listado cronológico inverso", "Historial vacío", "Filtrar historial por perfil".
- [ ] A5. Modificar `backend/app/api/v1/match.py` — transacción única al final
  - AC: todo I/O externo (HF, Groq) antes de abrir la transacción; INSERT de JD (con embedding + modelo) e INSERT de analyses (FK JD, `profile_id`, `profile_snapshot`, score, strengths, gaps, energy_level, reasoning, embedding) en una transacción; fallo LLM no-429 → 502 sin persistir; 429 agotado → 429 sin persistir; fallo DB → 503 con stack trace y request id; fallo HF embeddings → 502 sin persistir nada.
  - Escenarios: match-analysis — "Happy path", "Validación JD corto 422", "Perfil inexistente 404", "Error del LLM 5xx", "Rate limit 429", "Error de base de datos", "JD nuevo con embedding", "Falla del proveedor de embeddings".
- [ ] A6. Re-embedding on-demand del perfil en el flujo match
  - AC: si `profiles.embedding` es NULL o `embedding_model != settings.hf_embedding_model` → regenerar vía `generate_embedding` y persistir con warning logueado; el embedding del JD histórico nunca se regenera.
  - Escenarios: semantic-retrieval — "Perfil nuevo genera embedding", "Re-cálculo al actualizar perfil".
- [ ] A7. Tests de migración (extender `test_migrations.py`)
  - AC: up/down reversibles; índices HNSW, columnas y FK verificados por introspección post-up.
  - Escenarios: semantic-retrieval — "Índice HNSW presente post-migración".
- [ ] A8. Tests de persistencia + historial (base de la matriz test→scenario de #20)
  - AC: un test por cada escenario listado en A4/A5; verificación de ausencia de escritura tras fallos; piso de 49 tests vigente, CI en verde.

# Tasks: Sprint 1 — Match JD ↔ Perfil (Slice 1)

## Review Workload Forecast

| Campo | Valor |
|---|---|
| Líneas estimadas totales | ~1280–1380 en 6 PRs |
| Budget por PR (config: `review_budget_lines`) | 600 |
| Riesgo de budget | Low — PR máximo ~350 líneas |
| PRs encadenados recomendados | Yes |
| Split sugerido | Backend: A ∥ B → C → E · Frontend: D1 → D2 |
| Delivery strategy | ask-on-risk |
| Estrategia de cadena | Feature Branch Chain (cerrada en proposal/design) |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

Nota: el budget del proyecto es 600 líneas/PR (config.yaml); la guard default de 400 queda cubierta por el split en 6 PRs. Decisiones de naming ya cerradas: historial = `GET /v1/analyses` + `GET /v1/analyses/{id}` (REST sobre el recurso); env del frontend = `PUBLIC_BACKEND_API_KEY`.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Migración vectores + persistencia transaccional + historial | PR-A | `pytest backend/tests -k "migration or match or analyses"` | Alembic up/down en Neon branch + `POST /v1/match` en dev | Revert PR-A + `alembic downgrade -1` (aditivo, sin pérdida) |
| 2 | Auth por API key | PR-B | `pytest backend/tests -k auth` | Arranque con y sin `BACKEND_API_KEY` | Revert PR-B (independiente de A) |
| 3 | Retrieval semántico con umbral | PR-C | `pytest backend/tests -k retrieval` | Perfil >3000 chars + JD real en dev | Revert PR-C (sin C, el match usa perfil completo) |
| 4 | MCP a producción | PR-E | Smoke del adapter contra Render | Adapter local + JD real vía MCP | Revert PR-E (solo config) |
| 5 | Frontend core | PR-D1 | `npm run build && npm run check` (frontend/) | Build con `PUBLIC_BACKEND_API_KEY` + UI contra Render | Revert PR-D1 (directorio frontend/) |
| 6 | Frontend historial + i18n CI | PR-D2 | `npm run build && npm run test` (frontend/) | Navegación `/history` y `/history/[id]` contra prod | Revert PR-D2 |

## Resumen de tasks

| ID | Task | Issue | PR | Depende | Tamaño |
|---|---|---|---|---|---|
| A1 | Agregar `pgvector` a `backend/pyproject.toml` | #14 | A | — | S |
| A2 | Migración 002: vectores + HNSW + FK `analyses.profile_id` | #14 | A | A1 | M |
| A3 | Modelos `app/db/models.py`: `Vector(1024)` + `profile_id` | #14 | A | A2 | S |
| A4 | `GET /v1/analyses` + `GET /v1/analyses/{id}` | #17 | A | A3 | M |
| A5 | Persistencia transaccional en `POST /v1/match` | #17 | A | A3 | L |
| A6 | Re-embedding on-demand del perfil en flujo match | #17 | A | A3 | M |
| A7 | Tests de migración up/down | #20 | A | A2 | S |
| A8 | Tests persistencia + historial (matriz escenarios) | #20 | A | A4, A5 | M |
| B1 | `app/api/deps.py` con `verify_api_key` | #15 | B | — | S |
| B2 | Wiring en `main.py` + root + docs condicional | #15 | B | B1, B3 | S |
| B3 | `backend_api_key` en `app/core/config.py` | #15 | B | — | S |
| B4 | Tests de auth (modos protegido/abierto, exenciones) | #20 | B | B2 | S |
| C1 | `RETRIEVAL_SIZE_THRESHOLD_CHARS=3000` + `RETRIEVAL_TOP_K=8` | #16 | C | — | S |
| C2 | `app/services/retrieval.py`: segmentación + ranking coseno + caché | #16 | C | C1 | L |
| C3 | Fallbacks: embedding ausente / error pgvector | #16 | C | C2 | M |
| C4 | Conectar retrieval en `match.py` + logging estructurado | #16 | C | C2 | S |
| C5 | Tests retrieval + fallbacks + snapshot de prompts | #20 | C | C3, C4 | M |
| E1 | MCP: `backend_url` → Render + timeout 60 s | #18 | E | B deployado | S |
| E2 | MCP: `backend_api_key` + formatos | #18 | E | E1 | S |
| E3 | Smoke del adapter contra Render | #20 | E | E2 | S |
| D1.1 | Scaffold SvelteKit + `adapter-static` | #19 | D1 | — | M |
| D1.2 | i18n `svelte-i18n` + catálogos ES/EN + `LanguageToggle` | #19 | D1 | D1.1 | M |
| D1.3 | Cliente API + guard de env + tipos | #19 | D1 | D1.1 | M |
| D1.4 | Stores `analysisStore` / `historyStore` | #19 | D1 | D1.3 | S |
| D1.5 | Ruta `/`: `JdForm` + vista resultado + estados | #19 | D1 | D1.4 | L |
| D2.1 | Ruta `/history`: `HistoryList` | #19 | D2 | D1.5 | M |
| D2.2 | Ruta `/history/[id]`: detalle | #19 | D2 | D2.1 | M |
| D2.3 | Paridad de claves i18n en CI | #19, #20 | D2 | D1.2 | S |
| D2.4 | Integración prod: CORS en Render + env en Cloudflare Pages | #19 | D2 | D1.3 | S |

## Breakdown por PR

### PR-A — Migración vectores + persistencia + historial (~350 l) — Issues #14, #17, #20

- [x] A1. Agregar `pgvector` a `backend/pyproject.toml`
  - AC: dependencia instalada en CI; `from pgvector.sqlalchemy import Vector` importa sin error; stub de mypy ya declarado sigue vigente.
- [x] A2. Crear `backend/alembic/versions/002_add_vector_columns.py` (100% aditiva)
  - AC: `embedding vector(1024)` + `embedding_model varchar(100)` en `job_descriptions`, `analyses` y `profiles`; FK NULLable `analyses.profile_id → profiles(id)` (delta incorporado, ya va en esta migración); 3 índices HNSW con `vector_cosine_ops`; `alembic upgrade head` y `downgrade -1` validados en Neon branch sin pérdida de datos.
  - Escenarios: semantic-retrieval — "Índice HNSW presente post-migración".
- [x] A3. Actualizar `backend/app/db/models.py`
  - AC: columnas tipadas `Vector(1024)` + `analyses.profile_id`; modelos reflejan mig 002; mypy pasa; roundtrip ORM guarda y lee un vector de 1024 floats.
- [x] A4. Crear `backend/app/api/v1/analyses.py` — historial (delta incorporado: `GET /v1/analyses/{id}`)
  - AC listado: orden `created_at DESC`; `[]` si vacío; `?profile_id=` filtra; `limit` default 20 (max 100), `offset` default 0; items con `id`, `profile_id`, `job_description_id`, `score`, `created_at`.
  - AC detalle: análisis completo + título del JD; 404 si el id no existe.
  - Escenarios: match-analysis — "Listado cronológico inverso", "Historial vacío", "Filtrar historial por perfil".
- [x] A5. Modificar `backend/app/api/v1/match.py` — transacción única al final
  - AC: todo I/O externo (HF, Groq) antes de abrir la transacción; INSERT de JD (con embedding + modelo) e INSERT de analyses (FK JD, `profile_id`, `profile_snapshot`, score, strengths, gaps, energy_level, reasoning, embedding) en una transacción; fallo LLM no-429 → 502 sin persistir; 429 agotado → 429 sin persistir; fallo DB → 503 con stack trace y request id; fallo HF embeddings → 502 sin persistir nada.
  - Escenarios: match-analysis — "Happy path", "Validación JD corto 422", "Perfil inexistente 404", "Error del LLM 5xx", "Rate limit 429", "Error de base de datos", "JD nuevo con embedding", "Falla del proveedor de embeddings".
- [x] A6. Re-embedding on-demand del perfil en el flujo match
  - AC: si `profiles.embedding` es NULL o `embedding_model != settings.hf_embedding_model` → regenerar vía `generate_embedding` y persistir con warning logueado; el embedding del JD histórico nunca se regenera.
  - Escenarios: semantic-retrieval — "Perfil nuevo genera embedding", "Re-cálculo al actualizar perfil".
- [x] A7. Tests de migración (extender `test_migrations.py`)
  - AC: up/down reversibles; índices HNSW, columnas y FK verificados por introspección post-up.
  - Escenarios: semantic-retrieval — "Índice HNSW presente post-migración".
- [x] A8. Tests de persistencia + historial (base de la matriz test→scenario de #20)
  - AC: un test por cada escenario listado en A4/A5; verificación de ausencia de escritura tras fallos; piso de 49 tests vigente, CI en verde.

### PR-B — Auth por API key (~120 l) — Issue #15 (cierre) + #20

- [x] B1. Crear `backend/app/api/deps.py` con `verify_api_key` (dependency, no middleware)
  - AC: `backend_api_key` None → pass-through; key definida → exige `Authorization: Bearer` con `secrets.compare_digest`; 401 sin tocar session ni proveedores externos.
  - Escenarios: match-analysis — "API key inválida o ausente en modo protegido", "Modo abierto sin API key".
- [x] B2. Modificar `backend/app/main.py` — wiring por router + docs condicional
  - AC: `/health` y `/` exentos (root route mínima con nombre/metadata); `/ping`, `/v1/match`, `/v1/analyses` protegidos vía `dependencies=[Depends(verify_api_key)]`; con key definida la app se instancia con `docs_url=None, redoc_url=None, openapi_url=None`; en dev/CI siguen disponibles.
- [x] B3. Verificar/agregar `backend_api_key` en `backend/app/core/config.py`
  - AC: setting opcional (None default) leída de env `BACKEND_API_KEY`; cubierta por tests de Settings.
- [x] B4. Tests de auth
  - AC: 401 sin header; 401 con key incorrecta; 200 en modo abierto; `/health` 200 sin key; `/ping` 401 en modo protegido; OpenAPI 404 en modo protegido y 200 en abierto; usando `dependency_overrides`.
  - Escenarios: match-analysis — ambos scenarios del Requirement "Autenticación por API key".

### PR-C — Retrieval semántico con umbral (~200 l) — Issue #16 + #20

- [x] C1. Agregar `RETRIEVAL_SIZE_THRESHOLD_CHARS=3000` y `RETRIEVAL_TOP_K=8` a `backend/app/core/config.py`
  - AC: defaults en `Settings`; override por env verificado en test.
  - Escenarios: semantic-retrieval — "Umbral configurable desde entorno".
- [x] C2. Crear `backend/app/services/retrieval.py`
  - AC: fragmentos por `experience[i]` y `skills`/`preferences` aplanados por sección, cada uno con origen `(section, index)`; ranking coseno con numpy sobre embeddings de fragmentos vía `generate_embedding`; caché en memoria por `(profile_id, profile.updated_at, embedding_model)`; perfil ≤ umbral → texto completo sin segmentación; interfaz única: embedding del JD → contexto serializable a JSON, sin tipos pgvector expuestos; K=8 fragmentos de ~500 chars.
  - Escenarios: semantic-retrieval — "Perfil chico usa contexto completo", "Perfil grande activa retrieval semántico", "Búsqueda top-k por similitud coseno", "Interfaz agnóstica del backend de vectores".
- [x] C3. Fallbacks del servicio
  - AC: embedding ausente → perfil completo + warning; error pgvector → perfil completo, log nivel `error` con stack trace, y `POST /v1/match` responde 200.
  - Escenarios: semantic-retrieval — "Fallback por embedding ausente", "Fallback por error de pgvector".
- [x] C4. Conectar retrieval en `backend/app/api/v1/match.py` (paso 5 del flujo)
  - AC: contexto = perfil completo si ≤ umbral, si no top-K de fragmentos; logging estructurado por request de `chars_profile`, `retrieval_used`, `fragments_sent` (base para recalibración del umbral).
- [x] C5. Tests retrieval + snapshot de prompts
  - AC: unit tests con fixtures de vectores deterministas; fallbacks cubiertos; snapshots de prompts congelados en este PR — cualquier cambio posterior de prompt exige actualización explícita del snapshot.

### PR-E — MCP a producción (~60 l) — Issue #18 + #20

- [x] E1. `mcp-adapter/src/asistcv_mcp/config.py`: `backend_url` → Render + timeout 30→60 s
  - AC: adapter apunta al backend de Render; timeout efectivo 60 s (cubre cold start 30–50 s).
- [x] E2. `backend_api_key` en config del adapter + formatos
  - AC: adapter envía `Authorization: Bearer` cuando la key está configurada; formatos de salida según issue #18.
- [x] E3. Smoke del adapter contra Render con JD real
  - AC: llamada match vía MCP contra producción responde 200 con análisis completo; sin key se obtiene 401 esperado.
  - Depende de: B mergeado y A+B deployados en Render.

### PR-D1 — Frontend core (~350 l) — Issue #19

- [ ] D1.1. Scaffold SvelteKit + `adapter-static` en `frontend/`
  - AC: `svelte.config.js` con `adapter-static({ fallback: 'index.html' })`, `ssr = false`; `npm run build` genera `build/` con HTML/JS/assets servibles.
  - Escenarios: match-ui — "Build genera sitio estático".
- [ ] D1.2. i18n: `svelte-i18n` + `src/lib/i18n/locales/{es,en}.json` + `LanguageToggle`
  - AC: `init()` con orden localStorage → `navigator.language` (prefijo `en` → inglés) → fallback `es`; toggle persiste en `localStorage`; textos de componentes localizados.
  - Escenarios: match-ui — "Idioma por defecto del navegador", "Toggle manual persistente".
- [ ] D1.3. Cliente API `src/lib/api/client.ts`
  - AC: `Authorization: Bearer ${PUBLIC_BACKEND_API_KEY}` (convención `PUBLIC_` cerrada); timeout 60 s; tipos `MatchAnalysis`/`AnalysisSummary` espejo de Pydantic; build de producción falla con error explícito si la env no está definida.
  - Escenarios: match-ui — "Build falla sin la env var", "Key inyectada en runtime".
- [ ] D1.4. Stores en `src/lib/stores/`
  - AC: `analysisStore` y `historyStore` (writable) con `status: idle | loading | error | done`; sin librerías de estado externas.
- [ ] D1.5. Ruta `/`: `JdForm` + vista resultado
  - AC: validación cliente < 50 chars bloquea envío con mensaje localizado; loading con skeleton + aviso de ~50 s por cold start; 401 → banner accionable de credenciales sin redirect; 5xx/red → error con botón Reintentar; resultado renderiza `ScoreCard` (rojo < 50, amarillo 50–74, verde ≥ 75, constante compartida), `StrengthsGapsList`, `EnergyBadge` (`low|medium|high` coloreado), `ReasoningBox`.
  - Escenarios: match-ui — "Envío exitoso", "Validación cliente de JD corto", "Error 401 mostrado con claridad", "Error de red o 5xx con retry", "Render correcto".

### PR-D2 — Frontend historial + i18n en CI (~300 l) — Issues #19, #20

- [ ] D2.1. Ruta `/history`: `HistoryList` consumiendo `GET /v1/analyses`
  - AC: al montar llama al endpoint con la API key; lista con score, fecha y referencia al JD; paginación con `limit`/`offset`; vacío → "Aún no hay análisis" / "No analyses yet".
  - Escenarios: match-ui — "Carga del historial", "Historial vacío".
- [ ] D2.2. Ruta `/history/[id]`: detalle con `GET /v1/analyses/{id}`
  - AC: reusa `ScoreCard`, `ReasoningBox` y demás componentes; ruta resuelta client-side sin servidor (fallback SPA).
  - Escenarios: match-ui — "SPA routing sin servidor".
- [ ] D2.3. Paridad de claves i18n en CI
  - AC: step de CI compara claves de `es.json` vs `en.json` y valida que toda clave usada en componentes exista en ambos catálogos; CI falla si falta alguna.
  - Escenarios: match-ui — "Cobertura i18n completa".
- [ ] D2.4. Integración con producción
  - AC: dominio de Cloudflare Pages agregado a `CORS_ORIGINS` en Render; `PUBLIC_BACKEND_API_KEY` configurada en el build de Pages; flujo completo JD → resultado + historial funciona contra producción.

## Forecast de líneas por PR vs budget 600

| PR | Contenido | Est. líneas | Budget 600 | Margen |
|---|---|---|---|---|
| A | Migración + persistencia + historial + tests | ~350 | OK | ~250 |
| B | Auth + wiring + tests | ~120 | OK | ~480 |
| C | Retrieval + fallbacks + tests | ~200 | OK | ~400 |
| E | MCP producción | ~60 | OK | ~540 |
| D1 | Frontend core | ~350 | OK | ~250 |
| D2 | Frontend historial + i18n CI | ~300 | OK | ~300 |
| **Total** | | **~1380** | 6 PRs | Ningún PR excede 600 |

(Design estimó 1280 con D2=200; se presupuesta D2=300 por conservadurismo. Ambos escenarios quedan dentro de budget.)

## Plan de merge (lanes y orden)

Feature Branch Chain con tracker `feature/sprint-1-match-jd`; cada PR child apunta a la rama anterior de su lane; solo el tracker mergea a main.

- **LANE 1 (backend)**: PR-A → PR-C. Merge de A habilita C (columnas vector).
- **LANE 2 (backend)**: PR-B (paralelo con A) → PR-E (requiere A+B deployados en Render).
- **LANE 3 (frontend)**: scaffold → PR-D1 (requiere C en producción + CORS) → PR-D2 (sobre rama de D1).

Orden de merge: A ∥ B → C → E, en paralelo con D1 → D2. Semana 1: A, B, scaffold frontend contra mocks. Semana 2: C, deploy Render, E, D1, D2. Cada PR trae sus tests para mantener CI verde (49 tests actuales como piso).

## Riesgos y micro-deltas de spec (no se editan specs en esta fase)

1. **Micro-delta match-analysis**: falta ADDED Requirement para `GET /v1/analyses/{id}` (detalle, requerido por `/history/[id]`). Agregarlo antes/durante sdd-apply de PR-A; incluir escenario 404 para id inexistente (hoy sin cobertura en spec).
2. **Divergencia de ruta frontend**: el scenario "SPA routing sin servidor" del spec match-ui usa `/analyses/123`, pero el design fija `/history/[id]`. Adoptar `/history/[id]` (design gana); micro-delta de spec recomendado antes de verify.
3. **Default del umbral**: spec semantic-retrieval menciona "default ~2000"; el design cerró 3000. El test de "Umbral configurable desde entorno" debe validar el override por env, no el número default; micro-delta de texto recomendado.
4. **Momento del embedding del perfil**: el spec dice "al crearse o actualizarse", pero no hay endpoint de creación de perfiles en scope; el design define cálculo on-demand en el flujo match (A6). Micro-delta de wording para evitar fricción en verify.
5. **Paginación sin scenarios**: `limit`/`offset` no tienen escenario en spec; quedan cubiertos por design (20 default, max 100, offset 0). Riesgo bajo; verificar en sdd-verify.
6. **Riesgo heredado**: latencia HF on-demand en perfiles grandes — mitigada por caché (C2); si D2 se atrasa, se mueve a mini-sprint (fallback ya documentado en design).
