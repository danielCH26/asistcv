# Stack — Decisiones Arquitectónicas

> Documento vivo. Registra las decisiones cerradas del stack y las que aún están abiertas. Las decisiones se justifican con su razón concreta, no con preferencias genéricas.

---

## TL;DR

| Capa | Tecnología | Destino |
|---|---|---|
| Frontend | SvelteKit (static export) | Firebase Hosting |
| Backend | FastAPI sobre Python 3.12 | Cloud Run (GCP) |
| Base de datos | Postgres + pgvector | Cloud SQL db-f1-micro |
| LLM | Claude 3.5 Haiku | Vertex AI |
| Embeddings | text-multilingual-embedding-002 | Vertex AI |
| Adapter MCP | Python con SDK `mcp` oficial | Local / ejecución por usuario |
| CI/CD | Cloud Build | Triggers desde GitHub |
| Secretos | Secret Manager | GCP |
| Specs / artifacts | OpenSpec + Engram | Híbrido (local + persistente) |

---

## Topología

El sistema se compone de un adapter MCP local que expone el producto como tools a clientes MCP (Claude Desktop, Cursor), un backend FastAPI desplegado en Cloud Run que concentra la lógica de negocio y las llamadas a Vertex AI, un frontend SvelteKit con export estático servido por Firebase Hosting para la UI web, y una base Postgres con pgvector en Cloud SQL para persistir perfil, JDs evaluados, adaptaciones y aplicaciones. El usuario opera desde el cliente MCP o desde el frontend; el backend nunca expone UI propia y el frontend nunca llama a Vertex AI directo, siempre pasa por el backend.

---

## Decisiones

### Frontend — SvelteKit con static export

**Qué.** SvelteKit configurado en modo static export, sin SSR ni endpoints server-side. Hosteado en Firebase Hosting.

**Por qué.** El producto es una herramienta personal con pocas pantallas (tres páginas en total según el roadmap) y bajo tráfico. Una SPA estática servida por CDN es más barata y más simple de operar que un servidor Node para renderizar HTML. SvelteKit sobre el stack porque su modelo de componentes y reactividad es directo, el bundle resultante es chico, y la experiencia de desarrollo es rápida. Firebase Hosting se integra trivialmente con el resto del stack GCP (mismo proyecto, mismas credenciales, mismo dominio) y ofrece SSL y CDN sin configuración adicional.

**Alternativas consideradas.**

- *Next.js sobre Cloud Run.* Más pesado para el caso de uso y requiere un servidor Node corriendo siempre que paga por request, aunque sea barato. El SSR no aporta nada porque la página depende de un backend ya separado.
- *Astro sobre Firebase Hosting.* Buena alternativa por bundle chico y modelo de islas. Se descarta porque el equipo y la velocidad de iteración están más probados con Svelte; la ganancia de Astro en sitios estáticos con poca interactividad no justifica migrar el conocimiento.

**Costo.** Hosting dentro del free tier de Firebase mientras el tráfico sea de un solo usuario. Sin costo recurrente esperado.

---

### Backend — FastAPI sobre Python 3.12

**Qué.** API REST en FastAPI, Python 3.12, deploy en Cloud Run con autoescalado a cero.

**Por qué.** El dominio (procesamiento de texto, llamadas a LLM, embeddings) es cómodo en Python por el ecosistema. FastAPI ofrece validación de requests con Pydantic, OpenAPI automático y tipado estricto, todo lo que se necesita para mantener contratos claros con el frontend y con el adapter MCP. Cloud Run escala a cero cuando no hay tráfico (el caso típico de uso personal), cobra solo por request servido, y se conecta directo a servicios GCP vecinos (Cloud SQL, Secret Manager, Vertex AI) con IAM.

**Alternativas consideradas.**

- *Node + Express sobre Cloud Run.* Viable y compartiría runtime con el frontend. Se descarta porque el LLM, los embeddings y pgvector tienen mejor soporte y SDKs más maduros en Python; mantener dos lenguajes en el mismo proyecto aumenta la superficie a aprender y mantener.
- *Cloud Functions por endpoint.* Suficiente para slices chicos pero se vuelve incómodo cuando hay estado compartido (cliente de DB, configuración de Vertex AI, cache). Un contenedor único con FastAPI es más simple de razonar.

**Costo.** Cloud Run escala a cero; en uso personal el costo es despreciable. Presupuesto anual estimado bajo los $5 incluso con uso intensivo del autor.

---

### Base de datos — Postgres + pgvector sobre Cloud SQL db-f1-micro

**Qué.** Cloud SQL con Postgres 15 y extensión pgvector habilitada, en instancia `db-f1-micro` (compartida, 0.6 GB de RAM).

**Por qué.** pgvector cubre el caso de uso de embeddings (match semántico entre JD y perfil) sin sumar un servicio aparte tipo Pinecone o Vertex AI Vector Search, que serían más caros y agregarían complejidad operativa. Postgres es el esquema conocido, soporta JSON para los análisis estructurados del LLM, y las migraciones se manejan con herramientas estándar (Alembic). La instancia `db-f1-micro` es la más barata de Cloud SQL; alcanza para un solo usuario con cientos de evaluaciones y miles de embeddings porque los tamaños son chicos.

