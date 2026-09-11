# Roadmap — Asistente de Búsqueda de Empleo

> Documento vivo. Se actualiza a medida que se validan slices o cambian prioridades.

---

## TL;DR

Asistente agéntico de búsqueda de empleo con tres capacidades: evaluar match entre JD y perfil, adaptar CV y redactar outreach, y trackear el pipeline de aplicaciones. El proyecto está en fase de setup: documento fundacional, stack cerrado y roadmap definidos; el primer slice (match JD ↔ perfil) entra en construcción a continuación.

---

## Producto

Documento fundacional en [`job-search-assistant.md`](./job-search-assistant.md). Resume el problema, la solución propuesta, los anti-patrones explícitos (no auto-applier, no inventa experiencia, no chatbot mágico) y los criterios de éxito.

Tres capacidades centrales que el producto entrega:

1. **Match JD ↔ Perfil** — análisis semántico del puesto contra el perfil del usuario. Devuelve score honesto, razones del match, skills faltantes y energía recomendada para invertir.
2. **Adaptar CV + Outreach** — para los puestos que pasan el filtro anterior, reescribe los bullets del CV y redacta el primer mensaje. El usuario revisa y aprueba antes de enviar.
3. **Tracking Pipeline** — registra aplicaciones, status, fechas de seguimiento y recordatorios. Cierra el ciclo de uso.

Audiencia primaria: el propio autor durante su búsqueda real. Secundarias: devs Latam, transiciones de carrera, equipos chicos de recruiting.

---

## Slices de implementación

El orden de los slices sigue el flujo natural de uso: primero se necesita poder evaluar un puesto para decidir si vale la pena invertir energía; después se adapta el material; al final se trackea lo que se manda. Construir en otro orden genera productos sin uso real o dependencias que no se pueden ejercitar hasta tarde.

### Slice 1 — Match JD ↔ Perfil

**Por qué este orden.** Es la entrada del sistema. Sin un evaluador honesto, todo lo demás (CV adaptado, outreach) corre contra cualquier JD, no contra los buenos candidatos. Validar primero el match significa validar primero el corazón del producto y la integración más riesgosa del stack (LLM + embeddings + perfil persistido).

**Scope concreto.**

- Backend FastAPI: endpoint `POST /jobs/evaluate` que recibe texto de JD y devuelve score, razones, skills faltantes, energía recomendada. Endpoint `GET /profile` y `PUT /profile` para gestionar el perfil del usuario.
- DB Postgres + pgvector: tablas `profile` (texto + embedding del perfil) y `job_evaluations` (JD, embedding, score, JSON de análisis, timestamp).
- Adapter MCP: tools `evaluate_job(text)` y `read_profile` / `update_profile` para que un cliente MCP (Claude Desktop, Cursor) pueda invocar el sistema.
- Frontend SvelteKit: una sola página `/evaluate` con input de JD y panel de resultado. Static export para Firebase Hosting.
- Vertex AI: text-multilingual-embedding-002 para embeddings de perfil y JD; Claude 3.5 Haiku para el análisis estructurado.

**Métrica a validar.** Latencia end-to-end de una evaluación (texto recibido → score listo) y acuerdo entre el score del sistema y la decisión humana del autor sobre los primeros 20 JDs reales.

**Criterio de éxito.** 20 JDs reales evaluados con el sistema, decisión humana registrada después de leer el output, latencia mediana por debajo de 30 segundos, presupuesto de costo por evaluación dentro del estimado.

---

### Slice 2 — Adaptar CV + Outreach

**Por qué este orden.** Depende de Slice 1: solo se adapta material para los puestos que pasaron el filtro de match. Construirlo después permite reutilizar la lectura de perfil y la estructura de `job_evaluations`, y enfoca el LLM en una tarea más acotada (reescritura) cuando el filtro grueso ya está validado.

**Scope concreto.**

- Backend FastAPI: endpoint `POST /jobs/{evaluation_id}/adapt` que genera bullets de CV adaptados y primer mensaje con tono configurable. Endpoint `GET /adaptations/{id}` para recuperar drafts.
- DB: tabla `adaptations` (FK a `job_evaluations`, JSON con bullets sugeridos, JSON con mensaje, flag de aprobado, timestamp).
- Adapter MCP: tool `adapt_for_job(evaluation_id, tone)` que devuelve los drafts para revisión.
- Frontend: segunda página `/adapt` que muestra el JD original, los bullets propuestos y el mensaje, con botón de aprobar / descartar.
- LLM: mismo Claude 3.5 Haiku, con prompt separado del de evaluación.

**Métrica a validar.** Tasa de aprobación humana de los drafts (cuántos se aprueban sin reescritura) y calidad percibida de los bullets adaptados en un panel chico (3-5 personas).

