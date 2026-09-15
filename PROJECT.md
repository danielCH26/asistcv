# AsistCV

Asistente agéntico de búsqueda de empleo. Analiza descripciones de puesto contra el perfil del usuario, adapta el CV y redacta el primer mensaje para los puestos que valen la pena, y trackea el pipeline de aplicaciones. El sistema nunca envía nada sin aprobación humana.

## TL;DR

AsistCV es una herramienta personal que ayuda a aplicar mejor a los 5-10 puestos que valen la pena, en lugar de auto-aplicar a 100. La audiencia primaria es el propio autor durante su búsqueda de empleo; las audiencias secundarias son desarrolladores Latam que aplican a empresas US/EU, personas en transición de carrera y pequeños equipos de recruiting.

Fase actual: **Sprint 0 cerrado en local, migración a stack free tier en curso**. Documentación fundacional, stack y roadmap están publicados; el backend FastAPI, las migraciones Alembic, el mock LLM y el adapter MCP están operativos contra Postgres local con pgvector. El próximo paso es cerrar la migración al stack free tier (Neon, HuggingFace Spaces, Cloudflare Pages, Groq, HF Inference, GitHub Actions) y arrancar el Slice 1 (Match JD ↔ Perfil).

## El problema

Buscar trabajo hoy es un trabajo en sí mismo, y está roto en varios sentidos:

- **El volumen mata la calidad.** Hay más ofertas abiertas que nunca, pero el formato es inconsistente: cada empresa describe el mismo puesto de 10 formas distintas. Leer 30 JDs para encontrar 5 buenos candidatos es una jornada entera.
- **Adaptar el CV se hace mal.** Cambiar tres palabras clave y rezar no alcanza: los sistemas ATS lo descartan y el reclutador nota que es genérico. Adaptar de verdad toma una energía que no se tiene cuando se llevan 20 aplicaciones.
- **El primer mensaje se decide en frío.** Un mail genérico se ignora. Uno personalizado, breve, con contexto de la empresa, consigue respuestas. Pero escribirlos lleva tiempo que se agota rápido.
- **El seguimiento se pierde.** Sin registro de a quién se le escribió, cuándo y qué respondió, se pierden oportunidades y se duplican esfuerzos.

Para alguien que busca trabajo en serio (3-6 meses), esto son 100+ horas de trabajo mecánico que podrían enfocarse en preparar entrevistas, aprender o descansar. Y aun así, el resultado suele ser peor que si cada aplicación tuviera 30 minutos de cuidado.

## La solución

Tres capacidades que el producto entrega, en orden de uso natural: primero evaluar, después adaptar, al final trackear.

### Match JD ↔ Perfil

El usuario pega una descripción de puesto (texto o link) y el sistema devuelve en segundos un score honesto de match contra su perfil, las razones del score (skills que encajan, skills que faltan, cosas aprendibles rápido), y una recomendación de cuánta energía vale la pena invertir (alto / medio / bajo). No es un "sí o no" binario: es una segunda opinión informada para decidir mejor. La integración crítica es LLM + embeddings + perfil persistido en Postgres con pgvector.

### Adaptar CV + Outreach

Para los puestos que pasan el filtro anterior, el sistema reescribe los bullets relevantes del CV para resaltar la experiencia que el puesto pide y redacta un primer mensaje (al reclutador o al hiring manager) con tono configurable. El usuario revisa y aprueba antes de mandar nada; el sistema nunca envía nada por su cuenta. La restricción explícita es reorganizar y resaltar lo que el usuario ya tiene: jamás inventa skills o logros.

### Tracking Pipeline

Una vez enviadas las aplicaciones, queda todo registrado en un panel personal: aplicaciones, status, fechas de envío, respuesta y seguimiento, próximos pasos. El sistema recuerda cuándo hacer follow-up y qué se aprendió de cada interacción. Cierra el ciclo de uso y vuelve medibles las métricas del proyecto.

## Lo que NO es

