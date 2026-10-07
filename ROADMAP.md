# Roadmap — Asistente de Búsqueda de Empleo

> Documento vivo. Se actualiza a medida que se validan slices o cambian prioridades.

> **Nota de migración (septiembre 2026).** El roadmap se ajusta a un stack 100% free tier (sin tarjeta de crédito) en reemplazo del stack GCP original. Las capabilities del producto y las métricas del documento fundacional se mantienen sin cambios; cambian los destinos de deploy y los proveedores de LLM / embeddings. Detalle arquitectónico en [`STACK.md`](./STACK.md).

> **Reestructuración (septiembre 2026).** El roadmap se reorganiza en dos hitos de release después de descubrir, en la auditoría [`docs/audit/`](./audit/), bugs bloqueantes del MVP que se priorizan sobre nuevas features. Las nuevas requests de producto se difieren al release v2.0.

---

## TL;DR

Asistente agéntico de búsqueda de empleo con tres capacidades planificadas, dos ya en producción:

- **Match JD ↔ Perfil** ✅ — análisis semántico del puesto contra el perfil del usuario. Devuelve score honesto, razones, skills faltantes y energía recomendada.
- **Adaptación de CV** ✅ — para los puestos que pasan el filtro anterior, reescribe los bullets del CV. El usuario revisa y aprueba antes de enviar.
- **Outreach + Tracking Pipeline** ⏸️ — diferido al release v2.0 (Dec 2026). Sin código, sin migración, sin tool MCP.

El Sprint 0 está cerrado. La migración al stack free tier está cerrada. Slice 1 (Match) y Slice 2 (Adaptación) están mergeados en `main`. El sprint actual es **v1.0 — MVP Early Adopters**, con release target 14 oct 2026.

---

## Producto

Documento fundacional en [`job-search-assistant.md`](./job-search-assistant.md). Resume el problema, la solución propuesta, los anti-patrones explícitos (no auto-applier, no inventa experiencia, no chatbot mágico) y los criterios de éxito.

Audiencia primaria: el propio autor durante su búsqueda real. Secundarias: devs Latam, transiciones de carrera, equipos chicos de recruiting.

---

## Endpoints y herramientas hoy en producción

| Capacidad | Endpoint backend | Tool MCP |
|---|---|---|
| Match JD ↔ Perfil | `POST /v1/match` | `evaluate_match` |
| Listar historial de matches del usuario | `GET /v1/me/analyses` | — |
| Detalle de un análisis | `GET /v1/me/analyses/{analysis_id}` | — |
| Adaptar CV | `POST /v1/adaptations` | — |
| Listar adaptaciones | `GET /v1/adaptations` | — |
| Detalle de una adaptación | `GET /v1/adaptations/{adaptation_id}` | — |
| Aprobar / descartar adaptación | `POST /v1/adaptations/{adaptation_id}/approve` (o `/discard`) | — |
| Audit anónimo (capture + claim) | `POST /v1/audit/{token}/capture-email`, `POST /v1/audit/{token}/claim` | — |
| Auth | `POST /v1/auth/register`, `POST /v1/auth/login`, `POST /v1/auth/refresh`, `POST /v1/auth/logout` | — |
| Email verify | `POST /v1/verify-email/request`, `GET /v1/verify-email/confirm` | — |
| Profile | `GET /v1/profiles/{profile_id}`, `PUT /v1/profiles/{profile_id}` | — |
| Billing | `POST /v1/billing/checkout`, `POST /v1/billing/portal`, `POST /v1/webhooks/stripe`, `GET /v1/billing/plans` | — |
| Recruiter (consented) | `POST /v1/recruiter/candidates`, `POST /v1/recruiter/candidates/{id}/match` | — |
| Health | `GET /v1/health`, `GET /v1/ping` | `ping`, `get_health` |

Las tools MCP enumeradas en el repo son: `ping`, `get_health`, `evaluate_match`. El resto de la surface hoy es solo HTTP desde el frontend.

---

