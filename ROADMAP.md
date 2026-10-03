# Roadmap — Asistente de Búsqueda de Empleo

> Documento vivo. Se actualiza a medida que se validan slices o cambian prioridades.

> **Nota de migración (septiembre 2026).** El roadmap se ajusta a un stack 100% free tier (sin tarjeta de crédito) en reemplazo del stack GCP original. Las capabilities del producto y las métricas del documento fundacional se mantienen sin cambios; cambian los destinos de deploy y los proveedores de LLM / embeddings. Detalle arquitectónico en [`STACK.md`](./STACK.md).

> **Reestructuración (septiembre 2026).** El roadmap se reorganiza en dos hitos de release después de descubrir, en la auditoría [`docs/audit/`](./audit/), bugs bloqueantes del MVP que se priorizan sobre nuevas features. Las nuevas requests de producto se posponen al release v2.0.

---

## TL;DR

Asistente agéntico de búsqueda de empleo con tres capacidades: evaluar match entre JD y perfil, adaptar CV y redactar outreach, y trackear el pipeline de aplicaciones. El Sprint 0 está cerrado en local (backend FastAPI, mock LLM, migraciones Alembic, adapter MCP); la migración al stack free tier está en curso y desbloquea el Slice 1 (Match JD ↔ Perfil), que entra en construcción a continuación.

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
- DB Postgres + pgvector (Neon): tablas `profile` (texto + embedding del perfil) y `job_evaluations` (JD, embedding, score, JSON de análisis, timestamp).
- Adapter MCP: tools `evaluate_job(text)` y `read_profile` / `update_profile` para que un cliente MCP (Claude Desktop, Cursor) pueda invocar el sistema.
- Frontend SvelteKit: una sola página `/evaluate` con input de JD y panel de resultado. Static export para Cloudflare Pages.
- LLM: Llama 3.3 70B Versatile vía Groq para el análisis estructurado.
- Embeddings: BGE-M3 vía HuggingFace Inference API para embeddings de perfil y JD.

**Métrica a validar.** Latencia end-to-end de una evaluación (texto recibido → score listo) y acuerdo entre el score del sistema y la decisión humana del autor sobre los primeros 20 JDs reales.

**Criterio de éxito.** 20 JDs reales evaluados con el sistema, decisión humana registrada después de leer el output, latencia mediana por debajo de 30 segundos, costo por evaluación dentro del estimado ($0 con free tiers).

---

### Slice 2 — Adaptar CV + Outreach

**Por qué este orden.** Depende de Slice 1: solo se adapta material para los puestos que pasaron el filtro de match. Construirlo después permite reutilizar la lectura de perfil y la estructura de `job_evaluations`, y enfoca el LLM en una tarea más acotada (reescritura) cuando el filtro grueso ya está validado.

**Scope concreto.**

- Backend FastAPI: endpoint `POST /jobs/{evaluation_id}/adapt` que genera bullets de CV adaptados y primer mensaje con tono configurable. Endpoint `GET /adaptations/{id}` para recuperar drafts.
- DB: tabla `adaptations` (FK a `job_evaluations`, JSON con bullets sugeridos, JSON con mensaje, flag de aprobado, timestamp).
- Adapter MCP: tool `adapt_for_job(evaluation_id, tone)` que devuelve los drafts para revisión.
- Frontend: segunda página `/adapt` que muestra el JD original, los bullets propuestos y el mensaje, con botón de aprobar / descartar.
- LLM: mismo Llama 3.3 70B Versatile vía Groq, con prompt separado del de evaluación.

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

## Hito v1.0 — MVP Early Adopters (release target: 14 oct 2026)

**Por qué este orden.** La auditoría [`docs/audit/`](./audit/) descubrió bugs que rompen la promesa central del producto (verificación de email nunca se ejecuta, el CV nunca llega al LLM en `jd_directed`, la cuota de adaptaciones no se consume, etc.). Cerrar esos bugs antes de invertir en nuevas features es la diferencia entre un MVP cobrable y un demo con riesgo de reputación.

**Scope concreto.**

