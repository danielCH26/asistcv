# Delta para match-analysis

## ADDED Requirements

### Requirement: Análisis match estructurado

`POST /v1/match` acepta `jd_text` y `profile_id`, devuelve `MatchAnalysis` con `score` (0–100), `strengths`, `gaps`, `energy_level` (`low|medium|high`) y `reasoning`.

#### Scenario: Happy path

- GIVEN un perfil persistido y un `jd_text` ≥ 50 caracteres
- AND `Authorization: Bearer` válido
- WHEN el cliente envía `POST /v1/match`
- THEN el sistema responde 200 con `score` en `[0,100]`
- AND `strengths`, `gaps`, `energy_level` y `reasoning` poblados
- AND el JD persiste en `job_descriptions` con su embedding
- AND el análisis persiste en `analyses` con FK al JD

#### Scenario: Validación — JD ausente o corto

- GIVEN `jd_text` vacío, ausente o < 50 caracteres
- WHEN el cliente envía `POST /v1/match`
- THEN el sistema responde 422 con detalle de validación

#### Scenario: Validación — perfil inexistente

- GIVEN `profile_id` que no existe en `profiles`
- WHEN el cliente envía `POST /v1/match`
- THEN el sistema responde 404 con mensaje identificable

#### Scenario: Error del LLM (5xx)

- GIVEN el proveedor LLM responde con error no-429
- WHEN se invoca `POST /v1/match`
- THEN el sistema responde 502 sin persistir análisis

#### Scenario: Rate limit del LLM (429)

- GIVEN el proveedor LLM responde 429
- WHEN se invoca `POST /v1/match`
- THEN el sistema aplica backoff exponencial con jitter (N reintentos)
- AND responde 429 al cliente si se agotan los reintentos

#### Scenario: Error de base de datos

- GIVEN Postgres no responde o falla la escritura
- WHEN se invoca `POST /v1/match`
- THEN el sistema responde 503 y registra el error con stack trace y request id

#### Scenario: Cross-lingual JD inglés ↔ perfil español

- GIVEN un perfil con texto en español y un `jd_text` en inglés
- WHEN se invoca `POST /v1/match`
- THEN el sistema responde 200 con `reasoning` en español
- AND `strengths`/`gaps` reflejan correctamente el cruce ES↔EN

### Requirement: Autenticación por API key

Si `BACKEND_API_KEY` está definida, todos los endpoints excepto `/health` deben exigir `Authorization: Bearer <key>`.

#### Scenario: API key inválida o ausente en modo protegido

- GIVEN `BACKEND_API_KEY` configurada
- WHEN el cliente envía `POST /v1/match` sin `Authorization`
- OR con un valor que no coincide
- THEN el sistema responde 401 sin invocar proveedores externos

#### Scenario: Modo abierto sin API key

- GIVEN `BACKEND_API_KEY` no definida
- WHEN cualquier cliente envía `POST /v1/match`
- THEN el sistema responde 200 sin exigir autenticación

### Requirement: Historial de análisis consultable

`GET /v1/analyses` lista análisis en orden cronológico inverso, con paginación opcional.

#### Scenario: Listado cronológico inverso

- GIVEN al menos un análisis persistido
- WHEN el cliente envía `GET /v1/analyses`
- THEN el sistema responde 200 con `id`, `profile_id`, `job_description_id`, `score`, `created_at`
- AND los resultados están ordenados por `created_at` descendente

#### Scenario: Historial vacío

- GIVEN la tabla `analyses` está vacía
- WHEN el cliente envía `GET /v1/analyses`
- THEN el sistema responde 200 con `[]`

#### Scenario: Filtrar historial por perfil

- GIVEN análisis con `profile_id=1` y `profile_id=2`
- WHEN el cliente envía `GET /v1/analyses?profile_id=1`
- THEN el sistema responde 200 sólo con análisis del perfil 1

#### Scenario: Detalle de un análisis

- GIVEN un análisis persistido con id conocido
- WHEN el cliente envía `GET /v1/analyses/{id}`
- THEN el sistema responde 200 con `score`, `strengths`, `gaps`, `energy_level`, `reasoning`, `created_at`
- AND `job_description` embebido con `title` (si existe), `company` (si existe) y snippet del `raw_text`

#### Scenario: Detalle de análisis inexistente

- GIVEN un `id` que no existe en `analyses`
- WHEN el cliente envía `GET /v1/analyses/{id}`
- THEN el sistema responde 404 con mensaje identificable

### Requirement: Persistencia de JD con embedding

Cada JD se persiste en `job_descriptions` con embedding (vector 1024, modelo `BAAI/bge-m3`) antes de invocar el LLM.

#### Scenario: JD nuevo con embedding

- GIVEN un JD recibido por primera vez
- WHEN se invoca `POST /v1/match`
- THEN existe un registro en `job_descriptions` con vector de 1024 floats
- AND el análisis en `analyses` referencia ese `job_description_id` por FK

#### Scenario: Falla del proveedor de embeddings

- GIVEN HuggingFace Inference falla al calcular embedding
- WHEN se invoca `POST /v1/match`
- THEN el sistema responde 502 sin persistir JD ni análisis
