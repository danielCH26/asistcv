# Stack — Decisiones Arquitectónicas

> Documento vivo. Registra las decisiones cerradas del stack y las que aún están abiertas. Las decisiones se justifican con su razón concreta, no con preferencias genéricas.

> **Contexto de migración (septiembre 2026).** El stack fue originalmente diseñado sobre GCP completo: Cloud Run para el backend, Cloud SQL para Postgres, Vertex AI para LLM y embeddings, Cloud Build para CI/CD, Secret Manager para secretos. Ese stack requería tarjeta de crédito para habilitar billing en GCP, restricción que bloqueó el deploy de los servicios pagos (Cloud SQL, Cloud Run, Cloud Build, Vertex AI). El autor no cuenta con tarjeta, por lo que el stack se migró a alternativas 100% free tier, sin cambios en los frameworks (FastAPI, SvelteKit, pgvector, SDK `mcp`) y manteniendo las mismas decisiones de diseño. Este documento deja registro histórico del stack anterior en cada alternativa considerada.

---

## TL;DR

| Capa | Tecnología | Destino |
|---|---|---|
| Frontend | SvelteKit (static export) | Cloudflare Pages |
| Backend | FastAPI sobre Python 3.12 | HuggingFace Spaces (SDK Docker) |
| Base de datos | Postgres + pgvector | Neon (serverless) |
| LLM | Llama 3.3 70B Versatile | Groq |
| Embeddings | BGE-M3 | HuggingFace Inference API |
| Adapter MCP | Python con SDK `mcp` oficial | Local / ejecución por usuario |
| CI/CD | GitHub Actions | Pipelines por push y por PR |
| Secretos | GitHub Secrets + env vars en HF Spaces | — |
| Specs / artifacts | OpenSpec + Engram | Híbrido (local + persistente) |

---

## Topología

El sistema se compone de un adapter MCP local que expone el producto como tools a clientes MCP (Claude Desktop, Cursor), un backend FastAPI empaquetado como imagen Docker y desplegado en HuggingFace Spaces que concentra la lógica de negocio y las llamadas a Groq y a la Inference API de HuggingFace, un frontend SvelteKit con export estático servido por Cloudflare Pages para la UI web, y una base Postgres con pgvector en Neon para persistir perfil, JDs evaluados, adaptaciones y aplicaciones. El usuario opera desde el cliente MCP o desde el frontend; el backend nunca expone UI propia y el frontend nunca llama a Groq ni a HuggingFace directo, siempre pasa por el backend.

---

## Decisiones

### Frontend — SvelteKit con static export

**Qué.** SvelteKit configurado en modo static export, sin SSR ni endpoints server-side. Hosteado en Cloudflare Pages.

**Por qué.** El producto es una herramienta personal con pocas pantallas (tres páginas en total según el roadmap) y bajo tráfico. Una SPA estática servida por CDN es más barata y más simple de operar que un servidor Node para renderizar HTML. SvelteKit por su modelo de componentes directo, bundle chico y velocidad de iteración. Cloudflare Pages ofrece free tier real sin tarjeta de crédito, SSL y CDN global sin configuración, y se integra con deploys automáticos desde el repo de GitHub.

**Alternativas consideradas.**

- *Next.js sobre Cloudflare Pages o HuggingFace Spaces.* Más pesado para el caso de uso y requiere un servidor Node corriendo siempre que paga por request, aunque sea barato. El SSR no aporta nada porque la página depende de un backend ya separado.
- *SvelteKit sobre Firebase Hosting (stack anterior).* Se descarta porque Firebase Hosting requiere un proyecto GCP con billing habilitado, lo que reintroduce la restricción de tarjeta de crédito que motivó la migración.
- *Astro sobre Cloudflare Pages.* Buena alternativa por bundle chico y modelo de islas. Se descarta porque el conocimiento y la velocidad de iteración están más probados con Svelte; la ganancia de Astro en sitios estáticos con poca interactividad no justifica migrar el conocimiento.

**Costo.** $0 dentro del free tier de Cloudflare Pages, sin tarjeta de crédito requerida.

---

### Backend — FastAPI sobre Python 3.12