El espacio está lleno de herramientas con propuestas similares y problemas diferentes. Los anti-patrones explícitos del proyecto:

- **No es un auto-applier.** No manda 100 CVs sin supervisión. Eso es spam, daña la reputación a largo plazo y los reclutadores lo detectan.
- **No inventa experiencia.** No genera skills o logros que el usuario no tenga. Parte del CV real y solo reorganiza y resalta.
- **No es un chatbot mágico** estilo "consigue tu trabajo soñado con IA". Es una herramienta de trabajo que se gana su lugar ahorrando tiempo real.
- **No reemplaza el trabajo humano.** Automatiza el 70% mecánico; el 30% estratégico (buscar, entrevistar, decidir) sigue siendo del usuario.

## Estado del proyecto

### Contexto del stack

El stack original estaba diseñado sobre GCP completo (Cloud Run, Cloud SQL, Vertex AI, Cloud Build, Secret Manager), pero requiere tarjeta de crédito para habilitar billing, lo que bloquea el deploy. En septiembre de 2026 se migró a un stack 100% free tier — Cloudflare Pages, HuggingFace Spaces, Neon, Groq, HuggingFace Inference API, GitHub Actions — sin cambios en los frameworks (FastAPI, SvelteKit, pgvector, SDK `mcp`) y manteniendo las mismas decisiones de diseño. Detalle en [`STACK.md`](./STACK.md).

### Hitos

