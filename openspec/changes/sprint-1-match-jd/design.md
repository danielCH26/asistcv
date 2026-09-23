# Design: Sprint 1 — Match JD ↔ Perfil (Slice 1)

## Resumen del enfoque técnico

Sprint 0.5 dejó el stack completo en producción (FastAPI + Neon/pgvector, Groq `qwen/qwen3.8-27b`, embeddings HF `BAAI/bge-m3` 1024-dim, CI verde). Este sprint es solo el delta: cerrar el flujo match de punta a punta con persistencia, retrieval semántico con umbral, auth por API key, MCP en producción y frontend estático SvelteKit.

Decisiones ya cerradas que este diseño incorpora como hechos (no se re-debaten):

| # | Decisión cerrada |
|---|---|
| 1 | Auth por API key: `BACKEND_API_KEY` env; si existe, todos los endpoints excepto `/health` exigen `Authorization: Bearer`. Frontend la lee en build-time. MCP adapter ya tiene `backend_api_key` en su config. |
| 2 | Frontend SvelteKit + `adapter-static` → Cloudflare Pages; i18n con `svelte-i18n` (ES/EN, detección de browser + toggle). |
| 3 | Retrieval: infra pgvector (HNSW) + umbral por tamaño; retrieval si el perfil supera el umbral, si no perfil completo. |
| 4 | Transacción única: si el LLM falla, no se persiste nada (JD sin análisis no aporta en single-user). |

Mapa de archivos afectados (detalle por sección):

| Archivo | Acción | PR |
|---|---|---|
| `backend/alembic/versions/002_add_vector_columns.py` | Create | A |
| `backend/app/db/models.py` | Modify — columnas vector + `analyses.profile_id` | A |
| `backend/app/api/v1/analyses.py` | Create — historial | A |
| `backend/app/api/v1/match.py` | Modify — persistencia transaccional | A |
| `backend/app/api/deps.py` | Create — `verify_api_key` | B |
| `backend/app/main.py` | Modify — wiring auth + docs condicional | B |
| `backend/app/core/config.py` | Modify — `RETRIEVAL_SIZE_THRESHOLD_CHARS`, `RETRIEVAL_TOP_K` | C |
| `backend/app/services/retrieval.py` | Create | C |
| `backend/pyproject.toml` | Modify — agregar `pgvector` | A |
| `mcp-adapter/src/asistcv_mcp/config.py` | Modify — URL Render, timeout 60 s | E |
| `frontend/` | Create — app SvelteKit completa | D1/D2 |

---

## 1. Umbral de retrieval (`RETRIEVAL_SIZE_THRESHOLD_CHARS`)

**Decisión**: `RETRIEVAL_SIZE_THRESHOLD_CHARS = 3000` (default en `Settings`, override por env). Complementos: `RETRIEVAL_TOP_K = 8`, fragmentos objetivo de ~500 caracteres.

**Por qué**:

- El perfil seed (~800 chars) y perfiles chicos (< 3000) siempre van por contexto completo: la atención del prompt sobre un texto de ~750 tokens es plena, y no se paga la latencia de embeddings en el camino crítico.
- Perfiles reales de devs (5–15 experiencias: 2000–15000 chars) cruzan el umbral en la zona media del rango. Con 15000 chars (~3750 tokens) el perfil sigue entrando cómodo en la ventana de 131k de Qwen, pero el punto no es la ventana: es la dilución de atención sobre lo relevante. 3000 es el compromiso donde la dilución empieza a ser medible sin castigar perfiles medianos.
- Contexto en modo retrieval acotado: K=8 × ~500 chars ≈ 4000 chars máximo enviados al LLM — comparable en tamaño al umbral, pero enfocado.
- La segmentación en fragmentos es sobre el JSON del perfil, sin tabla intermedia: cada experiencia (`experience[i]`) es un fragmento, y `skills` / `preferences` se aplanan a texto por sección. Cada fragmento conserva su origen `(section, index)` — cumple el scenario "conserva su sección de origen" de `semantic-retrieval`. El ranking de fragmentos es coseno en proceso con numpy (ya es dependencia) sobre embeddings de fragmentos calculados on-demand vía `generate_embedding` (interfaz existente en `app/llm/base.py`), con caché en memoria indexada por `(profile_id, profile.updated_at, embedding_model)` — en single-user, el re-costo solo aparece al editar el perfil.