**Qué.** API REST en FastAPI, Python 3.12, empaquetada como imagen Docker y desplegada en HuggingFace Spaces con SDK Docker (recurso CPU).

**Por qué.** El dominio (procesamiento de texto, llamadas a LLM, embeddings) es cómodo en Python por el ecosistema. FastAPI ofrece validación de requests con Pydantic, OpenAPI automático y tipado estricto, todo lo necesario para mantener contratos claros con el frontend y con el adapter MCP. HuggingFace Spaces con SDK Docker permite correr cualquier contenedor en free tier real, sin tarjeta de crédito, y queda versionado por el repo de HuggingFace. El espacio CPU con sleep tras inactividad es suficiente para uso personal.

**Alternativas consideradas.**

- *FastAPI sobre Cloud Run (stack anterior).* Se descarta porque Cloud Run requiere billing habilitado en GCP, lo que implica tarjeta de crédito.
- *Node + Express sobre HuggingFace Spaces.* Viable y compartiría runtime con el frontend. Se descarta porque el LLM, los embeddings y pgvector tienen mejor soporte y SDKs más maduros en Python; mantener dos lenguajes en el mismo proyecto aumenta la superficie a aprender y mantener.
- *Cloud Functions por endpoint.* Suficiente para slices chicos pero se vuelve incómodo cuando hay estado compartido (cliente de DB, configuración de LLM, cache). Un contenedor único con FastAPI es más simple de razonar.

**Costo.** $0 dentro del free tier de HuggingFace Spaces para CPU Spaces, sin tarjeta de crédito requerida.

---

### Base de datos — Postgres + pgvector sobre Neon

**Qué.** Postgres serverless en Neon con extensión pgvector habilitada.

**Por qué.** pgvector cubre el caso de uso de embeddings (match semántico entre JD y perfil) sin sumar un servicio aparte tipo Pinecone o Vertex AI Vector Search, que serían más caros y agregarían complejidad operativa. Neon ofrece free tier real sin tarjeta de crédito, escala a cero cuando no hay conexiones, y se conecta vía driver estándar de Postgres (`psycopg` / `asyncpg`) sin protocolos especiales. Las migraciones se manejan con Alembic igual que con Cloud SQL.

**Alternativas consideradas.**

- *Cloud SQL `db-f1-micro` (stack anterior).* Se descarta porque Cloud SQL requiere billing habilitado en GCP, lo que implica tarjeta de crédito.
- *Vertex AI Vector Search (antes Matching Engine).* Mejor latencia y escala, pero overkill para un solo usuario y agrega un servicio más con su IAM y billing. Se descarta por relación costo / beneficio.
- *SQLite con sqlite-vss.* Más barato y cero operaciones, pero pierde la garantía de backups automáticos de un servicio gestionado, complica el deploy en HuggingFace Spaces (disco efímero) y limita concurrencia.

**Costo.** $0 dentro del free tier de Neon, sin tarjeta de crédito requerida.

---

### LLM — Llama 3.3 70B Versatile vía Groq

**Qué.** Llama 3.3 70B Versatile invocado vía API de Groq con SDK Python oficial `groq`.

**Por qué.** Llama 3.3 70B ofrece calidad comparable a modelos comerciales para tareas estructuradas (extracción de skills, scoring, redacción breve) y respeta instrucciones con buena adherencia a restricciones (como "no inventar experiencia"). Groq provee inferencia con latencia muy baja, free tier real sin tarjeta de crédito, y SDK Python oficial. Evita la dependencia de un proveedor único y mantiene los datos fuera de GCP. La latencia es suficiente para uso interactivo y permite iterar prompts rápido.

**Alternativas consideradas.**

- *Claude 3.5 Haiku vía Vertex AI (stack anterior).* Se descarta porque Vertex AI requiere billing habilitado en GCP, lo que implica tarjeta de crédito.
- *Gemini 1.5 Flash vía API directa.* Free tier limitado y requerimiento de tarjeta para habilitarlo. Se descarta por la misma razón que Vertex AI.
- *GPT-4o-mini vía OpenAI.* Calidad alta, pero free tier limitado y un proveedor externo adicional con sus propios términos. Se descarta por motivos operativos, no técnicos.

**Costo.** $0 dentro del free tier de Groq, sin tarjeta de crédito requerida. Límites por minuto suficientes para uso personal.