**Alternativas consideradas.**

- *Vertex AI Vector Search (antes Matching Engine).* Mejor latencia y escala, pero overkill para un solo usuario y agrega un servicio más con su IAM y billing. Se descarta por relación costo / beneficio.
- *SQLite con sqlite-vss.* Más barato y cero operaciones, pero pierde la garantía de backups automáticos de Cloud SQL y complica el deploy en Cloud Run (disco efímero). Para un portfolio que demuestra criterio, Cloud SQL es la opción correcta.

**Costo.** `db-f1-micro` tiene parte del tiempo cubierto por free trial o créditos iniciales de GCP; después ronda los $7-10 / mes según región. Es el componente dominante del presupuesto.

---

### LLM — Vertex AI Claude 3.5 Haiku

**Qué.** Claude 3.5 Haiku invocado vía Vertex AI Model Garden.

**Por qué.** Haiku es el modelo de mejor relación costo / calidad para tareas estructuradas (extracción de skills, scoring, redacción breve) y soporta instrucciones largas con buena adherencia a restricciones (como "no inventar experiencia"). Vertex AI en lugar de Anthropic directo unifica facturación con el resto del stack GCP, evita manejar claves de API de un proveedor externo, y mantiene los datos dentro del proyecto GCP. La latencia es suficiente para uso interactivo y permite iterar prompts rápido.

**Alternativas consideradas.**

- *Gemini 1.5 Flash sobre Vertex AI.* Más barato y nativo en GCP. Se considera como upgrade posterior si la calidad de Haiku resulta insuficiente, pero Haiku gana en adherencia a instrucciones estructuradas, que es el caso dominante en este proyecto.
- *GPT-4o-mini vía API directa.* Calidad similar a Haiku para el caso, pero implica cuenta y billing separado de GCP y datos saliendo del proyecto. Se descarta por motivos operativos, no técnicos.

**Costo.** Haiku sobre Vertex AI ronda los $0.80 por millón de tokens de input. Estimado de costo por evaluación completa (prompt + respuesta) por debajo de $0.01. Presupuesto mensual bajo los $5 con uso personal intenso.

---

### Embeddings — Vertex AI text-multilingual-embedding-002

**Qué.** Modelo de embeddings multilingüe de Google sobre Vertex AI (`text-multilingual-embedding-002`, 768 dimensiones).

**Por qué.** El usuario primario y muchos de los JDs que va a evaluar están en español, mientras que empresas destino publican en inglés. Un modelo multilingüe cubre los dos sin necesidad de traducir pre-embarazadamente (que introduce ruido semántico) ni mantener dos pipelines. Es nativo de Vertex AI, comparte credenciales con el LLM, y las dimensiones (768) son cómodas para pgvector sin penalizar demasiado el storage ni la búsqueda.

**Alternativas consideradas.**

- *text-embedding-004 (solo inglés).* Más barato y de mayor benchmark en inglés puro. Se descarta porque el caso bilingüe ES / EN es central.
- *Embeddings open-source via Hugging Face (e5-multilingual, BGE-M3).* Sin costo de API, control total del modelo. Se descarta por costo operativo: hospedar el modelo en Cloud Run con GPU es más caro que Vertex AI para este volumen, y administrarlo suma responsabilidad sin upside para un solo usuario.

**Costo.** Vertex AI cobra por cada 1000 caracteres. Estimado por debajo de $1 / mes en uso personal.

---

### Adapter MCP — Python con SDK oficial `mcp`

**Qué.** Servidor MCP escrito en Python usando el SDK `mcp` oficial, que expone las tools del backend al cliente MCP local del usuario (Claude Desktop, Cursor u otros).

**Por qué.** El SDK oficial garantiza compatibilidad con la evolución del protocolo MCP y elimina la tentación de reimplementar el transporte. Python unifica el lenguaje con el backend y permite reutilizar los modelos Pydantic y los clientes HTTP. El adapter corre local como proceso del usuario: no expone endpoints públicos ni requiere autenticación adicional; el backend ya está protegido en Cloud Run.

**Alternativas consideradas.**

- *SDK TypeScript.* Viable si el ecosistema MCP del lado del cliente fuera predominantemente TS. Se descarta para no introducir un segundo lenguaje en el proyecto.
- *Implementación custom del protocolo MCP.* Conocimiento profundo del protocolo pero trabajo extra y riesgo de divergir cuando el estándar evolucione. No vale la pena para un proyecto de un solo autor.

**Costo.** Cero directo. Costo operativo: mantener el SDK actualizado y el adapter compatible con versiones nuevas del protocolo.

---

### CI/CD — Cloud Build con triggers desde GitHub

**Qué.** Cloud Build conectado al repo de GitHub, con pipelines para backend (test + imagen + deploy a Cloud Run) y frontend (build estático + deploy a Firebase Hosting). Triggers por branch.