**Recalibración documentada**:

1. Cada request match loguea `chars_profile`, `retrieval_used`, `fragments_sent` (logging estructurado ya existe).
2. Tras los 20 JDs reales de la meta ROADMAP, comparar score del mismo JD con `RETRIEVAL_SIZE_THRESHOLD_CHARS=999999` (perfil completo) vs `3000`: si la varianza de score supera ±10 puntos, ajustar.
3. El override es env var en Render (aplica al redeploy, porque `get_settings()` está cacheada por proceso). No requiere cambio de código.

**Alternativas descartadas**:

- `2000`: perfiles medianos (2000–3000) caen al path de retrieval ganando poco (aún son pequeños para diluir) y pagando latencia HF en el camino crítico.
- `4000+`: pospone el beneficio; los perfiles de 4000–15000 chars van completos y la dilución persiste exactamente donde más molesta.
- "Siempre retrieval": over-engineering para single-user; agrega dependencia de HF al path de perfiles chicos que hoy funcionan bien.

---

## 2. Arquitectura de autenticación por API key

**Decisión**: dependency de FastAPI, no middleware. `verify_api_key` vive en `backend/app/api/deps.py` y se engancha a nivel router:

```python
app.include_router(health.router)                      # exento
app.include_router(ping.router,  prefix="/v1",
                   dependencies=[Depends(verify_api_key)])
app.include_router(match.router, prefix="/v1",
                   dependencies=[Depends(verify_api_key)])
```

La dependency: si `settings.backend_api_key` es `None` → pass-through (modo abierto, scenario "Modo abierto"); si está definida, exige `Authorization: Bearer <key>` con `secrets.compare_digest`; si falta o no coincide → `401` sin tocar session ni proveedores externos (cumple el scenario "401 sin invocar proveedores externos" porque las dependencies corren antes del handler).

Exentos: `/health` y `/` (se agrega una root route mínima con nombre/metadata de la app). `/ping` queda protegido.

Docs: cuando `backend_api_key` está definida, la app se instancia con `docs_url=None, redoc_url=None, openapi_url=None` (condicional en `main.py`). En dev y CI (sin key) siguen disponibles.

Frontend: lee `PUBLIC_BACKEND_API_KEY` en build-time vía `import.meta.env` (env de Cloudflare Pages). El build de producción falla con error explícito si la var no está definida (guard en el cliente API). Ante un `401`, la UI muestra un banner accionable con instrucciones de credenciales — sin redirect (no hay login adonde redirigir).

Nota de naming: el spec `match-ui` fija `PUBLIC_BACKEND_API_KEY`; el enunciado del sprint mencionó `PUBLIC_API_KEY`. Gana el spec (más explícito, ya tiene scenarios): se adopta `PUBLIC_BACKEND_API_KEY` en código, docs y env de Cloudflare Pages.

**Por qué dependency y no middleware**:

- Tipado y visible en OpenAPI (el 401 aparece documentado por ruta); un middleware con exenciones por string-matching de path es frágil e invisible.
- Granularidad por router (proteger `/v1`, exentar `/health`) sin lista de excepciones hardcodeada.
- Testeable con `dependency_overrides` de FastAPI; no arrastra los quirks de `BaseHTTPMiddleware` (ya hay dos middlewares en `main.py`; mezclar auth ahí sumaría un tercer concern al mismo archivo).

**Alternativas descartadas**:

- Middleware global: exenciones por path matching manual, OpenAPI ciego al 401, test más ruidoso.
- OAuth/JWT/sesiones: multi-usuario está explícitamente out of scope.
- Cloudflare Access: protege el frontend, no el backend ni el camino MCP; acopla auth a la infra del edge.

---