---

### Embeddings — BGE-M3 vía HuggingFace Inference API

**Qué.** Modelo BGE-M3 (multilingüe, 1024 dimensiones) invocado vía la Inference API de HuggingFace por HTTP estándar (httpx).

**Por qué.** El usuario primario y muchos de los JDs que va a evaluar están en español, mientras que empresas destino publican en inglés. BGE-M3 es multilingüe fuerte y cubre ambos idiomas sin traducir pre-embarazadamente, lo que evita ruido semántico. La Inference API de HuggingFace ofrece free tier real sin tarjeta de crédito y se accede por HTTP estándar, sin SDK propietario. Las 1024 dimensiones son cómodas para pgvector sin penalizar demasiado storage ni búsqueda.

**Alternativas consideradas.**

- *text-multilingual-embedding-002 vía Vertex AI (stack anterior).* Se descarta porque Vertex AI requiere billing habilitado en GCP, lo que implica tarjeta de crédito.
- *text-embedding-004 vía Vertex AI.* Más barato y de mayor benchmark en inglés puro. Se descarta porque el caso bilingüe ES / EN es central.
- *Hospedar BGE-M3 propio en HuggingFace Spaces con GPU.* Sin costo de API, pero los Spaces con GPU tienen free tier limitado y algunos tiers piden tarjeta. Se descarta por simplicidad operativa.

**Costo.** $0 dentro del free tier de HuggingFace Inference API, sin tarjeta de crédito requerida.

---

### Adapter MCP — Python con SDK oficial `mcp`

**Qué.** Servidor MCP escrito en Python usando el SDK `mcp` oficial, que expone las tools del backend al cliente MCP local del usuario (Claude Desktop, Cursor u otros).

**Por qué.** El SDK oficial garantiza compatibilidad con la evolución del protocolo MCP y elimina la tentación de reimplementar el transporte. Python unifica el lenguaje con el backend y permite reutilizar los modelos Pydantic y los clientes HTTP. El adapter corre local como proceso del usuario: no expone endpoints públicos ni requiere autenticación adicional; el backend ya está protegido en HuggingFace Spaces.

**Alternativas consideradas.**

- *SDK TypeScript.* Viable si el ecosistema MCP del lado del cliente fuera predominantemente TS. Se descarta para no introducir un segundo lenguaje en el proyecto.
- *Implementación custom del protocolo MCP.* Conocimiento profundo del protocolo pero trabajo extra y riesgo de divergir cuando el estándar evolucione. No vale la pena para un proyecto de un solo autor.

**Costo.** $0 directo. Costo operativo: mantener el SDK actualizado y el adapter compatible con versiones nuevas del protocolo.

---

### CI/CD — GitHub Actions

**Qué.** GitHub Actions conectado al repo de GitHub, con pipelines para backend (test + build de imagen Docker + push a HuggingFace) y frontend (build estático + deploy a Cloudflare Pages). Triggers por push a main y por PR.

**Por qué.** El repo ya vive en GitHub; GitHub Actions corre en el mismo ecosistema sin credenciales de un proveedor cloud adicional y se factura solo por minutos de build dentro de un free tier generoso (2000 minutos mensuales para repos públicos). Los workflows son archivos YAML declarativos que viven en el repo y quedan bajo review como cualquier otro código. Es suficiente para un solo autor con trunk-based o branches cortas.

**Alternativas consideradas.**

- *Cloud Build con triggers desde GitHub (stack anterior).* Se descarta porque Cloud Build requiere billing habilitado en GCP, lo que implica tarjeta de crédito.
- *HuggingFace Actions / Spaces build automático.* Viable para Spaces pero no cubre el deploy del frontend a Cloudflare Pages ni la ejecución de tests en el workflow. Se descarta por cobertura insuficiente.
- *Cloud Deploy.* Más sofisticado para escenarios multi-environment con promoción progresiva. Se descarta porque un solo environment es suficiente en esta fase.

**Costo.** $0 dentro del free tier de GitHub Actions (repos públicos).

---

### Secretos — GitHub Secrets + env vars en HuggingFace Spaces

