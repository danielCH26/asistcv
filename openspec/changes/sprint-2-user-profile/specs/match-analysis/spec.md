# Delta para match-analysis

## MODIFIED Requirements

### Requirement: Autenticación por API key

Si `BACKEND_API_KEY` está definida, todos los endpoints excepto
`/health` deben exigir `Authorization: Bearer <key>` para
clientes de servicio (MCP); los usuarios autenticados deben
enviar un JWT válido y la dependencia `get_current_user` aplica.
La validación dual se detalla en `authentication`.

(Previously: API key única exigida a todos los callers cuando
`BACKEND_API_KEY` estaba configurada.)

#### Scenario: API key inválida o ausente en modo protegido

- GIVEN `BACKEND_API_KEY` configurada
- WHEN el cliente envía `POST /v1/match` sin `Authorization`
- OR con un valor que no coincide con la API key ni es un JWT
  válido
- THEN el sistema responde 401 sin invocar proveedores externos

#### Scenario: Modo abierto sin API key

- GIVEN `BACKEND_API_KEY` no definida
- AND el endpoint no exige usuario autenticado (caso `free-audit`)
- WHEN cualquier cliente envía `POST /v1/match` con la misma firma
  sin Authorization
- THEN el sistema responde 200 sin exigir autenticación

#### Scenario: JWT de usuario en endpoint autenticado

- GIVEN un JWT con `sub = u1`, `role = "job_seeker"` y firma válida
- WHEN `u1` envía `POST /v1/match`
- THEN el sistema acepta el JWT como credencial válida
- AND el análisis resultante queda asociado a `u1` para efectos
  de historial y RLS

#### Scenario: MCP con API key sigue funcionando

- GIVEN `BACKEND_API_KEY` configurada
- AND el `mcp-adapter` envía `Authorization: Bearer <api_key>`
- WHEN invoca `POST /v1/match`
- THEN el sistema responde 200 con `auth_method = "api_key"`
- Y no se exige JWT (compatibilidad preservada)

### Requirement: Historial de análisis consultable

`GET /v1/analyses` lista los análisis del usuario autenticado por
JWT (o del servicio por API key) en orden cronológico inverso,
con paginación opcional. Las consultas ignoran o validan que el
`profile_id` o `user_id` del path/query coincida con el `sub` del
token para evitar lecturas cruzadas.

#### Scenario: Listado cronológico inverso

- GIVEN al menos un análisis del usuario autenticado
- WHEN el cliente envía `GET /v1/analyses`
- THEN el sistema responde 200 con `id`, `profile_id`,
  `job_description_id`, `score`, `created_at`
- AND los resultados están ordenados por `created_at` descendente
- AND sólo aparecen análisis cuyo `user_id = current_user.sub`

#### Scenario: Historial vacío

- GIVEN el usuario autenticado no tiene análisis
- WHEN el cliente envía `GET /v1/analyses`
- THEN el sistema responde 200 con `[]`

#### Scenario: Filtrar historial por perfil propio

- GIVEN análisis del usuario `u1` con `profile_id=1` y `profile_id=2`
- WHEN `u1` envía `GET /v1/analyses?profile_id=1`
- THEN el sistema responde 200 sólo con análisis del perfil 1
  de `u1`

#### Scenario: Usuario A no ve análisis de Usuario B

- GIVEN análisis de `u1` y `u2`
- WHEN `u1` envía `GET /v1/analyses`
- THEN la respuesta sólo contiene análisis de `u1`
- Y si `u1` intenta `GET /v1/analyses/{analisis_de_u2}` recibe 404

#### Scenario: Detalle de un análisis

- GIVEN un análisis del usuario autenticado con id conocido
- WHEN el cliente envía `GET /v1/analyses/{id}`
- THEN el sistema responde 200 con `score`, `strengths`, `gaps`,
  `energy_level`, `reasoning`, `created_at`, `cv_id`
- AND `job_description` embebido con `title` (si existe),
  `company` (si existe) y snippet del `raw_text`