## 3. Arquitectura frontend (SvelteKit + adapter-static + i18n)

**Decisión**: SPA estática. `svelte.config.js` con `adapter-static({ fallback: 'index.html' })`, `ssr = false` (Cloudflare Pages sirve el fallback y el router de SvelteKit resuelve rutas del lado cliente — cubre el scenario "SPA routing sin servidor" para `/history/123`).

Rutas:

```
src/routes/
├── +layout.svelte        ← nav mínima, LanguageToggle, banner de error global
├── +page.svelte          ← "/"  : JdForm → resultado (ScoreCard + detalles)
├── history/
│   ├── +page.svelte      ← listado (HistoryList)
│   └── [id]/+page.svelte ← detalle (reusa ScoreCard, ReasoningBox, etc.)
```

Estado (Svelte stores, `src/lib/stores/`):

- `analysisStore`: resultado actual + `status` (`idle | loading | error | done`).
- `historyStore`: listado + paginación + `status`.
- El idioma lo maneja el store interno de `svelte-i18n`.

i18n (`src/lib/i18n/locales/{es,en}.json`): `init()` con orden localStorage → `navigator.language` (prefijo `en` → inglés) → fallback `es`. El `LanguageToggle` persiste en `localStorage`. CI valida paridad de claves entre `es.json` y `en.json` y falla si un componente usa una clave inexistente.

Cliente API (`src/lib/api/client.ts`): `fetch` con `Authorization: Bearer ${PUBLIC_BACKEND_API_KEY}`, timeout de 60 s (cold start Render 30–50 s), tipos `MatchAnalysis`/`AnalysisSummary` espejo de los schemas de Pydantic. CORS: agregar el dominio de Cloudflare Pages a `CORS_ORIGINS` en Render.

Estados de UI, todos localizados:

- Loading: skeleton + mensaje "el análisis puede tardar ~50 s si el servidor está frío".
- Error: banner con causa (401 credenciales / 5xx-red con botón Reintentar / validación).
- Vacío: historial sin análisis → "Aún no hay análisis" / "No analyses yet".

Componentes (`src/lib/components/`): `JdForm`, `ScoreCard`, `StrengthsGapsList`, `EnergyBadge`, `ReasoningBox`, `HistoryList`, `LanguageToggle`. Colores de `ScoreCard` por score: rojo < 50, amarillo 50–74, verde ≥ 75 (constante compartida, no inline).

**Por qué esta forma**: adapter-static es lo único que Cloudflare Pages necesita (cero servidor); `svelte-i18n` es la opción más simple y documentada para SPA estática (decisión cerrada); stores nativos alcanzan sobrado para dos vistas y evitan introducir state libraries.

**Alternativas descartadas**:

- SSR/prerender por ruta: exige runtime en el edge para datos dinámicos; contradice adapter-static.
- `paraglide` para i18n: decisión cerrada a favor de `svelte-i18n`.
- TanStack Query / estado global tipo Redux: dos stores writable cubren el dominio; dependencias extra sin beneficio a esta escala.

---

## 4. Migración de vectores (#14)

**Decisión**: Alembic `backend/alembic/versions/002_add_vector_columns.py`, 100% aditiva, validada primero en Neon branch:

```sql
ALTER TABLE job_descriptions ADD COLUMN embedding vector(1024);
ALTER TABLE job_descriptions ADD COLUMN embedding_model varchar(100);
ALTER TABLE analyses           ADD COLUMN embedding vector(1024);
ALTER TABLE analyses           ADD COLUMN embedding_model varchar(100);
ALTER TABLE profiles           ADD COLUMN embedding vector(1024);
ALTER TABLE profiles           ADD COLUMN embedding_model varchar(100);
ALTER TABLE analyses           ADD COLUMN profile_id INTEGER REFERENCES profiles(id);

CREATE INDEX idx_jd_embedding_hnsw   ON job_descriptions USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_analyses_embedding_hnsw ON analyses USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_profiles_embedding_hnsw ON profiles USING hnsw (embedding vector_cosine_ops);
```

`down()`: drop de índices y columnas en orden inverso (sin pérdida de datos).

