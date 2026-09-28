# Spec: adaptation-experience

## Purpose

Experiencia de usuario para adaptar un CV a una JD en la ruta
`/profile`. Reutiliza los sub-componentes visuales de `MatchResult`
(`ScoreCard`, `StrengthsGapsList`, `ReasoningBox`) para no crecer las
páginas de 700+ líneas. La UX es asíncrona: el usuario envía un JD,
ve un spinner con el texto localizado "Adaptando CV…", y el frontend
hace polling del estado cada 2 segundos durante un máximo de 60
segundos. Slice A sólo cubre la ruta `/profile` (job_seeker); la
integración en `/recruiter` queda fuera de scope hasta que se
habilite Slice B/C.

## ADDED Requirements

### Requirement: Componente compartido `AdaptationResult`

`AdaptationResult.svelte` renderiza el resultado de una adaptación.
Reusa los sub-componentes existentes de `MatchResult`
(`ScoreCard`, `StrengthsGapsList`, `ReasoningBox`) para mantener una
lengua visual común con el flujo de match.

#### Scenario: Render de adaptación completada

- GIVEN una respuesta `GET /v1/adaptations/{id}` con
  `status = "completed"` y `adapted_cv` poblado
- WHEN el componente `AdaptationResult` recibe el payload
- THEN muestra `ScoreCard` con un score estimado de la adaptación
- AND muestra `StrengthsGapsList` con las `strengths` y `gaps`
  producidas por la adaptación (no las del match)
- AND muestra `ReasoningBox` con el `reasoning` (resumen del ajuste)
- AND muestra una sección "Cambios sugeridos" listando los bullets
  del CV adaptados

#### Scenario: Render de adaptación fallida

- GIVEN una respuesta con `status = "failed"` y `error_code` poblado
- WHEN el componente `AdaptationResult` recibe el payload
- THEN muestra un banner de error localizado según `error_code`:
  `INVALID_HONESTY` → "El modelo agregó contenido no presente en tu
  CV. Reintentá con otro JD o contactanos.",
  `LLM_UNAVAILABLE` → "El servicio de adaptación no está disponible.
  Reintentá en unos minutos.",
  `LLM_RATE_LIMITED` → "Recibimos muchas solicitudes. Esperá unos
  segundos y reintentá."
- AND ofrece un botón "Reintentar" que dispara un nuevo
  `POST /v1/adaptations`

#### Scenario: Render durante polling

- GIVEN una respuesta con `status = "pending"`
- WHEN el componente recibe el payload
- THEN muestra un placeholder neutro con el spinner (no muestra
  secciones vacías de `ScoreCard` o `StrengthsGapsList`)

### Requirement: Slot en `/profile` (no en `/recruiter`)

El componente `AdaptationResult` se integra en la ruta
`/profile` del frontend SvelteKit. NO se monta en `/recruiter` en
Slice A — la habilitación del flujo de adaptación para roster
queda diferida hasta que se active Slice B/C.

#### Scenario: Página /profile muestra el botón de adaptación

- GIVEN un usuario autenticado con un CV propio
- WHEN navega a `/profile`
- THEN la página muestra un formulario con un textarea para pegar el
  JD y un botón "Adaptar mi CV"
- AND bajo el formulario hay una zona reservada donde se monta
  `AdaptationResult` cuando el usuario envía el formulario

#### Scenario: Página /recruiter intacta

- GIVEN la ruta `/recruiter` actual
- WHEN el usuario navega a `/recruiter`
- THEN la página NO muestra el formulario de adaptación ni el
  componente `AdaptationResult`
- AND el bundle de `/recruiter` no incluye `AdaptationResult`
  (verificable por build artifact)

### Requirement: Flujo de envío con spinner localizado

El usuario pega un JD, presiona "Adaptar mi CV", y la UI muestra
inmediatamente el spinner con el texto "Adaptando CV…" (i18n: "Adapting your CV…" en EN).
El botón se deshabilita durante el envío para evitar dobles POSTs.

#### Scenario: Envío y feedback inmediato

- GIVEN un JD pegado de ≥ 50 caracteres en el formulario
- AND sesión autenticada (JWT)
- WHEN el usuario presiona "Adaptar mi CV"
- THEN la UI reemplaza el formulario por un spinner con
  "Adaptando CV…"
- AND el botón "Adaptar mi CV" se deshabilita
- AND la UI inicia polling contra `GET /v1/adaptations/{id}` cada 2 s
  (ver Requisito "Polling cada 2 s con timeout 60 s")

#### Scenario: Validación cliente de JD corto

