# Spec: authentication

## Purpose

Emisión, validación y rotación de credenciales de acceso (JWT) y
coexistencia con la API key actual para preservar compatibilidad con
el `mcp-adapter`. Esta spec no cubre el ciclo de vida de la cuenta
(ver `user-accounts`) ni la matriz fina de permisos por endpoint
(ver el `requirements` de cada capability).

## ADDED Requirements

### Requirement: Emisión de par de tokens JWT

Tras login o registro exitoso, el sistema emite un `access_token`
JWT firmado con HS256 y TTL de 15 minutos, más un `refresh_token`
opaco (rotado, almacenado hasheado) con TTL de 30 días.

#### Scenario: Claims del access_token

- GIVEN un usuario autenticado con id `u` y rol `r`
- WHEN el sistema firma el `access_token`
- THEN el payload contiene `sub = u`, `role = r`, `iat`, `exp`
  (iat + 900 s) y `jti` único

#### Scenario: Refresh token opaco

- GIVEN un par de tokens recién emitido
- WHEN el sistema persiste el `refresh_token`
- THEN almacena únicamente su hash (sha256) en `refresh_tokens`
  con `user_id`, `expires_at = now() + 30d`, `revoked_at = NULL`

### Requirement: Refresh con rotación

`POST /v1/auth/refresh` intercambia un `refresh_token` vigente por un
nuevo par de tokens; el token presentado se considera consumido y no
puede reutilizarse.

#### Scenario: Rotación exitosa

- GIVEN un `refresh_token` vigente, no revocado y cuyo hash existe en
  `refresh_tokens`
- WHEN el cliente envía `POST /v1/auth/refresh`
- THEN el sistema marca el token como consumido
  (`consumed_at = now()`)
- AND emite un nuevo `access_token` y un nuevo `refresh_token`
- AND responde 200

#### Scenario: Reuso de refresh token (token theft)

- GIVEN un `refresh_token` ya consumido (`consumed_at != NULL`)
- WHEN el cliente envía `POST /v1/auth/refresh`
- THEN el sistema responde 401 con código `TOKEN_REUSED`
- AND revoca todos los `refresh_token` activos del usuario
  (cadena comprometida)
- AND registra el evento en `auth_security_events`

#### Scenario: Refresh revocado o expirado

- GIVEN un `refresh_token` con `revoked_at != NULL` o `expires_at < now()`
- WHEN el cliente envía `POST /v1/auth/refresh`
- THEN el sistema responde 401 con código `TOKEN_INVALID`

### Requirement: Autenticación dual (JWT usuario + API key servicio)

El backend acepta dos formas de credencial por request, en este orden
de precedencia:

1. `Authorization: Bearer <jwt>` válido → usuario autenticado
2. `Authorization: Bearer <api_key>` que coincida con `BACKEND_API_KEY`
   → servicio/MCP autenticado
3. Si ninguno aplica, el endpoint queda bloqueado (salvo rutas públicas)

La dual auth preserva la compatibilidad con el `mcp-adapter` sin
romper el contrato de Sprint 1.

#### Scenario: Request con JWT válido

- GIVEN un `Authorization: Bearer <jwt>` con firma válida, no expirado
  y no revocado
- WHEN el cliente envía cualquier endpoint protegido
- THEN el sistema inyecta `current_user` con `id`, `role`
- AND deja accesible `auth_method = "jwt"`

#### Scenario: Request con API key válida

- GIVEN `BACKEND_API_KEY` configurada
- AND el header coincide con el valor configurado
- WHEN el cliente envía cualquier endpoint protegido
- THEN el sistema inyecta `current_service` con `name = "mcp"`,
  `auth_method = "api_key"`
- AND no exige JWT

#### Scenario: Request sin credencial

- GIVEN `BACKEND_API_KEY` configurada
- WHEN el cliente envía un endpoint protegido sin `Authorization`
- OR con un valor que no coincide con la API key ni es un JWT válido
- THEN el sistema responde 401 sin invocar lógica de negocio

#### Scenario: Modo abierto (sin API key ni JWT requerido)

- GIVEN `BACKEND_API_KEY` no definida
- AND el endpoint no exige usuario autenticado
- WHEN el cliente envía la petición
- THEN el sistema responde 200 con `auth_method = "anonymous"`
  (caso de `free-audit`)

### Requirement: Endpoint `/health` siempre público

`GET /health` no exige ningún tipo de credencial ni consume rate
limit de usuario. Se mantiene la compatibilidad con health checks de
Render y herramientas de uptime.

#### Scenario: Health sin credenciales

- GIVEN el sistema operativo
- WHEN cualquier origen envía `GET /health`
- THEN el sistema responde 200 con `{"status": "ok"}` sin evaluar
  `Authorization`

### Requirement: RBAC por dependencia FastAPI

Los endpoints declaran su rol requerido vía dependencia
(`require_role("recruiter")`); el sistema rechaza con 403 cuando
el rol del JWT no coincide.

#### Scenario: Acceso permitido por rol

- GIVEN un JWT con `role = "recruiter"`
- WHEN el cliente envía un endpoint protegido por
  `require_role("recruiter")`
- THEN el sistema responde según la lógica de negocio

#### Scenario: Acceso denegado por rol

- GIVEN un JWT con `role = "job_seeker"`
- WHEN el cliente envía un endpoint protegido por
  `require_role("recruiter")`
- THEN el sistema responde 403 con código `ROLE_FORBIDDEN`

#### Scenario: Recruiter accede a endpoint de job_seeker

- GIVEN un JWT con `role = "recruiter"`
- WHEN el cliente envía un endpoint protegido por
  `require_role("job_seeker")`
- THEN el sistema responde 403 con código `ROLE_FORBIDDEN`
- AND la respuesta no filtra la existencia del endpoint

### Requirement: Aislamiento por sesión activa

Cada request autenticado vía JWT opera sobre el `user_id` del token;
ningún endpoint acepta `user_id` como parámetro para cambiar el
alcance. Los path/query params que incluyan `user_id` se ignoran o
se validan contra el `sub` del token.

#### Scenario: Intento de acceder a recursos de otro usuario

- GIVEN un JWT con `sub = u1`
- WHEN el cliente envía `GET /v1/users/{u2}` con `u2 != u1`
- THEN el sistema responde 404 (no 403, para no filtrar existencia)
- AND registra el intento en `auth_security_events`

### Requirement: Cabecera CORS para credenciales

Las respuestas a endpoints autenticados deben incluir
`Access-Control-Allow-Credentials: true` cuando el origen está en
la allow-list y la petición incluye cookies de refresh en el
flujo de la UI.

#### Scenario: Petición CORS con credenciales

- GIVEN un origen en `CORS_ALLOWED_ORIGINS`
- AND una petición con `credentials: "include"`
- WHEN el backend responde
- THEN la respuesta lleva
  `Access-Control-Allow-Credentials: true`
- AND `Access-Control-Allow-Origin` espejado (no `*`)
