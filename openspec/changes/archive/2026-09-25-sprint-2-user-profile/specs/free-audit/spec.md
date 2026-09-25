# Spec: free-audit

## Purpose

Funnel de auditoría gratuita y anónima: un visitante sube un CV
(opcional y recomendado: una JD), recibe un análisis de calidad del
CV —o de match contra la JD si la provee— sin crear cuenta, y al
final se le ofrece opcionalmente capturar el email para enviar el
resultado. El gancho de conversión es la auditoría del CV en sí
(CV-only); el análisis dirigido por JD es un bonus. Limita el abuso
por IP (3/día) y retiene los datos crudos 30 días como máximo.

## ADDED Requirements

### Requirement: Auditoría anónima

`POST /v1/audit/anonymous` acepta un CV y un `jd_text` OPCIONAL por
multipart sin requerir autenticación. El CV se envía por exactamente
UNO de dos caminos: `cv_file` (PDF ≤ 10 MB, parseado en el servidor)
o `cv_text` (texto pegado, ≥ 50 chars). Sin `jd_text` (o vacío) corre
el modo CV-only (auditoría de calidad del CV); con `jd_text` (≥ 50
chars) corre el modo jd_directed (match CV vs JD). La respuesta indica
el modo con `mode: "cv_only" | "jd_directed"`. En cv_only incluye
`score`, `problematicas` (con `seccion`, `problema`, `severidad`),
`recomendaciones` y `fortalezas`; en jd_directed devuelve un
`MatchAnalysis` idéntico al endpoint autenticado. En ambos casos se
agrega `audit_token`, sin persistir el análisis en `analyses` ni el
CV en `users_cvs`.

#### Scenario: Auditoría CV-only con PDF (sin autenticación, sin JD)

- GIVEN un visitante anónimo (sin JWT, sin API key)
- AND un PDF ≤ 10 MB con texto extraíble
- WHEN envía `POST /v1/audit/anonymous` (multipart) con `cv_file`
  y SIN `jd_text`
- THEN el sistema responde 200 con `mode = "cv_only"`, `audit_token`,
  `score`, `problematicas` (cada una con `seccion`, `problema`,
  `severidad`), `recomendaciones` y `fortalezas`
- AND el CV queda en `audit_uploads` con `jd_text = NULL`,
  `audit_result_json.mode = "cv_only"` y
  `expires_at = now() + 30d`
- Y el análisis NO se persiste en `analyses`

#### Scenario: Auditoría CV-only con texto pegado

- GIVEN un visitante anónimo sin JD
- WHEN envía `POST /v1/audit/anonymous` (multipart) con `cv_text`
  (≥ 50 chars) y sin `jd_text`
- THEN el sistema responde 200 con `mode = "cv_only"` y el análisis
  de calidad del CV

#### Scenario: Auditoría exitosa dirigida por JD (jd_directed)

- GIVEN un visitante anónimo y un JD de ≥ 50 caracteres
- WHEN envía `POST /v1/audit/anonymous` (multipart) con un CV
  (por `cv_file` o `cv_text` ≥ 50 chars) y `jd_text`
- THEN el sistema responde 200 con `mode = "jd_directed"`,
  `audit_token`, `score`, `strengths`, `gaps`, `energy_level`,
  `reasoning`

#### Scenario: JD corto (solo cuando se provee)

- GIVEN un `jd_text` provisto con < 50 caracteres
- WHEN el visitante envía `POST /v1/audit/anonymous` con `jd_text`
- THEN el sistema responde 422 con código `JD_TOO_SHORT`
- AND la ausencia de `jd_text` NUNCA dispara `JD_TOO_SHORT`

#### Scenario: PDF escaneado (sin texto extraíble)

- GIVEN un PDF válido estructuralmente pero sin texto extraíble
  (escaneado / image-only)
- WHEN el visitante envía `POST /v1/audit/anonymous` con `cv_file`
- THEN el sistema responde 422 con código `PDF_NO_TEXT`

#### Scenario: PDF que supera el límite de tamaño

- GIVEN un archivo de 12 MB (> 10 MB)
- WHEN el visitante envía `POST /v1/audit/anonymous` con `cv_file`
- THEN el sistema responde 413 con código `FILE_TOO_LARGE`

#### Scenario: Archivo que no es PDF

- GIVEN un archivo `.txt` (content type `text/plain`)
- WHEN el visitante envía `POST /v1/audit/anonymous` con `cv_file`
- THEN el sistema responde 415 con código `UNSUPPORTED_MEDIA_TYPE`

#### Scenario: Fallo de parseo del PDF

- GIVEN un archivo con content type PDF cuyo contenido no puede
  ser parseado por pypdf ni pdfminer
- WHEN el visitante envía `POST /v1/audit/anonymous` con `cv_file`
- THEN el sistema responde 503 con código `PDF_PARSE_FAILED`