#### Scenario: Detalle de análisis inexistente o ajeno

- GIVEN un `id` que no existe en `analyses`
- OR pertenece a otro usuario
- WHEN el cliente envía `GET /v1/analyses/{id}`
- THEN el sistema responde 404 con mensaje identificable

## ADDED Requirements

### Requirement: Análisis match estructurado

`POST /v1/match` acepta `jd_text` y `profile_id`, devuelve
`MatchAnalysis` con `score` (0–100), `strengths`, `gaps`,
`energy_level` (`low|medium|high`) y `reasoning`. Cuando el
caller es un usuario autenticado por JWT, el análisis se asocia
a su `user_id` y se persiste con FK al CV propio del usuario.

#### Scenario: Happy path (job_seeker autenticado)

- GIVEN un CV propio del usuario autenticado (`users_cvs`)
- AND un `jd_text` ≥ 50 caracteres
- WHEN el cliente envía `POST /v1/match` con JWT válido
- THEN el sistema responde 200 con `score` en `[0,100]`
- AND `strengths`, `gaps`, `energy_level` y `reasoning` poblados
- AND el JD persiste en `job_descriptions` con su embedding
- AND el análisis persiste en `analyses` con FK al JD y al
  `user_id` del JWT

#### Scenario: Validación — JD ausente o corto

- GIVEN `jd_text` vacío, ausente o < 50 caracteres
- WHEN el cliente envía `POST /v1/match`
- THEN el sistema responde 422 con detalle de validación

#### Scenario: Validación — CV inexistente o ajeno

- GIVEN un `profile_id` que no existe en `users_cvs` del usuario
  autenticado
- WHEN el cliente envía `POST /v1/match`
- THEN el sistema responde 404 con mensaje identificable
- (RLS filtra CVs ajenos antes del servicio)

#### Scenario: Error del LLM (5xx)

- GIVEN el proveedor LLM responde con error no-429
- WHEN se invoca `POST /v1/match`
- THEN el sistema responde 502 sin persistir análisis

#### Scenario: Rate limit del LLM (429)

- GIVEN el proveedor LLM responde 429
- WHEN se invoca `POST /v1/match`
- THEN el sistema aplica backoff exponencial con jitter (N
  reintentos)
- AND responde 429 al cliente si se agotan los reintentos

#### Scenario: Error de base de datos

- GIVEN Postgres no responde o falla la escritura
- WHEN se invoca `POST /v1/match`
- THEN el sistema responde 503 y registra el error con stack
  trace y request id

#### Scenario: Cross-lingual JD inglés ↔ perfil español

- GIVEN un perfil con texto en español y un `jd_text` en inglés
- WHEN se invoca `POST /v1/match`
- THEN el sistema responde 200 con `reasoning` en español
- AND `strengths`/`gaps` reflejan correctamente el cruce ES↔EN

#### Scenario: Límite de plan alcanzado

- GIVEN un usuario `recruiter` con plan Starter
  (`matches_per_month = 50`) y `usage.matches_this_month = 50`
- WHEN invoca `POST /v1/match`
- THEN el sistema responde 402 con código `PLAN_LIMIT_REACHED`

### Requirement: Persistencia de JD con embedding

Cada JD se persiste en `job_descriptions` con embedding (vector
1024, modelo `BAAI/bge-m3`) antes de invocar el LLM. El análisis
queda vinculado al `user_id` del JWT (o al `recruiter_id` para
matches de roster).

#### Scenario: JD nuevo con embedding

- GIVEN un JD recibido por primera vez por un usuario autenticado
- WHEN se invoca `POST /v1/match`
- THEN existe un registro en `job_descriptions` con vector de
  1024 floats
- AND el análisis en `analyses` referencia ese `job_description_id`
  por FK y el `user_id` del JWT

#### Scenario: Falla del proveedor de embeddings

- GIVEN HuggingFace Inference falla al calcular embedding
- WHEN se invoca `POST /v1/match`
- THEN el sistema responde 502 sin persistir JD ni análisis
