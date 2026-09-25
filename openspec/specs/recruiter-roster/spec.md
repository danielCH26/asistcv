# Spec: recruiter-roster

## Purpose

Gestión de candidatos externos que un reclutador añade a su roster. Estos candidatos NO son usuarios de la plataforma; el reclutador gestiona sus CVs y análisis en nombre del candidato, previa aceptación de declaración de buena fe y Términos del Servicio.

## ADDED Requirements

### Requirement: Consentimiento del reclutador

La cuenta de un reclutador sólo puede operar el roster tras haber aceptado, durante el registro, una declaración de buena fe y los ToS que asignan responsabilidad legal al reclutador por el manejo de datos de terceros.

#### Scenario: Reclutador con consentimiento activo

- GIVEN un JWT con `role = "recruiter"` y `recruiter_consent.accepted_at IS NOT NULL`
- WHEN el cliente envía un endpoint del roster
- THEN el sistema responde según la lógica de negocio

#### Scenario: Reclutador sin consentimiento

- GIVEN un JWT con `role = "recruiter"` y `recruiter_consent IS NULL`
- WHEN el cliente intenta añadir un candidato o listar el roster
- THEN el sistema responde 403 con código `CONSENT_REQUIRED`
- AND sugiere completar el flujo de consentimiento

#### Scenario: Migración de cuentas previas

- GIVEN una cuenta `recruiter` creada antes de Sprint 2 sin `recruiter_consent`
- WHEN el usuario autenticado hace su primer request a un endpoint del roster
- THEN el sistema fuerza la pantalla de consentimiento antes de cualquier operación
- AND registra el evento `consent_recovered`

### Requirement: Alta de candidato externo

`POST /v1/recruiter/candidates` añade un candidato al roster del reclutador autenticado. Acepta: `full_name`, `email` (opcional), `phone` (opcional), `notes` (opcional) y archivo CV (PDF ≤ 10 MB).

#### Scenario: Alta exitosa

- GIVEN un reclutador autenticado con consentimiento activo
- AND un PDF válido
- WHEN envía `POST /v1/recruiter/candidates` (multipart)
- THEN el sistema responde 201 con `candidate_id`, `full_name`, `cv_id`, `added_at`
- AND persiste el CV en `recruiter_candidates_cvs` (no en `users_cvs`)

#### Scenario: Email duplicado en el roster

- GIVEN el reclutador ya tiene un candidato con el mismo `email`
- WHEN intenta crear otro con idéntico `email`
- THEN el sistema responde 409 con código `CANDIDATE_DUPLICATED`

#### Scenario: Email de candidato colisiona con un usuario registrado

- GIVEN existe `users.email = candidato@example.com`
- WHEN el reclutador añade un candidato con ese email
- THEN el sistema responde 201 y persiste el candidato en el roster
- AND el sistema NUNCA vincula el candidato externo al usuario registrado (separación estricta)

### Requirement: Listado del roster

`GET /v1/recruiter/candidates` devuelve los candidatos del reclutador autenticado, paginados.

#### Scenario: Listado paginado

- GIVEN un reclutador con 25 candidatos
- WHEN envía `GET /v1/recruiter/candidates?page=1&page_size=10`
- THEN el sistema responde 200 con 10 candidatos, `total = 25`, `has_more = true`

#### Scenario: Roster vacío

- GIVEN un reclutador sin candidatos
- WHEN envía `GET /v1/recruiter/candidates`
- THEN el sistema responde 200 con `[]`, `total = 0`

#### Scenario: Aislamiento entre reclutadores

- GIVEN dos reclutadores autenticados
- WHEN cada uno envía `GET /v1/recruiter/candidates`
- THEN el sistema devuelve sólo los candidatos del `recruiter_id` correspondiente (RLS)

### Requirement: Análisis de candidato contra JD

`POST /v1/recruiter/candidates/{id}/match` ejecuta el pipeline de match (`POST /v1/match`) pero usando el CV del candidato externo y el JD provisto por el reclutador. El resultado se persiste en `recruiter_analyses` con FK al candidato.

#### Scenario: Match exitoso

- GIVEN un candidato externo con CV persistido
- AND un JD de ≥ 50 caracteres
- WHEN el reclutador envía `POST /v1/recruiter/candidates/{id}/match` con `{"jd_text": "..."}`
- THEN el sistema responde 200 con el `MatchAnalysis`
- AND persiste el resultado en `recruiter_analyses` con FK al candidato y al reclutador

#### Scenario: Candidato ajeno

- GIVEN un JWT con `sub = recruiter_1`
- WHEN intenta `POST /v1/recruiter/candidates/{cand_de_recruiter_2}/match`
- THEN el sistema responde 404 (RLS)

### Requirement: Ranking híbrido del roster

`GET /v1/recruiter/candidates/ranked?jd_text=...` devuelve el roster del reclutador ordenado por `ranking_score = match_score × recency_decay`, con piso (`floor`) de 0.5 sobre `match_score` para evitar hundir candidatos válidos por baja recencia.

#### Scenario: Ranking por score y recencia

- GIVEN el reclutador tiene 3 candidatos con `match_score = 0.9, 0.7, 0.85` y `last_analysed_at` distintos
- WHEN envía `GET /v1/recruiter/candidates/ranked?jd_text=...`
- THEN el sistema aplica `recency_decay = exp(-Δdías / 30)`
- AND ordena descendente por `match_score × recency_decay`
- AND respeta el piso: `effective_score = max(match_score, 0.5)` sólo cuando se usa como filtro, pero el ranking usa el valor ponderado completo

#### Scenario: Roster sin análisis previos

- GIVEN el reclutador añadió candidatos pero no ejecutó match contra el JD actual
- WHEN envía `GET /v1/recruiter/candidates/ranked?jd_text=...`
- THEN el sistema calcula el match en línea para cada candidato (con presupuesto de N = 10 candidatos top)
- AND devuelve el ranking de esos N

#### Scenario: Roster demasiado grande

- GIVEN el reclutador tiene > 10 candidatos
- WHEN envía el ranking
- THEN el sistema procesa sólo los 10 con mayor coincidencia rápida al JD (top-K pre-filtrado por similitud de embedding)
- Y los restantes quedan fuera del ranking devuelto

### Requirement: Eliminación de candidato

`DELETE /v1/recruiter/candidates/{id}` elimina el candidato y todos sus análisis del roster.

#### Scenario: Eliminación exitosa

- GIVEN un candidato del reclutador autenticado
- WHEN envía `DELETE /v1/recruiter/candidates/{id}`
- THEN el sistema responde 204
- AND los `recruiter_analyses` referenciantes se eliminan en cascada

### Requirement: Auditoría de acciones del reclutador

Toda operación sobre el roster (alta, match, eliminación) debe registrarse en `recruiter_audit_log` con timestamp, acción, `recruiter_id`, `candidate_id` y hash de los datos sensibles (NUNCA el PDF crudo).

#### Scenario: Log de alta

- GIVEN un reclutador añade un candidato
- WHEN el alta se completa
- THEN existe una fila en `recruiter_audit_log` con `action = "candidate_added"`, `recruiter_id`, `candidate_id`, `sha256(pdf_bytes)`, `created_at`

#### Scenario: Log inalterable

- GIVEN un registro en `recruiter_audit_log`
- WHEN se intenta `UPDATE` o `DELETE` desde la API
- THEN el sistema rechaza la operación (tabla append-only vía trigger o RLS que niegue UPDATE/DELETE)