#### Scenario: Sin CV (ni archivo ni texto)

- GIVEN cualquier request (con o sin `jd_text`)
- WHEN el visitante envía `POST /v1/audit/anonymous` sin `cv_file`
  ni `cv_text`
- THEN el sistema responde 422 con código `CV_REQUIRED`

#### Scenario: Texto de CV demasiado corto

- GIVEN un `cv_text` < 50 caracteres
- WHEN el visitante envía `POST /v1/audit/anonymous` con `cv_text`
- THEN el sistema responde 422 con código `CV_TOO_SHORT`

### Requirement: Captura opcional de email

Tras un análisis exitoso, el sistema expone
`POST /v1/audit/{audit_id}/capture-email` para que el visitante
reciba el resultado por correo. La captura es opcional y nunca
bloquea el funnel.

#### Scenario: Email válido

- GIVEN un `audit_id` recién generado (≤ 1 h de antigüedad)
- WHEN el cliente envía `POST /v1/audit/{audit_id}/capture-email`
  con `{"email": "user@example.com"}`
- THEN el sistema responde 202
- Y envía un email con el resultado del análisis y un CTA de
  registro

#### Scenario: Email malformado

- GIVEN un email que no cumple RFC 5322
- WHEN el cliente envía la captura
- THEN el sistema responde 422 con código `EMAIL_INVALID`
- Y no envía nada

#### Scenario: Audit expirado

- GIVEN un `audit_id` con más de 1 h de antigüedad
- WHEN el cliente intenta capturar el email
- THEN el sistema responde 410 con código `AUDIT_EXPIRED`

### Requirement: Rate limit por IP (anti-abuso)

El endpoint `POST /v1/audit` está limitado a 3 invocaciones
exitosas por IP cada 24 h, identificado por `X-Forwarded-For`
(con la lista de proxies de confianza configurada).

#### Scenario: Dentro del límite

- GIVEN una IP con 2 auditorías en las últimas 24 h
- WHEN envía una nueva `POST /v1/audit`
- THEN el sistema responde 200 con el análisis

#### Scenario: Límite excedido

- GIVEN una IP con 3 auditorías en las últimas 24 h
- WHEN envía una nueva `POST /v1/audit`
- THEN el sistema responde 429 con `Retry-After` (segundos hasta
  el reset) y código `RATE_LIMITED`

#### Scenario: Contador sólo cuenta auditorías exitosas

- GIVEN una IP con 5 intentos fallidos (PDF inválido) y 1 exitoso
- WHEN envía una nueva `POST /v1/audit` válida
- THEN el sistema responde 200 (el contador sólo suma exitosas)

### Requirement: Retención de 30 días para uploads anónimos

Los PDFs y JDs subidos por `POST /v1/audit` se eliminan 30 días
después de su creación. Un job programado (cron interno) borra
los registros vencidos.

#### Scenario: Limpieza programada

- GIVEN un `audit_uploads` con `expires_at < now()`
- WHEN corre el job diario de limpieza
- THEN el sistema elimina la fila y su binario asociado

#### Scenario: Vinculación a cuenta posterior

- GIVEN un visitante hizo una auditoría hace 5 días y posteriormente
  creó una cuenta con el mismo email
- WHEN el usuario autenticado solicita ver su historial
- THEN la UI puede mostrar los últimos N análisis anónimos
  vinculados al email del usuario (migración opcional en
  `sdd-design`)
- Y el CV anónimo NO se transfiere automáticamente a
  `users_cvs`; el usuario decide si lo sube de nuevo

### Requirement: Cabeceras anti-scraping

Las respuestas de `POST /v1/audit` deben incluir
`Cache-Control: no-store` y un `X-Robots-Tag: noindex` para que
los motores de búsqueda no indexen el contenido generado.

#### Scenario: Cabeceras presentes

- GIVEN una respuesta exitosa de `POST /v1/audit`
- WHEN se inspeccionan los headers
- THEN están presentes `Cache-Control: no-store` y
  `X-Robots-Tag: noindex`

### Requirement: Telemetría del funnel

Cada paso del funnel (inicio, éxito, captura de email, conversión
a registro) se registra de forma agregada en
`audit_funnel_events` con timestamp, `ip_hash` (sha256 truncado),
`step` y `audit_id` (cuando aplique).

#### Scenario: Evento de éxito

- GIVEN una auditoría exitosa
- WHEN el sistema responde 200
- THEN existe una fila en `audit_funnel_events` con
  `step = "audit_success"`, `audit_id`, `ip_hash`

#### Scenario: Conversión a registro

- GIVEN un usuario que capturó email en una auditoría previa y
  luego se registró
- WHEN completa el registro
- THEN se registra un evento
  `step = "audit_to_signup"` con el `audit_id` original si está
  disponible (matching por email + ventana de 30 d)