- [x] Documento fundacional ([`job-search-assistant.md`](./job-search-assistant.md))
- [x] Stack tecnológico definido ([`STACK.md`](./STACK.md))
- [x] Roadmap ([`ROADMAP.md`](./ROADMAP.md))
- [x] Repo público en GitHub (https://github.com/danielCH26/asistcv)
- [x] Estructura SDD inicializada ([`openspec/`](./openspec/))
- [x] Monorepo con `backend/`, `frontend/`, `mcp-adapter/`, `infra/`
- [x] Backend FastAPI con healthcheck, settings, logging estructurado y `LLMProvider` (mock + factory)
- [x] Alembic + SQLModel operativos contra Postgres local con pgvector (docker-compose)
- [x] Adapter MCP stdio con tools `ping` y `evaluate_match`
- [ ] Reescribir backend: settings + clientes LLM (Groq) y embeddings (HF Inference API); agregar `groq` y `httpx` (ya presente) a `pyproject.toml`
- [ ] Provisionar Neon Postgres + pgvector y migrar schema
- [ ] CI/CD con GitHub Actions (build + deploy a HF Spaces y Cloudflare Pages)
- [ ] Deploy backend en HuggingFace Spaces
- [ ] Deploy frontend en Cloudflare Pages
- [ ] Validación end-to-end con credenciales reales (Groq, HF, Neon)
- [ ] Proposal, specs, design e implementación del Slice 1

## Stack tecnológico (resumen)

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

Costo estimado total: **$0 / mes**, sin tarjeta de crédito requerida. Decisiones completas, con justificación y alternativas descartadas, en [`STACK.md`](./STACK.md).

## Roadmap (resumen)

| Slice | Capacidad | Estado |
|---|---|---|
| Sprint 0 — Fundación técnica | Backend, mock LLM, Alembic, MCP adapter | Cerrado en local |
| Migración a free tier | Settings + clients + deploy en HF / Cloudflare / Neon | En curso |
| 1 | Match JD ↔ Perfil | Pendiente (próximo, depende de la migración) |
| 2 | Adaptar CV + Outreach | Pendiente (depende de Slice 1) |
| 3 | Tracking Pipeline | Pendiente (depende de Slice 2) |

El orden sigue el flujo natural de uso: primero evaluar para decidir, después adaptar el material, al final trackear lo que se mandó. Detalle de scope, métricas y criterios de éxito de cada slice en [`ROADMAP.md`](./ROADMAP.md).

## Métricas de éxito

Las métricas vienen del documento fundacional. Las primarias son criterio de éxito del proyecto; las secundarias se miden cuando es posible sin fricción adicional.

### Primarias

| Métrica | Objetivo |
|---|---|
| Aplicaciones procesadas con el sistema | 30 o más |
| Coincidencia match del sistema vs decisión humana | 80% o más |
| Tiempo mediano de evaluación de un JD | 15 min → 2 min |
| Entrevistas atribuibles a CV/mensaje adaptado | 3 o más |

### Secundarias

| Métrica | Objetivo |
|---|---|
| Costo por aplicación procesada | Dentro del presupuesto ($0 / mes, free tier) |
| Latencia mediana de `POST /jobs/evaluate` | Por debajo de 30 segundos |
| Tasa de respuestas positivas | Medida y registrada |
| Calidad de CV adaptado | Evaluación con panel de 3-5 personas |

## Estructura del repositorio

```
asistcv/
├── job-search-assistant.md    # PRD fundacional (problema, solución, anti-patrones)
├── PROJECT.md                  # este archivo
├── ROADMAP.md                  # plan de slices con scope, métricas y criterios
├── STACK.md                    # decisiones arquitectónicas cerradas y abiertas
├── README.md                   # quick start
├── Makefile                    # tareas de dev local
├── openspec/                   # artifacts del flujo SDD
│   ├── config.yaml             # configuración del proyecto OpenSpec
│   ├── specs/                  # specs principales (se llena con el Slice 1)
│   └── changes/                # proposals de cambio (uno por slice)
├── backend/                    # FastAPI service (deploy a HuggingFace Spaces)
├── frontend/                   # SvelteKit app (deploy a Cloudflare Pages)
├── mcp-adapter/                # SDK `mcp` en Python, corre local
└── infra/                      # docker-compose local, scripts de deploy
```

## Desarrollo local

El desarrollo local es independiente del deploy: docker-compose levanta Postgres con pgvector, el backend corre con `LLM_PROVIDER=mock` sin credenciales, y el frontend con `npm run dev`. El deploy corre sobre GitHub Actions y se describe en [`STACK.md`](./STACK.md).

### Prerequisitos

- Python 3.12
- Node 20+
- Docker y Docker Compose
- gh CLI (para PRs contra el repo público)

### Setup

```bash
make setup          # instala deps de backend y frontend
make db-up          # levanta Postgres con pgvector en docker-compose
make backend-run    # API en http://localhost:8000
make frontend-run   # UI en http://localhost:5173
make mcp-run        # arranca el adapter MCP stdio
```

### Cómo correr el backend

`make backend-run` (o `cd backend && uv run uvicorn app.main:app --reload`). Con `LLM_PROVIDER=mock` no hace falta credencial de LLM; los providers reales (Groq, HF Inference) se activan por env vars cuando llega el momento del deploy.

### Cómo correr el frontend

`make frontend-run` (o `cd frontend && npm run dev`).

### Cómo correr el MCP adapter

`make mcp-run` (o `cd mcp-adapter && uv run asistcv-mcp`). Conectable desde Claude Desktop o Cursor; apunta al backend local por defecto.

### Cómo correr los tests

`make test` corre los tres paquetes (`backend/`, `frontend/`, `mcp-adapter/`) según los targets disponibles.

## Licencia

**TBD.** Decisión pendiente del dueño del proyecto.

Candidatos a evaluar cuando se cierre la decisión: MIT, Apache 2.0, AGPL. Consideraciones relevantes (impacto en el uso comercial del código, obligación de compartir modificaciones, compatibilidad con el resto del stack) pueden documentarse en [`STACK.md`](./STACK.md) si aplica.

## Links

- PRD fundacional: [`job-search-assistant.md`](./job-search-assistant.md)
- Decisiones de stack: [`STACK.md`](./STACK.md)
- Plan de slices: [`ROADMAP.md`](./ROADMAP.md)
- Repositorio público: https://github.com/danielCH26/asistcv