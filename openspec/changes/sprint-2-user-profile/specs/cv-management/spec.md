# Spec: cv-management

## Purpose

Gestión del CV por usuario autenticado: ingestión de PDF, extracción
estructurada con `pypdf`, persistencia y recuperación de la versión
editable. Aislamiento estricto por usuario vía PostgreSQL RLS.

## ADDED Requirements

### Requirement: Subida de CV en PDF

`POST /v1/cvs` acepta un archivo PDF (multipart, ≤ 10 MB), lo
procesa con `pypdf` en streaming y persiste el texto crudo más la
versión estructurada extraída.

#### Scenario: Subida exitosa

- GIVEN un usuario autenticado con sesión JWT válida
- AND un PDF ≤ 10 MB con texto extraíble
- WHEN el cliente envía `POST /v1/cvs` (multipart) con `file`
- THEN el sistema responde 201 con `cv_id`, `parsed_at`,
  `structured.sections`, `structured.skills`
- AND el PDF binario se almacena en `cvs.raw_blob` (objeto binario)
- AND el texto extraído se almacena en `cvs.raw_text`
- AND el JSON estructurado se almacena en `cvs.structured`

#### Scenario: PDF sin texto extraíble

- GIVEN un PDF compuesto únicamente por imágenes (escaneado)
- WHEN el cliente envía `POST /v1/cvs`
- THEN el sistema responde 422 con código `PDF_NO_TEXT`
- AND no persiste el archivo

#### Scenario: PDF excede 10 MB

- GIVEN un archivo con `Content-Length > 10 MB`
- WHEN el cliente envía `POST /v1/cvs`
- THEN el sistema responde 413 con código `FILE_TOO_LARGE`

#### Scenario: Tipo MIME incorrecto

- GIVEN un archivo cuyo `Content-Type` no es `application/pdf`
- WHEN el cliente envía `POST /v1/cvs`
- THEN el sistema responde 415 con código `UNSUPPORTED_MEDIA_TYPE`

#### Scenario: Fallo de pypdf por OOM

- GIVEN un PDF que provoca uso de memoria superior al límite
  configurado del worker
- WHEN `pypdf` lanza `MemoryError`
- THEN el sistema activa el fallback a `pdfminer.six`
- AND si el fallback también falla, responde 503 con código
  `PDF_PARSE_FAILED`
- AND registra el incidente con stack trace y `cv_id` tentativo

### Requirement: Estructura parseada del CV

El parser debe extraer como mínimo: `full_name`, `email`,
`phone`, `location`, `experience[]`, `education[]`, `skills[]`,
`languages[]`. Cada `experience` incluye `company`, `title`,
`start_date`, `end_date`, `description`.

#### Scenario: Extracción completa

- GIVEN un CV con secciones claras (encabezado, experiencia,
  educación, habilidades)
- WHEN el parser procesa el PDF
- THEN el JSON resultante contiene todas las claves mínimas
- AND los `experience[]` tienen fechas en formato ISO 8601

#### Scenario: Sección faltante

- GIVEN un CV sin sección explícita de `education`
- WHEN el parser procesa el PDF
- THEN `education` queda como `[]` y no se rechaza el documento

#### Scenario: Idioma del CV

- GIVEN un CV cuyo texto está en español
- WHEN el parser lo procesa
- THEN el sistema detecta `locale = "es"` y lo persiste en
  `cvs.detected_locale`

### Requirement: Editor estructurado del CV

`PATCH /v1/cvs/{id}` actualiza la versión estructurada. El sistema
recalcula el embedding (vector 1024, `BAAI/bge-m3`) tras la edición.

#### Scenario: Edición válida

- GIVEN un CV del usuario autenticado
- WHEN el cliente envía `PATCH /v1/cvs/{id}` con
  `{"structured": {...}}` válido
- THEN el sistema persiste los cambios, marca
  `cvs.last_edited_at = now()`
- AND recalcula el embedding (vector 1024)
- AND responde 200 con la versión actualizada

#### Scenario: Edición de CV ajeno

- GIVEN un JWT con `sub = u1` y un CV cuyo `owner_user_id = u2`
- WHEN `u1` envía `PATCH /v1/cvs/{cv_de_u2}`
- THEN el sistema responde 404 (RLS filtra la fila antes del
  servicio) y registra el intento

#### Scenario: Payload inválido

- GIVEN un payload que rompe el esquema del editor (sección
  requerida faltante o tipo incorrecto)
- WHEN el cliente envía `PATCH /v1/cvs/{id}`
- THEN el sistema responde 422 con detalle de validación

### Requirement: Listado y detalle del CV

`GET /v1/cvs` lista los CVs del usuario autenticado.
`GET /v1/cvs/{id}` devuelve el detalle.

#### Scenario: Listado propio

- GIVEN un usuario con 2 CVs propios
- WHEN envía `GET /v1/cvs`
- THEN el sistema responde 200 con `[{cv_id, original_filename,
  detected_locale, created_at, last_edited_at}, ...]`
- AND nunca incluye CVs de otros usuarios (RLS)

#### Scenario: Detalle del CV

- GIVEN un CV propio del usuario
- WHEN envía `GET /v1/cvs/{id}`
- THEN el sistema responde 200 con `cv_id`, `structured`,
  `detected_locale`, `created_at`, `last_edited_at`

#### Scenario: CV inexistente

- GIVEN un `id` que no pertenece al usuario (o no existe)
- WHEN envía `GET /v1/cvs/{id}`
- THEN el sistema responde 404 con código `CV_NOT_FOUND`

### Requirement: Eliminación del CV

`DELETE /v1/cvs/{id}` elimina el CV del usuario autenticado y todos
los análisis derivados quedan huérfanos pero conservados para
auditoría.

#### Scenario: Eliminación exitosa

- GIVEN un CV propio del usuario
- WHEN envía `DELETE /v1/cvs/{id}`
- THEN el sistema responde 204
- AND el registro se elimina de `cvs`
- AND los análisis previos quedan con `cv_id` apuntando al id
  eliminado (FK con `ON DELETE SET NULL`)

### Requirement: Aislamiento STRICT por PostgreSQL RLS

Las tablas `users_cvs`, `users_cv_embeddings` y derivadas deben
tener políticas RLS que limiten toda lectura/escritura al
`owner_user_id` cuando el contexto de la sesión es
`app.user_id`. Las pruebas de regresión deben ejercitar intentos
cross-user y cross-role.

#### Scenario: Cross-user bloqueado en SELECT

- GIVEN una sesión Postgres con `app.user_id = u1`
- WHEN se ejecuta `SELECT * FROM users_cvs`
- THEN el resultado sólo contiene filas con
  `owner_user_id = u1`

#### Scenario: Cross-role bloqueado (recruiter → job_seeker)

- GIVEN una sesión con `app.user_id = recruiter` y `app.role =
  'recruiter'`
- WHEN intenta `SELECT * FROM users_cvs`
- THEN el resultado es vacío (RLS impide ver CVs de job_seekers)

#### Scenario: Inserción cross-user bloqueada

- GIVEN una sesión con `app.user_id = u1`
- WHEN intenta `INSERT INTO users_cvs (owner_user_id = u2)`
- THEN Postgres rechaza la operación con `RowLevelSecurityViolation`

#### Scenario: Contexto sin `app.user_id`

- GIVEN una sesión Postgres sin la GUC `app.user_id` configurada
- WHEN cualquier operación toca tablas con RLS
- THEN el sistema responde 500 con código `AUTH_CONTEXT_MISSING`
  antes de tocar datos