El embedding del perfil vive como **columna de `profiles`** — sin tabla polimórfica de embeddings (decisión cerrada; para single-user es over-engineering). Nota: los índices HNSW sobre `profiles`/`job_descriptions` sirven al scenario "top-K por similitud coseno" del spec (selección de perfil más relevante y dedupe futuro de JDs); el ranking intra-perfil por fragmentos es en-proceso (sección 1) y no necesita índice a esta escala.

`embedding_model varchar` junto a cada vector es el mecanismo de re-embedding: si `embedding_model != settings.hf_embedding_model` o el vector es `NULL` (dato legacy/fallo de ingesta), se regenera **on-demand** durante el flujo match y se persiste con el modelo nuevo, logueando warning. El embedding del JD histórico nunca se regenera (es snapshot del momento del análisis).

`analyses.profile_id` es necesario: el spec exige filtrar historial por perfil y el modelo actual (`app/db/models.py`) no tiene esa FK (solo `profile_snapshot` JSON). NULLable — filas previas quedan sin perfil.

Cambios asociados: agregar `pgvector` a `pyproject.toml` (el stub de mypy ya está declarado) y tipar las columnas en `models.py` con `Vector(1024)` de `pgvector.sqlalchemy`.

**Por qué**: migración aditiva = rollback trivial (`alembic downgrade`) y cero riesgo sobre datos existentes; HNSW con `vector_cosine_ops` es el índice por defecto de pgvector para coseno (mejor recall/latencia que ivfflat en volúmenes chicos, sin tuning de listas); columna vs tabla aparte evita un join innecesario en el caso de un solo perfil.

**Alternativas descartadas**:

- Tabla `embeddings` polimórfica (entity_type/entity_id): over-engineering cerrado por decisión de sprint.
- Índice `ivfflat`: requiere entrenar listas y degrada con pocos rows; HNSW es plug-and-play a esta escala.
- No persistir el embedding del análisis: rompe reproducibilidad (¿qué vector produjo este score?) y el spec lo exige.
- Dejar `analyses` sin `profile_id`: el filtro de historial por perfil del spec sería imposible sin parsear el snapshot JSON.

---

## 5. Persistencia del flujo match (#17)

**Decisión**: el flujo completo de `POST /v1/match` con transacción única al final:

```
POST /v1/match
  │
  ├─1─ verify_api_key (Depends) ────────────────────→ 401
  ├─2─ validar input (jd_text ≥ 50, profile_id int) → 422
  ├─3─ embedding del JD (BGE-M3 vía HF) ────────────→ 502 sin persistir
  ├─4─ lookup perfil ───────────────────────────────→ 404
  │      └─ on-demand: si embedding del perfil es NULL o cambió
  │         el modelo → regenerar y persistir (warning)
  ├─5─ contexto: perfil completo (≤ umbral)
  │      o retrieval top-K de fragmentos (> umbral)
  │      └─ error pgvector / embedding ausente → perfil completo (fallback)
  ├─6─ prompt + LLM Groq (backoff exponencial + jitter en 429)
  │      └─ 429 agotado → 429 | error no-429 → 502, sin persistir
  ├─7─ parse + validación del esquema de respuesta
  └─8─ TRANSACCIÓN ÚNICA
         BEGIN
           INSERT job_descriptions (raw_text, embedding, embedding_model, ...)
           INSERT analyses (job_description_id FK, profile_id FK,
                            profile_snapshot, score, strengths, gaps,
                            energy_level, reasoning, embedding, embedding_model)
         COMMIT  ── error DB → ROLLBACK → 503 (log con request id)
```

Puntos clave:

- Todo I/O externo (HF embeddings, LLM) ocurre **antes** de abrir la transacción: la conexión al pool no se sostiene durante llamadas lentas.
- Si el LLM falla (paso 6/7) no se persiste nada: el JD sin análisis es ruido en single-user (decisión cerrada).
- El análisis persiste el embedding del JD y `profile_id` — habilita historial filtrable y dedupe futuro.

