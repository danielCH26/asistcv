# Spec: user-accounts

## Purpose

Gestión de identidad de usuario (registro, login, perfil básico) para los roles `job_seeker` y `recruiter`. Esta spec cubre el ciclo de vida de la cuenta; la emisión y validación de tokens vive en `authentication`.

## ADDED Requirements

### Requirement: Registro de cuenta por rol

`POST /v1/auth/register` crea una cuenta nueva con `email`, `password`, `role` ∈ {`job_seeker`, `recruiter`} y datos de perfil mínimos (`full_name`, `locale` por defecto `es`).

#### Scenario: Registro exitoso de job_seeker

- GIVEN un `email` no registrado y `password` ≥ 10 caracteres con mayúscula, minúscula y dígito
- WHEN el cliente envía `POST /v1/auth/register` con `{"email", "password", "role": "job_seeker", "full_name", "accept_tos": true}`
- THEN el sistema responde 201 con `user_id`, `role`, `email`, `full_name`
- AND la contraseña queda almacenada como hash bcrypt (cost ≥ 12)
- AND el cliente recibe `access_token` (15 min) y `refresh_token` (30 d)

#### Scenario: Registro exitoso de recruiter con consentimiento

- GIVEN un `email` no registrado y `password` válida
- AND `role: "recruiter"`
- AND `accept_tos: true` y `good_faith_declaration: true`
- WHEN el cliente envía `POST /v1/auth/register`
- THEN el sistema persiste `recruiter_consent` con `accepted_at`, `tos_version`, `ip` y `user_agent`
- AND responde 201 con tokens de sesión

#### Scenario: Rechazo por falta de consentimiento del reclutador

- GIVEN `role: "recruiter"`
- AND `accept_tos: false` o `good_faith_declaration: false`
- WHEN el cliente envía `POST /v1/auth/register`
- THEN el sistema responde 422 con código `CONSENT_REQUIRED`
- AND no crea la cuenta ni emite tokens

#### Scenario: Email duplicado

- GIVEN un `email` ya registrado en `users`
- WHEN el cliente envía `POST /v1/auth/register`
- THEN el sistema responde 409 con código `EMAIL_TAKEN`
- AND no revela si el email pertenece a un job_seeker o recruiter

#### Scenario: Password débil

- GIVEN un `password` con < 10 caracteres o que no cumpla la política de complejidad
- WHEN el cliente envía `POST /v1/auth/register`
- THEN el sistema responde 422 con detalle de validación

#### Scenario: Email malformado

- GIVEN un `email` que no cumple RFC 5322
- WHEN el cliente envía `POST /v1/auth/register`
- THEN el sistema responde 422 con detalle de validación

### Requirement: Login con email y contraseña

`POST /v1/auth/login` valida credenciales y emite par de tokens.

#### Scenario: Credenciales válidas

- GIVEN un `email` registrado y `password` correcto
- WHEN el cliente envía `POST /v1/auth/login`
- THEN el sistema responde 200 con `access_token` (15 min) y `refresh_token` (30 d)
- AND registra `last_login_at` en `users`

#### Scenario: Credenciales inválidas

- GIVEN un `email` registrado con `password` incorrecto
- OR un `email` no registrado
- WHEN el cliente envía `POST /v1/auth/login`
- THEN el sistema responde 401 con mensaje genérico (`invalid_credentials`) sin distinguir email existente de contraseña incorrecta
- AND el intento fallido se registra en `auth_login_attempts`

#### Scenario: Cuenta bloqueada por fuerza bruta

- GIVEN más de 5 intentos fallidos para el mismo `email` en una ventana de 15 minutos
- WHEN el cliente envía `POST /v1/auth/login`
- THEN el sistema responde 429 con `Retry-After` configurable
- AND el bloqueo se libera al expirar la ventana o tras login exitoso

### Requirement: Roles con restricción CHECK

La tabla `users` debe tener una columna `role` con `CHECK` que sólo permita los valores `job_seeker` y `recruiter`.