**Por qué.** Cloud Build vive en el mismo proyecto GCP que el resto del stack, no requiere credenciales adicionales y se factura solo por minutos de build. Los pipelines son declarativos en archivos `cloudbuild.yaml`, viven en el repo y quedan bajo review como cualquier otro código. Es suficiente para un solo autor con un flujo de trunk-based o branches cortas.

**Alternativas consideradas.**

- *GitHub Actions.* Más familiar para el autor y ecosistema grande de actions. Se descarta porque introduce secrets de GCP adicionales fuera del proyecto, y Cloud Run se integra mejor con Cloud Build (workload identity nativo).
- *Cloud Deploy.* Más sofisticado para escenarios multi-environment con promoción progresiva. Se descarta porque un solo environment es suficiente en esta fase.

**Costo.** Cloud Build tiene free tier generoso (120 minutos diarios). Sin costo esperado en este proyecto.

---

### Secretos — Secret Manager

**Qué.** Secret Manager de GCP para credenciales de BD, claves de servicio y cualquier API key.

**Por qué.** Es el servicio estándar de GCP, integrable con Cloud Run vía IAM (los secrets se montan como variables de entorno sin pasar por el repositorio) y con logging de accesos. Evita archivos `.env` versionados y reduce el riesgo de leaks accidentales.

**Alternativas consideradas.**

- *Variables de entorno en el código del Cloud Run.* Más simple para un solo autor pero pierde auditoría y rotación. Se descarta por buenas prácticas.
- *HashiCorp Vault.* Más potente pero requiere operar infraestructura adicional. Desproporcionado para este proyecto.

**Costo.** Secret Manager cobra por secreto activo y por operación de acceso. En este proyecto son unos pocos secretos y el costo es despreciable (centavos por mes).

---

### Specs y planning — OpenSpec + Engram (híbrido)

**Qué.** SDD se ejecuta con artifact store híbrido: OpenSpec para los artefactos commiteables y revisables en PRs (proposal, specs, design, tasks); Engram para el contexto persistente entre sesiones y entre compactaciones.

**Por qué.** OpenSpec deja un rastro auditable en Git que sirve como portfolio del proceso de diseño, no solo del resultado. Engram cubre la fricción de retomar el proyecto después de pausas (el caso del autor, que usa el sistema durante una búsqueda de empleo con interrupciones). El modo híbrido los une: OpenSpec como fuente de verdad del artefacto, Engram como memoria de proceso.

**Alternativas consideradas.**

- *Solo OpenSpec.* Sin memoria entre sesiones; cada reanudación implica releer specs. Pierde valor en un proyecto de un solo autor con uso intermitente.
- *Solo Engram.* Sin artefactos commiteables; pierde el valor de portfolio del proceso SDD.

**Costo.** Cero directo.

---

## Costos mensuales estimados

| Componente | Estimado | Notas |
|---|---|---|
| Cloud SQL `db-f1-micro` | $7-10 | Dominante del presupuesto. Posible free trial el primer mes. |
| Vertex AI Haiku | < $5 | Escala con uso. Instrumentado desde Slice 1. |
| Vertex AI embeddings | < $1 | Volumen chico por embedding. |
| Cloud Run (backend) | < $1 | Escala a cero. |
| Firebase Hosting | $0 | Dentro del free tier. |
| Cloud Build | $0 | Dentro del free tier. |
| Secret Manager | < $0.50 | Pocos secretos. |
| **Total estimado** | **$10-20 / mes** | Dominado por Cloud SQL. |

---

## Próximas decisiones a documentar

Estas decisiones están abiertas y se documentarán a medida que se cierren, en este mismo archivo bajo una sección de "Decisiones cerradas" con la fecha relativa del slice en que se tomaron.

- **Autenticación.** Hoy el backend corre detrás de Cloud Run con tráfico solo del autor. Cuando se exponga más allá del single-user primario, hace falta auth en el adapter MCP y en el frontend. Candidatos a evaluar: OAuth contra GCP (IAP), API keys simples con rotación, o Auth0 / Firebase Auth. Decisión esperada durante Slice 2 o 3 si el alcance se expande.
- **Schema DB detallado.** Tablas, columnas, índices (incluido el índice de pgvector), políticas de retención y migraciones. Se documenta cuando se cierre el diseño del Slice 1 antes de implementar.
- **Contratos API.** Forma final de los endpoints REST, schemas de request / response, versionado y manejo de errores. Se documenta al cerrar el diseño de Slice 1 y se actualiza con cada nuevo slice.
- **Estrategia de prompts.** Versionado de prompts (archivos en repo con numeración), estrategias de cacheo, fallback entre modelos, y rúbrica del score de match. Se documenta cuando se itere la primera versión durante Slice 1.

---

*Documento vivo. Las decisiones cerradas se mueven a su sección definitiva cuando se validan en producción; las abiertas quedan registradas en "Próximas decisiones" hasta entonces.*