## Hito v1.0 — MVP Early Adopters (release target: 14 oct 2026)

**Por qué este orden.** La auditoría [`docs/audit/`](./audit/) descubrió bugs que rompen la promesa central del producto (verificación de email nunca se ejecuta, el CV nunca llega al LLM en `jd_directed`, la cuota de adaptaciones no se consume, etc.). Cerrar esos bugs antes de invertir en nuevas features es la diferencia entre un MVP cobrable y un demo con riesgo de reputación.

**Scope concreto.**

- Cierra Fase 0 (seguridad), Fase 1 (funcional P0/P1), Fase 2 (honestidad + red de seguridad) y Fase 3 (docs + deuda) del [plan de remediación](./audit/PLAN.md): issues #44–#51.
- Issues nuevas del sprint: **#54** FE design tokens base, **#59** MCP tool de búsqueda de ofertas con grounding para fecha actual, **#61** FE tabs CV vs JD.
- Stripe queda como única pasarela de cobro. **No** hay landing pública, **no** hay pasarela Colombia, **no** hay rediseño visual completo.

**Modelo de distribución.** Cobro a early adopters manuales que el maintainer invita uno-a-uno. Sin signup público masivo. Email de verificación real (no stub) es prerequisito de cualquier cobro.

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
- Cron de ofertas de empleo según perfil (#55): scheduler + búsqueda externa de ofertas + email resumen al usuario.
- Privacidad: privacy policy y terms redactados y revisados.
- KYC Colombia: completar la verificación con el proveedor elegido antes de exponer el path CO.
- Monitoreo + alertas (Sentry, Plausible analytics, dashboard de error rate).
- **Outreach y Tracking Pipeline**, si se reabre la decisión (hoy están diferidos).

**Métricas a validar.** Conversión landing → signup ≥ 5%; tasa de verificación de email ≥ 80%; suscripciones activas de Colombia vía PSE; ofertas relevantes entregadas por el cron con feedback positivo del usuario.

**Criterio de éxito.** El producto soporta el flujo completo de un usuario colombiano desde cero sin intervención manual. Lighthouse ≥ 90 en la landing. Cero issues P0/P1 abiertas.

**Issues del milestone.** Ver [milestone v2.0 en GitHub](https://github.com/danielCH26/asistcv/milestone/8).

---

## Hitos de infraestructura

### Sprint 0 — Fundación técnica ✅

- [x] Documento fundacional publicado (`job-search-assistant.md`).
- [x] Stack tecnológico cerrado y documentado (`STACK.md`).
- [x] Roadmap publicado (`ROADMAP.md`).
- [x] Repo público en GitHub.
- [x] Estructura SDD inicializada (`openspec/`) — archivada al migrar a ODD.
- [x] Monorepo con `backend/`, `frontend/`, `mcp-adapter/`, `infra/`, READMEs y Makefile.
- [x] Backend FastAPI con `/health`, `/v1/ping`, `/docs`, settings, logging estructurado y `LLMProvider` (mock + factory).
- [x] Alembic + SQLModel operativos contra Postgres local con pgvector (docker-compose).
- [x] Adapter MCP stdio con tools `ping` y `evaluate_match`.

### Migración a stack free tier ✅ (issues #38–#43)

- [x] Provisionar Neon Postgres + pgvector y migrar la DB local.
- [x] Setup de cuentas: Groq, HuggingFace, Neon, Render, Cloudflare.
- [x] Reescribir `Settings` y clientes de LLM (Groq) y embeddings (HF Inference API) en el backend.
- [x] CI/CD con GitHub Actions: tests + build + deploy a Render (backend) y Cloudflare Pages (frontend).
- [x] Deploy del backend en Render (Web Service free tier).
- [x] Configurar secretos: GitHub Secrets para CI, env vars en Render / Cloudflare para runtime.
- [x] Deploy del frontend en Cloudflare Pages accesible públicamente.
- [x] Validación end-to-end: cliente MCP → backend en Render → Neon → Groq / HF Inference.

### Slices de producto ✅

- [x] Slice 1 — Match JD ↔ Perfil mergeado en `main` (sprint-1-match-jd, ver `openspec/changes/archive/`).
- [x] Slice 2 — Adaptación de CV mergeado en `main` (sprint-adapt-cv-outreach, ver `openspec/changes/archive/`).
- [ ] Slice 3 — Tracking Pipeline: **diferido a v2.0**.

---

## Métricas del documento fundacional

### Primarias

- [ ] 30+ aplicaciones procesadas con el sistema como apoyo.
- [ ] 80% de coincidencia entre match del sistema y decisión humana.
- [ ] Tiempo mediano de evaluación de JD: 15 min → 2 min.
- [ ] 3+ entrevistas atribuibles a la calidad del CV adaptado.

### Secundarias

- [ ] Costo total por aplicación procesada medido y dentro del presupuesto ($0 con free tier).
- [ ] Latencia mediana por debajo de 30 segundos en `POST /v1/match`.
- [ ] Tasa de respuestas positivas sobre aplicaciones enviadas medida.
- [ ] Calidad de CV adaptado evaluada con panel de 3-5 personas.

---

## Costos mensuales estimados (stack free tier)

| Componente | Estimado | Notas |
|---|---|---|
| Cloudflare Pages (frontend) | $0 | Free tier, sin tarjeta requerida. |
| Render Web Service (backend) | $0 | Free tier, sin tarjeta requerida. |
| Neon Postgres | $0 | Free tier, sin tarjeta requerida. |
| Groq (LLM) | $0 | Free tier, sin tarjeta requerida. |
| HuggingFace Inference API | $0 | Free tier, sin tarjeta requerida. |
| GitHub Actions | $0 | Free tier para repos públicos. |
| **Total estimado** | **$0 / mes** | Sin tarjeta de crédito requerida. |

---

## Riesgos identificados

**R1 — El score del match no es calibrable.** Riesgo de que el modelo devuelva scores inflados o inconsistentes entre JDs similares. Mitigación: durante Slice 1 se valida el score contra decisiones humanas del autor en los primeros 20 JDs reales; si el acuerdo es bajo, se ajusta el prompt y la rúbrica antes de invertir en Slice 2.

**R2 — Los free tiers se quedan cortos o cambian sus condiciones.** Riesgo de que algún proveedor cambie su free tier (límite de rate, costo oculto, requisito de tarjeta introducido a futuro). Mitigación: monitorear uso real desde el cierre de la migración; el costo estimado es $0 hoy y el costo de portar a otra plataforma es bajo porque el código no está atado a un proveedor específico; el stack GCP anterior queda como referencia documentada en [`STACK.md`](./STACK.md) por si hay que re-plataformar.

**R3 — Adaptaciones suenan genéricas o inventadas.** Riesgo de que el LLM agregue skills o logros que el usuario no tiene, rompiendo el anti-patrón explícito. Mitigación: prompts con instrucciones explícitas de "solo reorganizar, no inventar"; revisión humana obligatoria antes de aprobar; auditoría periódica (Fase 2 / C6 — hallazgo #49 — verifica que las métricas numéricas del CV no se inflen).

**R4 — El proyecto se abandona por fricción de uso.** El autor es el usuario primario; si la fricción diaria (deploys, debugging, prompts que rompen) supera el valor, el sistema deja de usarse. Mitigación: priorizar simplicidad operativa sobre features; CI/CD automatizado desde el inicio; documentar decisiones y procedimientos para reducir el costo de retomar después de pausas.

**R5 — Latencia inconsistente del backend en Render.** Los servicios gratuitos pueden tener cold start y recursos compartidos, lo que introduce variabilidad en latencia. Mitigación: medir latencia por percentiles (no solo mediana); si el percentil 95 resulta inaceptable, evaluar upgrade del plan o migración del backend.

---

*Documento vivo. Se actualiza a medida que se validan slices o cambian prioridades.*