- Cierra Fase 0 (seguridad) y Fase 1 (funcional) del [plan de remediación](./audit/PLAN.md): issues #44–#51.
- Tres issues nuevas del sprint: tabs CV vs JD en `/profile` (#61), `web_search` tool en el MCP adapter (#59), design tokens base en el frontend (#54).
- Stripe queda como única pasarela de cobro. **No** hay landing pública, **no** hay pasarela Colombia, **no** hay rediseño visual completo.

**Modelo de distribución.** Cobro a early adopters manuales que Daniel invita uno-a-uno. Sin signup público masivo. Email de verificación real (no stub) es prerequisito de cualquier cobro.

**Métricas a validar.** Email de verificación llega a la bandeja en <2 min; checkout de Stripe completa con un usuario verificado y devuelve 200; el score del audit refleja el CV subido en `jd_directed`; la cuota del plan se consume por adaptación; los tests del frontend corren en CI.

**Criterio de éxito.** Al menos un early adopter completa signup → verificación → pago → uso del producto sin errores 500. Lighthouse score > 85. Cero issues P0 abiertas al cierre.

**Issues del milestone.** Ver [milestone v1.0 en GitHub](https://github.com/danielCH26/asistcv/milestone/7). Kanban en vivo en [Proyecto #8 AsistCV Kanban](https://github.com/users/danielCH26/projects/8), columnas Backlog → Ready → In progress → In review → Done, con vista Timeline por Start/Target date.

---

## Hito v2.0 — Post-MVP Lanzamiento público (release target: dic 2026)

**Por qué después de v1.0.** Depende de v1.0 cerrado: sin verificación de email real no podés exponer un CTA "empezá gratis"; sin auditoría honesta del CV no podés comunicar honestidad; sin cuota RLS funcionando el multi-tenant filtra. Y depende de gates que **no se acceleran con paralelismo**: KYC de pasarela colombiana (1–3 semanas por banco), redacción legal (privacy + terms), copy de landing validado, bug bash con usuarios reales.

**Scope concreto.**

- Landing pública seria en `/` (producto, beneficios, "cómo funciona", planes, FAQ, CTA, footer con legal).
- Pasarela de pago Colombia (PSE / Nequi / Daviplata vía Wompi/Bold/PayU o Stripe+PSE).
- Rediseño visual completo Claymorphism + minimalismo suizo (#60), construido sobre los design tokens de v1.0 (#54) y la paleta completa de v2.0 (#57).
- Paleta de colores completa con roles semánticos y validación WCAG AA/AAA (#57).
- Cron de ofertas de empleo según perfil (#55): scheduler + `web_search` + matching + email resumen.
- Privacidad: privacy policy y terms redactados y revisados.
- KYC Colombia: completar la verificación con el proveedor elegido antes de exponer el path CO.
- Monitoreo + alertas (Sentry, Plausible analytics, dashboard de error rate).

**Métricas a validar.** Conversión landing → signup ≥ 5%; tasa de verificación de email ≥ 80%; suscripciones activas de Colombia vía PSE; ofertas relevantes entregadas por el cron con feedback positivo del usuario.

**Criterio de éxito.** El producto soporta el flujo completo de un usuario colombiano desde cero sin intervención manual. Lighthouse ≥ 90 en la landing. Cero issues P0/P1 abiertas.

**Issues del milestone.** Ver [milestone v2.0 en GitHub](https://github.com/danielCH26/asistcv/milestone/8).

---

## Hitos de infraestructura

### Sprint 0 — Fundación técnica (cerrado en local)

Las issues originales que dependían de GCP (#8 Cloud SQL, #10 Cloud Build, #11 Cloud Run) fueron congeladas y reemplazadas por issues equivalentes del stack free tier, listadas en la sección siguiente.

- [x] Documento fundacional publicado (`job-search-assistant.md`).
- [x] Stack tecnológico cerrado y documentado (`STACK.md`).
- [x] Roadmap publicado (`ROADMAP.md`).
- [x] Repo público en GitHub.
- [x] Estructura SDD inicializada (`openspec/`).
- [x] Monorepo con `backend/`, `frontend/`, `mcp-adapter/`, `infra/`, READMEs y Makefile (issue #6).
- [x] Backend FastAPI con `/health`, `/v1/ping`, `/docs`, settings, logging estructurado y placeholder `POST /v1/match` (issue #7).
- [x] `LLMProvider` con `MockProvider` determinista y factory por `LLM_PROVIDER` (issue #12).
- [x] Alembic + SQLModel operativos contra Postgres local con pgvector (docker-compose, issue #9).
- [x] Adapter MCP stdio con tools `ping` y `evaluate_match` → `/v1/match` (issue #13).

### Migración a stack free tier (issues nuevas, reemplaza #8 / #10 / #11)

Pendiente. Cada item reemplaza un issue del plan original sobre GCP.

- [ ] Provisionar Neon Postgres + pgvector y migrar la DB local (reemplaza #8 Cloud SQL).
- [ ] Setup de cuentas: Groq, HuggingFace, Cloudflare.
- [ ] Reescribir `Settings` (env vars) y clientes de LLM (Groq) y embeddings (HF Inference API) en el backend.
- [ ] CI/CD con GitHub Actions: tests + build de imagen Docker + push a HuggingFace Spaces para el backend; build estático + deploy a Cloudflare Pages para el frontend (reemplaza #10 Cloud Build).
- [ ] Deploy del backend en HuggingFace Spaces con SDK Docker (reemplaza #11 Cloud Run).
- [ ] Configurar secretos: GitHub Secrets para CI, env vars en HF Spaces para runtime (reemplaza Secret Manager).
- [ ] Deploy del frontend en Cloudflare Pages accesible públicamente.
- [ ] Validación end-to-end: cliente MCP → backend en HF → Neon → Groq / HF Inference.
- [ ] Adapter MCP ejecutándose localmente y conectado al backend remoto.

### Slices de producto

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

- [ ] Costo total por aplicación procesada medido y dentro del presupuesto ($0 con free tier).
- [ ] Latencia mediana por debajo de 30 segundos en `POST /jobs/evaluate`.
- [ ] Tasa de respuestas positivas sobre aplicaciones enviadas medida.
- [ ] Calidad de CV adaptado evaluada con panel de 3-5 personas.

---

## Costos mensuales estimados (stack free tier)

| Componente | Estimado | Notas |
|---|---|---|
| Cloudflare Pages (frontend) | $0 | Free tier, sin tarjeta requerida. |
| HuggingFace Spaces CPU (backend) | $0 | Free tier, sin tarjeta requerida. |
| Neon Postgres | $0 | Free tier, sin tarjeta requerida. |
| Groq (LLM) | $0 | Free tier, sin tarjeta requerida. |
| HuggingFace Inference API | $0 | Free tier, sin tarjeta requerida. |
| GitHub Actions | $0 | Free tier para repos públicos. |
| **Total estimado** | **$0 / mes** | Sin tarjeta de crédito requerida. |

---

## Riesgos identificados

**R1 — El score del match no es calibrable.** Riesgo de que el modelo devuelva scores inflados o inconsistentes entre JDs similares. Mitigación: durante Slice 1 se valida el score contra decisiones humanas del autor en los primeros 20 JDs reales; si el acuerdo es bajo, se ajusta el prompt y la rúbrica antes de invertir en Slice 2.

**R2 — Los free tiers se quedan cortos o cambian sus condiciones.** Riesgo de que algún proveedor cambie su free tier (límite de rate, costo oculto, requisito de tarjeta introducido a futuro). Mitigación: monitorear uso real desde el cierre de la migración; el costo estimado es $0 hoy y el costo de portar a otra plataforma es bajo porque el código no está atado a un proveedor específico; el stack GCP anterior queda como referencia documentada en [`STACK.md`](./STACK.md) por si hay que re-plataformar.

**R3 — Adaptaciones suenan genéricas o inventadas.** Riesgo de que el LLM agregue skills o logros que el usuario no tiene, rompiendo el anti-patrón explícito. Mitigación: prompts con instrucciones explícitas de "solo reorganizar, no inventar"; revisión humana obligatoria antes de aprobar; auditoría periódica de las adaptaciones aprobadas para detectar drift.

**R4 — El proyecto se abandona por fricción de uso.** El autor es el usuario primario; si la fricción diaria (deploys, debugging, prompts que rompen) supera el valor, el sistema deja de usarse. Mitigación: priorizar simplicidad operativa sobre features; CI/CD automatizado desde el inicio; documentar decisiones y procedimientos para reducir el costo de retomar después de pausas.

**R5 — Latencia inconsistente del backend en HuggingFace Spaces.** Los Spaces CPU gratuitos pueden tener cold start y recursos compartidos, lo que introduce variabilidad en latencia. Mitigación: medir latencia por percentiles (no solo mediana) en Slice 1; si el percentil 95 resulta inaceptable, evaluar upgrade del Space o plan B de hosting.

---

*Documento vivo. Se actualiza a medida que se validan slices o cambian prioridades.*