Historial: `GET /v1/analyses?limit=20&offset=0&profile_id=` — orden `created_at DESC`, `[]` si vacío, defaults `limit=20` (max 100) y `offset=0`. Paginación por offset: suficiente y correcta para single-user (no hay escrituras concurrentes que desestabilicen ventanas).

Discrepancia de naming a resolver: el enunciado del sprint mencionó `GET /v1/match/history`, pero `proposal.md` y el spec `match-analysis` ya fijan `GET /v1/analyses` (con scenarios). **Gana el spec**: una sola ruta canónica orientada al recurso; adoptar la otra significaría editar spec + proposal + tests por gusto de naming.

Gap detectado: el detalle `/history/[id]` del frontend necesita un `GET /v1/analyses/{id}` (análisis completo + título del JD) que ningún spec cubre. Es aditivo y barato (~15 líneas, mismo PR-A); requiere un pequeño delta en el spec `match-analysis` durante sdd-tasks.

**Por qué**: la transacción única garantiza el invariant "todo análisis referenciable tiene su JD" con un solo mecanismo (FK NOT NULL + atomicidad), sin estados intermedios que limpiar; el backoff con jitter para 429 ya es patrón existente del provider de Groq.

**Alternativas descartadas**:

- Persistir el JD antes del LLM (para "no perder el input"): genera JDs huérfanos sin análisis y requiere GC; no aporta en single-user.
- Outbox / estados `pending`: máquina de estados para un flujo de un solo usuario sin reintentos del lado server — complejidad sin caso de uso.
- Paginación keyset (`created_at` cursor): correcta pero innecesaria sin concurrencia; offset es más simple y auditable.

---

## 6. Cadena de PRs y budget (1280 líneas vs 600 por PR)

**Decisión**: seis PRs encadenados, cada uno dentro del budget de 600 líneas. PR-D se divide explícitamente en D1+D2 y **queda dentro del sprint**, con fallback documentado.

| PR | Contenido | Issues | Líneas ~ | Depende de |
|---|---|---|---|---|
| **A** | Migración vectores + persistencia transaccional + `GET /v1/analyses` (+`/{id}`) + tests de migración/persistencia | #14 #17 | 350 | — |
| **B** | `verify_api_key` + wiring + docs condicional + tests auth | #15 (cierre auth) | 120 | — (independiente de A) |
| **C** | Servicio retrieval + umbral + fallbacks + tests retrieval con vectores fixture | #16 | 200 | A |
| **E** | MCP a producción: `backend_url` Render, timeout 60 s, `backend_api_key`, formatos | #18 | 60 | B (deploy de A+B) |
| **D1** | Frontend core: scaffold, i18n, cliente API, `/`, JdForm, ScoreCard, EnergyBadge, ReasoningBox, StrengthsGapsList | #19 | 350 | C en producción |
| **D2** | Frontend historial: `/history`, `/history/[id]`, estados vacío/error, paridad de claves en CI | #19 | 200 | D1 |

Total ≈ 1280 líneas en 6 PRs; ningún PR supera 600.

**Decisión explícita sobre PR-D**: entra al sprint **dividido en D1 y D2**. Como monolito (550l) rozaría el budget y dejaría sin margen cualquier ajuste de review; dividido, cada parte es reviewable y el flujo match end-to-end ya entrega valor con D1. Fallback (si el sprint se atrasa): D2 se mueve a un mini-sprint propio — el historial es aditivo y no bloquea la métrica fundacional (15 min → 2 min por evaluación). Esto formaliza el "candidato a PR separado post-sprint" que ya insinuaba la propuesta.

Orden de merge: **A → B → C → E → D1 → D2**. A y B son independientes y pueden desarrollarse/mergearse en paralelo; C depende de las columnas de A; E requiere backend con auth deployado; D1/D2 requieren la API en producción (y CORS configurado).

**Por qué**: PRs chicos = reviews rápidos y rollback granular; separar retrieval (C) de persistencia (A) permite que el umbral se tunee sin tocar el camino transaccional; E es minúsculo y no justifica un sprint, pero tampoco contamina un PR de backend.