**Qué.** Secretos (claves de API de Groq y HuggingFace, URL de Neon, credenciales varias) almacenados en GitHub Secrets para los pipelines y como variables de entorno en la configuración del HuggingFace Space para el runtime del backend.

**Por qué.** GitHub Secrets está integrado con Actions sin proveedor adicional y forma parte del mismo ecosistema que el repo. Las variables de entorno en HuggingFace Spaces son el mecanismo soportado por la plataforma para inyectar configuración al contenedor. Ambos evitan archivos `.env` versionados y reducen el riesgo de leaks accidentales; el acceso queda auditado por la plataforma correspondiente.

**Alternativas consideradas.**

- *Secret Manager (stack anterior).* Se descarta porque requiere billing habilitado en GCP, lo que implica tarjeta de crédito.
- *Variables de entorno en código del Space.* Más simple pero pierde auditoría y rotación. Se descarta por buenas prácticas.
- *HashiCorp Vault.* Más potente pero requiere operar infraestructura adicional. Desproporcionado para este proyecto.

**Costo.** $0 dentro de los free tiers.

---

### Specs y planning — OpenSpec + Engram (híbrido)

**Qué.** SDD se ejecuta con artifact store híbrido: OpenSpec para los artefactos commiteables y revisables en PRs (proposal, specs, design, tasks); Engram para el contexto persistente entre sesiones y entre compactaciones.

**Por qué.** OpenSpec deja un rastro auditable en Git que sirve como portfolio del proceso de diseño, no solo del resultado. Engram cubre la fricción de retomar el proyecto después de pausas (el caso del autor, que usa el sistema durante una búsqueda de empleo con interrupciones). El modo híbrido los une: OpenSpec como fuente de verdad del artefacto, Engram como memoria de proceso.

**Alternativas consideradas.**

- *Solo OpenSpec.* Sin memoria entre sesiones; cada reanudación implica releer specs. Pierde valor en un proyecto de un solo autor con uso intermitente.
- *Solo Engram.* Sin artefactos commiteables; pierde el valor de portfolio del proceso SDD.

**Costo.** $0 directo.

---

## Costos mensuales estimados

| Componente | Estimado | Notas |
|---|---|---|
| Cloudflare Pages (frontend) | $0 | Free tier, sin tarjeta requerida. |
| HuggingFace Spaces CPU (backend) | $0 | Free tier, sin tarjeta requerida. |
| Neon Postgres | $0 | Free tier, sin tarjeta requerida. |
| Groq (LLM) | $0 | Free tier, sin tarjeta requerida. |
| HuggingFace Inference API | $0 | Free tier, sin tarjeta requerida. |
| GitHub Actions | $0 | Free tier para repos públicos. |
| GitHub Secrets | $0 | Incluido en el plan. |
| **Total estimado** | **$0 / mes** | Sin tarjeta de crédito requerida. |

---

## Próximas decisiones a documentar

Estas decisiones están abiertas y se documentarán a medida que se cierren, en este mismo archivo bajo una sección de "Decisiones cerradas" con la fecha relativa del slice en que se tomaron.

- **Autenticación.** Hoy el backend corre detrás de HuggingFace Spaces con tráfico solo del autor. Cuando se exponga más allá del single-user primario, hace falta auth en el adapter MCP y en el frontend. Candidatos a evaluar: API keys simples con rotación, OAuth contra un provider externo, o autenticación mutua entre adapter y backend. Decisión esperada durante Slice 2 o 3 si el alcance se expande.
- **Schema DB detallado.** Tablas, columnas, índices (incluido el índice de pgvector), políticas de retención y migraciones. Se documenta cuando se cierre el diseño del Slice 1 antes de implementar.
- **Contratos API.** Forma final de los endpoints REST, schemas de request / response, versionado y manejo de errores. Se documenta al cerrar el diseño de Slice 1 y se actualiza con cada nuevo slice.
- **Estrategia de prompts.** Versionado de prompts (archivos en repo con numeración), estrategias de cacheo, fallback entre modelos, y rúbrica del score de match. Se documenta cuando se itere la primera versión durante Slice 1.

---

*Documento vivo. Las decisiones cerradas se mueven a su sección definitiva cuando se validan en producción; las abiertas quedan registradas en "Próximas decisiones" hasta entonces.*