#### Scenario: Inserción con rol válido

- GIVEN una fila a insertar en `users`
- WHEN `role` ∈ {`job_seeker`, `recruiter`}
- THEN la inserción se completa sin error

#### Scenario: Inserción con rol inválido

- GIVEN una fila a insertar en `users`
- WHEN el rol toma cualquier otro valor
- THEN Postgres rechaza la inserción con `CheckViolation`

### Requirement: Logout e invalidación de sesión

`POST /v1/auth/logout` invalida el `refresh_token` activo y revoca el `access_token` hasta su expiración natural.

#### Scenario: Logout exitoso

- GIVEN un `refresh_token` válido asociado al usuario
- WHEN el cliente envía `POST /v1/auth/logout` con el token
- THEN el sistema marca el `refresh_token` como revocado en `refresh_tokens.revoked_at = now()`
- AND añade el `jti` del `access_token` a la deny list (`token_revocation`) con TTL igual al `exp`
- AND responde 204

#### Scenario: Logout idempotente

- GIVEN un `refresh_token` ya revocado
- WHEN el cliente reenvía `POST /v1/auth/logout`
- THEN el sistema responde 204 sin error

### Requirement: Datos básicos de perfil

`GET /v1/users/me` devuelve el perfil del usuario autenticado. `PATCH /v1/users/me` actualiza campos editables (`full_name`, `locale`, `avatar_url`).

#### Scenario: Lectura de perfil propio

- GIVEN un usuario autenticado con sesión JWT válida
- WHEN el cliente envía `GET /v1/users/me`
- THEN el sistema responde 200 con `id`, `email`, `role`, `full_name`, `locale`, `avatar_url`, `created_at`

#### Scenario: Actualización de locale

- GIVEN un usuario autenticado
- WHEN envía `PATCH /v1/users/me` con `{"locale": "en"}`
- THEN el sistema persiste el cambio y responde 200 con el perfil actualizado

#### Scenario: Intento de cambiar role

- GIVEN un usuario autenticado como `job_seeker`
- WHEN envía `PATCH /v1/users/me` con `{"role": "recruiter"}`
- THEN el sistema responde 422 con código `ROLE_IMMUTABLE`

### Requirement: Verificación de email

Tras el registro, el sistema envía un email de verificación con token de un solo uso; la cuenta queda en estado `pending_verification` hasta confirmar.

#### Scenario: Reenvío de verificación

- GIVEN un usuario con `email_verified_at IS NULL`
- WHEN el cliente envía `POST /v1/auth/verify-email/request`
- THEN el sistema genera un token de 24 h, lo persiste y lo envía por email
- AND responde 202

#### Scenario: Confirmación exitosa

- GIVEN un token de verificación vigente y no consumido
- WHEN el cliente envía `POST /v1/auth/verify-email/confirm` con el token
- THEN el sistema marca `email_verified_at = now()`, `email_verification_token` consumido
- AND responde 200

#### Scenario: Token expirado o consumido

- GIVEN un token vencido (> 24 h) o ya consumido
- WHEN el cliente envía `POST /v1/auth/verify-email/confirm`
- THEN el sistema responde 410 con código `TOKEN_EXPIRED`

### Requirement: Cambio de contraseña autenticado

`POST /v1/users/me/password` permite al usuario autenticado cambiar su contraseña conociendo la actual.

#### Scenario: Cambio exitoso

- GIVEN un usuario autenticado con `current_password` correcto
- WHEN envía `POST /v1/users/me/password` con `current_password` y `new_password` válidos
- THEN el sistema actualiza el hash bcrypt
- AND revoca todos los `refresh_token` activos del usuario
- AND responde 200

#### Scenario: Contraseña actual incorrecta

- GIVEN un `current_password` que no coincide con el hash
- WHEN el cliente envía el cambio
- THEN el sistema responde 401 con código `INVALID_PASSWORD`
