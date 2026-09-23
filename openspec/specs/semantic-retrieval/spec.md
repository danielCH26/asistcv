# Spec: semantic-retrieval

## ADDED Requirements

### Requirement: Embeddings del perfil persistidos

El sistema debe calcular y persistir embeddings (vector 1024, modelo `BAAI/bge-m3`) para cada `profile` al crearse o actualizarse.

#### Scenario: Perfil nuevo genera embedding

- GIVEN un perfil recién creado con `experience`, `skills` y `preferences`
- WHEN el perfil se persiste
- THEN existe un registro de embedding con vector de 1024 floats
- AND el modelo registrado coincide con la configuración activa

#### Scenario: Re-cálculo al actualizar perfil

- GIVEN un perfil existente con embedding previo
- WHEN se actualiza su contenido textual
- THEN el embedding se recalcula y reemplaza al anterior

### Requirement: Índice HNSW sobre embeddings

La columna vector de la tabla de embeddings debe contar con un índice HNSW usando `vector_cosine_ops`.

#### Scenario: Índice HNSW presente post-migración

- GIVEN la migración aditiva de Sprint 1 aplicada en Neon
- WHEN se inspecciona el esquema de la tabla de embeddings
- THEN existe un índice HNSW sobre la columna vector con `vector_cosine_ops`

#### Scenario: Búsqueda top-k por similitud coseno

- GIVEN embeddings de al menos 3 perfiles persistidos
- WHEN se consulta el top-K más similar a un vector de consulta
- THEN el sistema devuelve los K perfiles ordenados por distancia coseno ascendente

### Requirement: Retrieval con umbral por tamaño

El servicio de retrieval debe devolver el contexto del perfil según el tamaño del texto concatenado, configurable vía `RETRIEVAL_SIZE_THRESHOLD_CHARS` (default ~2000).

#### Scenario: Perfil chino usa contexto completo

- GIVEN el texto concatenado del perfil tiene largo total ≤ umbral configurado
- WHEN el servicio de retrieval es invocado
- THEN devuelve el perfil completo sin segmentación

#### Scenario: Perfil grande activa retrieval semántico

- GIVEN el texto concatenado del perfil supera el umbral
- WHEN el servicio de retrieval es invocado con el embedding de un JD
- THEN devuelve los K fragmentos más relevantes del perfil
- AND cada fragmento conserva su sección de origen

#### Scenario: Umbral configurable desde entorno

- GIVEN el operador define `RETRIEVAL_SIZE_THRESHOLD_CHARS=N`
- WHEN el servicio de retrieval arranca
- THEN el umbral efectivo es `N` (con default documentado si no se define)

### Requirement: Fallback a perfil completo

El retrieval debe tolerar ausencia de embeddings o errores de pgvector sin romper el flujo del endpoint `POST /v1/match`.

#### Scenario: Fallback por embedding ausente

- GIVEN un perfil sin embedding (dato legacy o fallo de ingesta)
- WHEN el servicio de retrieval es invocado
- THEN devuelve el perfil completo como contexto
- AND registra un warning indicando embedding ausente

#### Scenario: Fallback por error de pgvector

- GIVEN la consulta al índice pgvector retorna error
- WHEN el servicio de retrieval es invocado
- THEN devuelve el perfil completo como contexto
- AND registra el error con nivel `error` y stack trace
- AND el endpoint `POST /v1/match` responde 200 usando el contexto completo

### Requirement: Servicio retrieval expone interfaz única

El servicio debe exponer una función que reciba el embedding del JD y devuelva el contexto del perfil, sin filtrar detalles de pgvector al resto del sistema.

#### Scenario: Interfaz agnóstica del backend de vectores

- GIVEN cualquier caller (servicio match, tests)
- WHEN invoca la interfaz de retrieval
- THEN recibe siempre una estructura de contexto (no tipos específicos de pgvector)
- AND el resultado es serializable a JSON para logging estructurado
