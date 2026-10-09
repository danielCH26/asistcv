# AsistCV

Asistente agéntico de búsqueda de empleo. Hoy entrega **Match JD ↔ perfil** y **Adaptación de CV** (reorganiza bullets del CV del usuario contra una JD, sin inventar experiencia). Outreach y Tracking Pipeline están diferidos a v2.0. El sistema nunca envía nada sin aprobación humana.

## TL;DR

AsistCV es una herramienta personal que ayuda a aplicar mejor a los 5-10 puestos que valen la pena, en lugar de auto-aplicar a 100. La audiencia primaria es el propio autor durante su búsqueda de empleo; las audiencias secundarias son desarrolladores Latam que aplican a empresas US/EU, personas en transición de carrera y pequeños equipos de recruiting.

**Estado actual (octubre 2026):** v1.0 MVP Early Adopters cerrado: las fases 0/1/2/3 del [plan de remediación](./audit/PLAN.md) y las features críticas están en producción — match verificado end-to-end (score honesto con embeddings Gemini, sin tarjeta), adaptación con validador anti-alucinación, billing Stripe, rate limiting, RLS y design system v2 (teal + clay, issue #60 slice 1). El stack es 100% free tier sin tarjeta de crédito. Métricas reales en [docs/metrics.md](./docs/metrics.md). El próximo paso es v2.0 (landing, pasarela Colombia, cron de ofertas) — ver [ROADMAP.md](./ROADMAP.md).

## El problema

Buscar trabajo hoy es un trabajo en sí mismo, y está roto en varios sentidos:

- **El volumen mata la calidad.** Hay más ofertas abiertas que nunca, pero el formato es inconsistente: cada empresa describe el mismo puesto de 10 formas distintas. Leer 30 JDs para encontrar 5 buenos candidatos es una jornada entera.
- **Adaptar el CV se hace mal.** Cambiar tres palabras clave y rezar no alcanza: los sistemas ATS lo descartan y el reclutador nota que es genérico. Adaptar de verdad toma una energía que no se tiene cuando se llevan 20 aplicaciones.
- **El primer mensaje se decide en frío.** Un mail genérico se ignora. Uno personalizado, breve, con contexto de la empresa, consigue respuestas. Pero escribirlos lleva tiempo que se agota rápido.

Para alguien que busca trabajo en serio (3-6 meses), esto son 100+ horas de trabajo mecánico que podrían enfocarse en preparar entrevistas, aprender o descansar. Y aun así, el resultado suele ser peor que si cada aplicación tuviera 30 minutos de cuidado.

## La solución

Las capacidades del producto, en orden de uso natural: primero evaluar, después adaptar. Tracking de aplicaciones y outreach se difieren a v2.0 (ver [ROADMAP.md](./ROADMAP.md)). Las métricas del documento con datos reales: [docs/metrics.md](./docs/metrics.md).

### Match JD ↔ Perfil

El usuario pega una descripción de puesto (texto o link) y el sistema devuelve en segundos un score honesto de match contra su perfil, las razones del score (skills que encajan, skills que faltan, cosas aprendibles rápido), y una recomendación de cuánta energía vale la pena invertir (alto / medio / bajo). No es un "sí o no" binario: es una segunda opinión informada para decidir mejor. La integración crítica es LLM + embeddings + perfil persistido en Postgres con pgvector. Endpoint: `POST /v1/match`. Tool MCP: `evaluate_match`.

### Adaptación de CV

Para los puestos que pasan el filtro anterior, el sistema reescribe los bullets relevantes del CV para resaltar la experiencia que el puesto pide. El usuario revisa y aprueba antes de mandar nada; el sistema nunca envía nada por su cuenta. La restricción explícita es reorganizar y resaltar lo que el usuario ya tiene: jamás inventa skills o logros (la auditoría C6 cubre esta promesa con un test de métricas numéricas). Endpoint: `POST /v1/adaptations`. Los drafts viven en la tabla `adaptations`.

### Diferido a v2.0

- **Outreach** — primer mensaje con tono configurable. Sin código, sin migración, sin tool.
- **Tracking Pipeline** — kanban de aplicaciones con fechas y follow-ups. Sin código, sin migración, sin tool.

La decisión de diferir ambas se tomó en la auditoría de septiembre 2026: no se entra al release v1.0 sin (a) verificación de email real, (b) audit honesto del CV, (c) cuota RLS funcionando. Detalle en [docs/audit/PLAN.md](./audit/PLAN.md) y la discusión en la sección "Outreach y Tracking Pipeline" del [ROADMAP.md](./ROADMAP.md).

## Lo que NO es

El espacio está lleno de herramientas con propuestas similares y problemas diferentes. Los anti-patrones explícitos del proyecto:

- **No es un auto-applier.** No manda 100 CVs sin supervisión. Eso es spam, daña la reputación a largo plazo y los reclutadores lo detectan.
- **No inventa experiencia.** No genera skills o logros que el usuario no tenga. Parte del CV real y solo reorganiza y resalta. (Auditado del sistema: la auditoría C6 verifica numéricamente que los bullets adaptados no introducen cifras inventadas.)
- **No es un chatbot mágico** estilo "consigue tu trabajo soñado con IA". Es una herramienta de trabajo que se gana su lugar ahorrando tiempo real.
- **No reemplaza el trabajo humano.** Automatiza el 70% mecánico; el 30% estratégico (buscar, entrevistar, decidir) sigue siendo del usuario.

## Estado del proyecto

### Contexto del stack

El stack original estaba diseñado sobre GCP completo (Cloud Run, Cloud SQL, Vertex AI, Cloud Build, Secret Manager), pero requiere tarjeta de crédito para habilitar billing, lo que bloqueaba el deploy. En septiembre de 2026 se migró a un stack 100% free tier — **Cloudflare Pages** para frontend, **Neon Postgres** para la DB, **Groq** para LLM, **HuggingFace Inference API** para embeddings, **GitHub Actions** para CI, **Render** para el backend — sin cambios en los frameworks (FastAPI, SvelteKit, pgvector, SDK `mcp`) y manteniendo las mismas decisiones de diseño. Detalle en [`STACK.md`](./STACK.md).

### Hitos cerrados (issues #38–#43)

- [x] Setup de cuentas (Groq, HuggingFace, Neon) + API keys en GitHub Secrets (#38)
- [x] Migrar backend: Vertex stub → Groq (LLM) + HuggingFace Inference (embeddings) (#39)
- [x] Conectar backend a Neon Postgres (#40)
- [x] Deploy backend a Render (#41)
- [x] Deploy frontend SvelteKit a Cloudflare Pages (#42)
- [x] CI/CD con GitHub Actions (#43)
- [x] Adapter MCP stdio con tools `ping`, `get_health`, `evaluate_match`
- [x] Slice 1 — Match JD ↔ Perfil (sprint-1-match-jd)
- [x] Slice 2 — Adaptación de CV (sprint-adapt-cv-outreach)
- [x] Fases 0/1/2/3 del [plan de remediación](./audit/PLAN.md) (issues #44–#51)

### v1.0 (milestone abierto)

Issues abiertas para cerrar antes del 14 oct 2026:

- [ ] [v1.0] FE design tokens base (#54)
- [ ] [v1.0] MCP web_search tool (#59)
- [ ] [v1.0] FE tabs CV vs JD en `/profile` (#61)
- [ ] [P2] C8 docs+makefile (#51) — en este branch
- [ ] Cerrar issues del sprint `sprint-adapt-cv-outreach` (#77-#87) que ya están mergeadas en código pero abiertas en el tracker

Ver el [milestone v1.0 en GitHub](https://github.com/danielCH26/asistcv/milestone/7).

## Stack tecnológico (resumen)

| Capa | Tecnología | Destino |
|---|---|---|
| Frontend | SvelteKit (TypeScript, npm) | Cloudflare Pages (auto-deploy desde main) |
| Backend | FastAPI sobre Python 3.12 | Render Web Service (auto-deploy desde main) |
| Base de datos | Postgres + pgvector | Neon (serverless) |
| LLM | Llama 3.x vía Groq | Groq (free tier) |
| Embeddings | BGE-M3 | HuggingFace Inference API (free tier) |
| Adapter MCP | Python con SDK `mcp` oficial | Local / ejecución por usuario |
| CI/CD | GitHub Actions | Pipelines por push y por PR |
| Secretos | GitHub Secrets + env vars en Render / Cloudflare dashboard | — |

Costo estimado total: **$0 / mes**, sin tarjeta de crédito requerida. Decisiones completas, con justificación y alternativas descartadas, en [`STACK.md`](./STACK.md).

## Roadmap (resumen)

| Hito | Capacidad | Estado |
|---|---|---|
| Sprint 0 — Fundación técnica | Backend, mock LLM, Alembic, MCP adapter | Cerrado |
| Migración free tier | Settings + clients + deploy en Render/Neon/Cloudflare | Cerrado (#38–#43) |
| Slice 1 | Match JD ↔ Perfil | Cerrado (sprint-1-match-jd) |
| Slice 2 | Adaptación de CV | Cerrado (sprint-adapt-cv-outreach) |
| v1.0 | MVP Early Adopters | En curso (target 14 oct 2026) |
| v2.0 | Lanzamiento público (landing + pasarela CO + Claymorphism full + outreach + tracking + cron ofertas) | Planificado (diciembre 2026) |

El detalle de cada hito, con scope, métricas y criterios de éxito, en [`ROADMAP.md`](./ROADMAP.md).

## Métricas de éxito

Las métricas vienen del documento fundacional. Las primarias son criterio de éxito del proyecto; las secundarias se miden cuando es posible sin fricción adicional.

### Primarias

| Métrica | Objetivo |
|---|---|
| Aplicaciones procesadas con el sistema | 30 o más |
| Coincidencia match del sistema vs decisión humana | 80% o más |
| Tiempo mediano de evaluación de un JD | 15 min → 2 min |
| Entrevistas atribuibles a CV adaptado | 3 o más |

### Secundarias

| Métrica | Objetivo |
|---|---|
| Costo por aplicación procesada | Dentro del presupuesto ($0 / mes, free tier) |
| Latencia mediana de `POST /v1/match` | Por debajo de 30 segundos |
| Tasa de respuestas positivas | Medida y registrada |
| Calidad de CV adaptado | Evaluación con panel de 3-5 personas |

## Estructura del repositorio

```
asistcv/
├── job-search-assistant.md    # PRD fundacional (problema, solución, anti-patrones)
├── PROJECT.md                 # este archivo
├── ROADMAP.md                  # plan de hitos con scope, métricas y criterios
├── STACK.md                   # decisiones arquitectónicas cerradas y abiertas
├── README.md                  # quick start
├── Makefile                   # tareas de dev local
├── odd/                       # artifacts del flujo ODD (Gentle-AI v4.0)
│   └── tasks/                 # feature documents (uno por sprint)
├── openspec/                  # artifacts del flujo SDD anterior (archivados)
├── backend/                   # FastAPI service (deploy a Render)
├── frontend/                  # SvelteKit app (deploy a Cloudflare Pages)
├── mcp-adapter/               # SDK `mcp` en Python, corre local
└── infra/                     # docker-compose local + .env.example
```

## Desarrollo local

El desarrollo local es independiente del deploy: docker-compose levanta Postgres con pgvector, el backend corre con `LLM_PROVIDER=mock` sin credenciales, y el frontend con `npm run dev`. El deploy corre sobre GitHub Actions → Render / Cloudflare Pages, automático desde main. Detalle en [`docs/DEPLOY.md`](./DEPLOY.md).

### Prerequisitos

- Python 3.12+ con [uv](https://docs.astral.sh/uv/)
- Node.js 20+ con npm
- Docker y Docker Compose
- gh CLI (para PRs contra el repo público)

### Setup

```bash
make setup          # instala deps de backend + frontend + mcp + db local
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
cp infra/.env.example infra/.env
make migrate        # aplica migraciones
make backend-run    # API en http://localhost:8000
make frontend-run   # UI en http://localhost:5173
make mcp-run        # arranca el adapter MCP stdio
```

### Cómo correr los tests

```bash
make test           # corre los tres paquetes (backend/, frontend/, mcp-adapter/)
make lint           # lints los tres paquetes
```

`make help` lista todos los targets disponibles.

## Licencia

Apache 2.0. Ver [LICENSE](LICENSE).

## Links

- PRD fundacional: [`job-search-assistant.md`](./job-search-assistant.md)
- Decisiones de stack: [`STACK.md`](./STACK.md)
- Plan de hitos: [`ROADMAP.md`](./ROADMAP.md)
- Plan de remediación: [`docs/audit/PLAN.md`](./audit/PLAN.md)
- Repositorio público: https://github.com/danielCH26/asistcv