**Alternativas descartadas**:

- PR-D monolítico de 550l: dentro del budget numérico, pero sin margen de review y mezcla i18n + routing + dominio en un solo diff.
- Frontend post-sprint (fallback de la propuesta como plan A): posterga la demo end-to-end y el success criteria "frontend contra producción" sin necesidad — D1 solo ya la cubre.
- Un PR único de backend (A+B+C ~670l): excede budget y hace que un bug de auth bloquee el merge de la migración.

---

## 7. Orden de implementación y paralelismo

```
Semana 1
  ├─ LANE 1 (backend):   PR-A migración + persistencia
  │      (validar migración en Neon branch antes de abrir el PR)
  ├─ LANE 2 (backend):   PR-B auth            ← paralelo con LANE 1
  └─ LANE 3 (frontend):  scaffold SvelteKit + adapter-static + i18n
                         + cliente API contra mocks  ← paralelo, cero deps

Semana 2
  ├─ PR-C retrieval (tras merge de A) + tests con vectores fixture
  ├─ Deploy Render (A+B+C) → PR-E MCP → smoke test con JD real
  ├─ PR-D1: integración frontend contra producción (CORS + key)
  └─ PR-D2: historial + estados + paridad de claves en CI

Continuo (#20, en cada PR):
  - A: tests de migración up/down (ya existe test_migrations.py), persistencia transaccional
  - B: 401/200 modos protegido y abierto, exenciones
  - C: retrieval unit (fixtures de vectores), snapshot de prompts, fallbacks
  - E: smoke del adapter contra Render
  - D1/D2: anti-alucinación con JDs reales (vía e2e manual contra prod), validación i18n
```

Reglas de dependencia: nada de frontend consume API real hasta que C esté deployado (evita reelaborar mocks dos veces); los snapshot de prompts se congelan en C y cualquier cambio posterior de prompt exige actualización explícita del snapshot; cada PR trae sus tests para mantener CI verde (49 tests actuales como piso).

---

## Riesgos técnicos

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Latencia HF al calcular embeddings de fragmentos on-demand (path retrieval) | Media | Suma segundos al endpoint en perfiles grandes | Caché en memoria por `(profile_id, updated_at, model)`; K fijo; si persiste, mover a pre-cálculo al editar perfil |
| Interpretación del retrieval por fragmentos (en-proceso) vs scenarios pgvector del spec | Baja | Divergencia en verificación (sdd-verify) | El spec queda cubierto: HNSW + top-K entre perfiles vía SQL; fallbacks de pgvector implementados en el servicio. Dejar asentado en tasks |
| `GET /v1/analyses/{id}` y el naming del historial requieren micro-delta de spec | Alta (detección ya hecha) | Fricción menor en verify | Agregar el ADDED requirement durante sdd-tasks; confirmar naming con el owner |
| PR-D se atrasa y arrastra el cierre del sprint | Media | Sprint sin demo end-to-end | División D1/D2 ya decidida; fallback: D2 a mini-sprint |
| Cold start Render (30–50 s) degrada la UX del frontend | Media | Percepción de "no funciona" | Timeout 60 s en cliente API + mensaje explícito en loading |
| OTPM de Groq (1000) con JDs largos | Media | 429 esporádicos | Backoff con jitter ya existente; scenario 429 del spec cubierto |
| Rate limit de HF con profiles grandes + edits repetidos | Baja | Fallbacks a perfil completo (spec lo tolera) | Backoff existente; caché; warning logueado |
| Migración sobre Neon pooler (conexiones) | Baja | Migración falla por timeout | Ejecutar en Neon branch primero; migración aditiva y rápida |

## Preguntas abiertas

- [ ] Confirmar naming del historial: `GET /v1/analyses` (spec, recomendado) vs `GET /v1/match/history` (mencionado en el enunciado). Una línea de código, pero fija contrato con MCP y frontend.
- [ ] Confirmar `PUBLIC_BACKEND_API_KEY` (spec) como nombre definitivo de la env del frontend.