- GIVEN un JD pegado con menos de 50 caracteres
- WHEN el usuario presiona "Adaptar mi CV"
- THEN la UI muestra mensaje de validación ("El JD es muy corto.
  Pegá al menos 50 caracteres.") y bloquea el envío
- AND NO se ejecuta la llamada HTTP

#### Scenario: Doble envío bloqueado

- GIVEN el spinner está activo (job en curso)
- WHEN el usuario hace doble-click sobre el botón "Adaptar mi CV"
- THEN sólo se ejecuta un `POST /v1/adaptations`
- AND los clicks subsecuentes son no-ops

### Requirement: Polling cada 2 s con timeout 60 s

La UI hace polling del estado de la adaptación cada 2 segundos
durante un máximo de 60 segundos (30 intentos). Pasado ese tiempo,
la UI abandona el polling y muestra un error accionable.

#### Scenario: Polling refleja `pending` → `completed`

- GIVEN un job recién creado
- WHEN la UI ejecuta el primer poll a `t = 0s`
- AND el segundo poll a `t = 2s` (aún `pending`)
- AND el LLM completa a `t = 7s`
- WHEN la UI ejecuta el poll a `t = 8s`
- THEN recibe `status = "completed"`
- AND desmonta el spinner
- AND monta `AdaptationResult` con el payload completo

#### Scenario: Polling refleja `pending` → `failed`

- GIVEN un job recién creado
- WHEN el LLM falla por `INVALID_HONESTY` y la fila queda
  `status = "failed"`
- AND la UI ejecuta el siguiente poll
- THEN recibe `status = "failed"` con `error_code` poblado
- AND desmonta el spinner
- AND monta `AdaptationResult` en modo error con botón "Reintentar"

#### Scenario: Timeout de polling (60 s)

- GIVEN un job que permanece `pending` durante más de 60 segundos
- WHEN la UI completa los 30 intentos de polling
- THEN la UI abandona el polling
- AND muestra un mensaje: "La adaptación está tomando más tiempo de
  lo esperado. Dejá esta página abierta o reintentá más tarde."
- AND ofrece un botón "Reintentar" y otro "Verificar estado"
  (que ejecuta un poll manual adicional)

#### Scenario: Error de red durante polling

- GIVEN un poll en curso
- WHEN la llamada HTTP falla por error de red o 5xx transitorio
- THEN la UI continúa con el siguiente poll programado (no aborta)
- AND sólo tras 3 errores consecutivos muestra mensaje de "Error de
  conexión" y permite reintentar manualmente

### Requirement: Manejo de errores de autenticación

La UI maneja 401 del backend limpiando la sesión y redirigiendo a
`/login`, igual que el flujo de match (consistencia con `match-ui`).

#### Scenario: 401 durante envío

- GIVEN el JWT expiró durante el envío
- WHEN `POST /v1/adaptations` responde 401
- THEN la UI limpia los tokens (access + refresh)
- AND redirige a `/login` con mensaje accionable sobre credenciales

#### Scenario: 402 PLAN_LIMIT_REACHED mostrado en upgrade card

- GIVEN el usuario agotó su cuota de adaptaciones del mes
- WHEN `POST /v1/adaptations` responde 402 con `upgrade_url`
- THEN la UI muestra una "upgrade card" con el límite alcanzado, el
  plan actual y un CTA al `upgrade_url`
- AND NO monta `AdaptationResult` (la adaptación no se creó)

#### Scenario: 404 CV_NOT_FOUND mostrado

- GIVEN el `cv_id` enviado fue eliminado entre el polling previo y
  este envío
- WHEN `POST /v1/adaptations` responde 404 con `CV_NOT_FOUND`
- THEN la UI muestra mensaje accionable ("Tu CV ya no existe. Volvé
  a `/profile` y subí uno nuevo.")

### Requirement: i18n bilingüe ES/EN

Todos los textos visibles del flujo de adaptación siguen el catálogo
existente (`es.json` / `en.json`) de la spec `match-ui`. No se
agregan strings hardcodeados.

#### Scenario: Catálogo sincronizado

- GIVEN los catálogos `es.json` y `en.json` ya contienen las claves
  del flujo de match
- WHEN se agrega el flujo de adaptación
- THEN las claves nuevas (`adapt.button.submit`,
  `adapt.status.pending`, `adapt.error.invalid_honesty`, etc.)
  aparecen en ambos catálogos
- AND la validación CI de cobertura i18n sigue verde

#### Scenario: Cambio de idioma se aplica a la pantalla

- GIVEN el usuario cambia el toggle de ES a EN
- WHEN está en `/profile` con un job en polling activo
- THEN el texto "Adaptando CV…" se reemplaza por "Adapting your CV…"
  sin reiniciar el polling