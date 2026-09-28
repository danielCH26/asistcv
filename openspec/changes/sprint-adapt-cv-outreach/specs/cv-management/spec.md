# Delta for cv-management

> Modificaciones sobre `openspec/specs/cv-management/spec.md`. Esta
> delta añade dos requirements que conectan la spec de CV (Sprint 2)
> con la nueva capacidad de adaptación (Slice A). NO modifica
> requirements existentes — sólo agrega. El CV fuente permanece
> intacto: la adaptación es una derivada.

## ADDED Requirements

### Requirement: `cv_id` como fuente de verdad para adaptación

El identificador `cv_id` (FK a `user_cvs.id`) es la fuente de verdad
que la spec `cv-adaptation` usa para vincular una adaptación a su
CV origen. Esta convención reemplaza cualquier referencia previa a
`profile_id` en el contexto de adaptación: la spec de match
(`match-analysis`) y la spec de adaptación (`cv-adaptation`) deben
referirse al mismo `cv_id` cuando describan el insumo del usuario.

#### Scenario: Adaptación referencia `cv_id` del usuario

- GIVEN un usuario autenticado con un CV propio (`cv_id = C1`)
- WHEN el sistema procesa una adaptación
- THEN la fila `cv_adaptations` se persiste con
  `parent_cv_id = C1` y `owner_user_id = sub del JWT`
- AND el endpoint `GET /v1/adaptations/{id}` devuelve ese mismo
  `parent_cv_id` en su payload

#### Scenario: Mismo `cv_id` en match y adaptación

- GIVEN un CV propio del usuario (`cv_id = C1`)
- WHEN el cliente envía `POST /v1/match` con `cv_id = C1`
- AND luego envía `POST /v1/adaptations` con `cv_id = C1`
- THEN ambos endpoints aceptan el mismo `cv_id` (no se exige
  `profile_id` separado)
- AND el historial de match (`GET /v1/analyses`) y el de adaptación
  (`GET /v1/cvs/{id}/adaptations`) referencian el mismo CV fuente

### Requirement: Adaptaciones no bloquean ni se borran en cascada con el CV

La eliminación de un CV fuente o de cualquier adaptación asociada NO
genera cascadas destructivas. La spec `cv-adaptation` exige esta
garantía: las adaptaciones son derivadas, no dueñas del CV, y el CV
fuente es independiente del resultado adaptado.

#### Scenario: Eliminar el CV no borra adaptaciones derivadas

- GIVEN un CV propio del usuario con 3 adaptaciones previas
  (`parent_cv_id = C1`)
- WHEN el cliente envía `DELETE /v1/cvs/{C1}`
- THEN el sistema responde 204 y elimina la fila de `user_cvs`
- AND las 3 filas de `cv_adaptations` quedan con `parent_cv_id = null`
  (FK con `ON DELETE SET NULL`) — conservadas para auditoría
- AND `GET /v1/adaptations/{id}` de cada huérfana sigue funcionando
  con `status` y `adapted_cv_json` originales

#### Scenario: Eliminar una adaptación no toca el CV fuente

- GIVEN un CV propio con `cv_id = C1` y una adaptación vinculada
  (`parent_cv_id = C1`)
- WHEN el sistema elimina (o purga por retención) la fila de
  `cv_adaptations`
- THEN el CV fuente (`C1`) permanece intacto en `user_cvs`
- AND no se emite ninguna acción sobre el CV (no hay cascade en
  dirección hija → padre)

#### Scenario: Adaptación consultable tras borrar CV

- GIVEN una adaptación completada con `parent_cv_id = C1`
- WHEN el CV `C1` es eliminado
- AND el cliente envía `GET /v1/adaptations/{id}` con JWT válido
- THEN el sistema responde 200 con el payload completo
  (`adapted_cv_json`, `status`, `completed_at`)
- AND el `parent_cv_id` en la respuesta aparece como `null` para
  reflejar el estado huérfano

#### Scenario: Listado de adaptaciones tras borrado

- GIVEN un CV `C1` con 2 adaptaciones previas
- WHEN el cliente envía `DELETE /v1/cvs/{C1}`
- AND luego envía `GET /v1/cvs/{C1}/adaptations` con JWT válido
- THEN el sistema responde 404 con código `CV_NOT_FOUND` (el CV ya
  no existe)
- Y el cliente puede seguir consultando adaptaciones individuales
  vía `GET /v1/adaptations/{id}` (huérfanas pero accesibles)

#### Scenario: Crear nueva adaptación con mismo CV tras cache miss

- GIVEN el CV `C1` se mantiene activo (no fue eliminado)
- WHEN el cliente envía `POST /v1/adaptations` con un nuevo JD
  (`jd_text_hash` distinto al cacheado)
- THEN el sistema crea una nueva fila `cv_adaptations` con
  `parent_cv_id = C1` (mismo CV fuente, distinta adaptación)
- AND el CV fuente no se duplica ni se versiona (sigue siendo una
  sola fila en `user_cvs`)