**Criterio de éxito.** Al menos 10 adaptaciones generadas para JDs reales; más de la mitad aprobadas con ajustes menores o sin ajustes; drafts enviados producen respuesta o entrevista atribuible.

---

### Slice 3 — Tracking Pipeline

**Por qué este orden.** Es la última pieza porque captura valor del flujo completo: aplica a quien ya evaluaste como buen match (Slice 1) y adaptaste material (Slice 2). Sin las dos anteriores, no hay qué trackear. Construirlo al final evita rehacer el schema cuando todavía no se estabilizó qué se persiste.

**Scope concreto.**

- Backend FastAPI: endpoints CRUD para `applications` (crear desde una adaptación aprobada, actualizar status, listar, archivar). Endpoint de recordatorios: `GET /applications/due` para follow-ups pendientes.
- DB: tabla `applications` (FK a `adaptations`, status enum, fechas de envío, respuesta y seguimiento, notas libres).
- Adapter MCP: tools `create_application`, `update_status`, `list_due_followups`.
- Frontend: tercera página `/pipeline` estilo kanban con columnas por status y vista de "due today".

**Métricas a validar.** Cobertura: porcentaje de aplicaciones que entraron al pipeline vs aplicaciones totales hechas por el autor. Cumplimiento de follow-ups en la fecha marcada.

**Criterio de éxito.** Las 30+ aplicaciones del criterio fundacional están registradas en el pipeline; el sistema recuerda los follow-ups a tiempo; las métricas primarias del documento fundacional se pueden calcular desde los datos.

---

## Hitos de infraestructura

- [x] Documento fundacional publicado (`job-search-assistant.md`).
- [x] Stack tecnológico cerrado y documentado (`STACK.md`).
- [x] Roadmap publicado (`ROADMAP.md`).
- [ ] OpenSpec inicializado y convenciones SDD aplicadas al proyecto.
- [ ] Repositorio con CI/CD configurado (Cloud Build trigger desde GitHub).
- [ ] Secret Manager con credenciales de GCP, Vertex AI y DB.
- [ ] Deploy del backend en Cloud Run respondiendo a healthcheck.
- [ ] Deploy del frontend en Firebase Hosting accesible públicamente.
- [ ] Cloud SQL provisionado con pgvector y migraciones iniciales aplicadas.
- [ ] Adapter MCP ejecutándose localmente y conectado al backend remoto.
- [ ] Slice 1 funcional y validado contra los primeros 20 JDs reales.
- [ ] Slice 2 funcional y validado con 10+ adaptaciones.
- [ ] Slice 3 funcional y las 30+ aplicaciones del criterio registradas.

---

## Métricas del documento fundacional

### Primarias

- [ ] 30+ aplicaciones procesadas con el sistema como apoyo.
- [ ] 80% de coincidencia entre match del sistema y decisión humana.
- [ ] Tiempo mediano de evaluación de JD: 15 min → 2 min.
- [ ] 3+ entrevistas atribuibles a la calidad del CV o mensaje adaptado.

### Secundarias

- [ ] Costo total por aplicación procesada medido y dentro del presupuesto.
- [ ] Latencia mediana por debajo de 30 segundos en `POST /jobs/evaluate`.
- [ ] Tasa de respuestas positivas sobre aplicaciones enviadas medida.
- [ ] Calidad de CV adaptado evaluada con panel de 3-5 personas.

---

## Riesgos identificados

**R1 — El score del match no es calibrable.** Riesgo de que el modelo devuelva scores inflados o inconsistentes entre JDs similares. Mitigación: durante Slice 1 se valida el score contra decisiones humanas del autor en los primeros 20 JDs reales; si el acuerdo es bajo, se ajusta el prompt y la rúbrica antes de invertir en Slice 2.

**R2 — El costo se dispara por uso.** Vertex AI cobra por tokens; un uso intenso (muchas evaluaciones, re-adaptaciones, prompts largos) puede empujar el costo por encima del presupuesto mensual estimado. Mitigación: instrumentar costo por request desde el primer slice, alertas cuando una operación supera un umbral, y caché de embeddings del perfil para no recalcular en cada request.

**R3 — Adaptaciones suenan genéricas o inventadas.** Riesgo de que el LLM agregue skills o logros que el usuario no tiene, rompiendo el anti-patrón explícito. Mitigación: prompts con instrucciones explícitas de "solo reorganizar, no inventar"; revisión humana obligatoria antes de aprobar; auditoría periódica de las adaptaciones aprobadas para detectar drift.

**R4 — El proyecto se abandona por fricción de uso.** El autor es el usuario primario; si la fricción diaria (deploys, debugging, prompts que rompen) supera el valor, el sistema deja de usarse. Mitigación: priorizar simplicidad operativa sobre features; CI/CD automatizado desde el inicio; documentar decisiones y procedimientos para reducir el costo de retomar después de pausas.

---

*Documento vivo. Se actualiza a medida que se validan slices o cambian prioridades.*