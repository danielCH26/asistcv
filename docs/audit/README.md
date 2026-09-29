# Auditoría de código — AsistCV

**Fecha:** 2026-09-29
**Alcance:** backend FastAPI (Python 3.12), servicios + integración LLM, frontend SvelteKit, adapter MCP, CI e infraestructura.
**Método:** tres sub-agentes mapper de solo lectura mapeando en paralelo las cuatro áreas, más una re-verificación del orquestador sobre los hallazgos principales leyendo el código directamente (no confiando en el resumen de los mappers).

> **Alcance de la evidencia.** Los hallazgos son **análisis estático** obtenidos leyendo el código; cada referencia `file:line` fue verificada leyendo el archivo.
>
> **⚠️ Excepción — S1 fue REPRODUCIDO contra el despliegue real.** El backend está desplegado en `https://asistcv-backend.onrender.com` y se verificó que acepta access tokens firmados con la clave de firma por defecto publicada en el repo. Ver [Verificación en producción](#verificación-en-producción). El resto de los hallazgos sigue siendo **no reproducido**: un hallazgo "verificado por línea" requiere reproducirlo (o su test) antes de cerrar el fix.

---

## Verificación en producción (2026-09-29)

**Topología de despliegue (confirmada con el maintainer y verificada contra el repo):**

| Componente | Dónde | Nota |
|---|---|---|
| Backend (FastAPI) | **Render** — `https://asistcv-backend.onrender.com` | Free tier, cold start ~31s |
| Frontend (SvelteKit SPA) | **Cloudflare Pages** — `https://asistcv-frontend.pages.dev` | Export estático, `ssr=false` |
| Base de datos | Neon (Postgres + pgvector) | |
| LLM / Embeddings | Groq / HuggingFace Inference | |

> **Drift adicional:** `STACK.md:27/35/45` sigue describiendo el frontend en Cloudflare Pages ✅ pero también afirma que el backend está en **HuggingFace Spaces** (`STACK.md:27`), cuando el deploy real es **Render**. La topología de frontend sí coincide con los docs; la de backend no.

El backend está **live** en `https://asistcv-backend.onrender.com`. Se verificó su configuración de auth de forma pasiva y con un probe dirigido:

| Chequeo | Resultado | Conclusión |
|---|---|---|
| `GET /health` | `200` (31.7s) | Backend desplegado y operativo |
| `GET /docs` | `404` | `BACKEND_API_KEY` **sí** está seteada — `main.py:51` desactiva OpenAPI cuando existe |
| `GET /openapi.json` | `404` | Confirma lo anterior |
| `GET /v1/ping` | `401` | Modo protegido activo, la API key se valida |
| `GET /v1/billing/plans` | `200` | Correcto, público por diseño |

**Consecuencia para los hallazgos de Fase 0:**

- **S2 (modo abierto) — MITIGADO en producción por configuración.** La key existe, así que `optional_auth` no devuelve el service super-principal a requests anónimos. S2 sigue siendo un bug de diseño (y un riesgo de deploy futuro si alguien quita la key), pero **no está explotado hoy**.
- **S1 (`jwt_secret` default público) — CONFIRMADO EXPLOTADO EN PRODUCCIÓN.** Se firmó un access token con `dev-secret-change-in-production` y el backend lo aceptó, devolviendo datos reales del usuario `id=1`. Esto es independiente de `BACKEND_API_KEY`: son variables separadas, y la key de la API puede estar correctamente seteada mientras el secreto JWT sigue con el default del repo.
- **S3 (IDOR en `claim_audit`) — sigue siendo explotable.** El endpoint no tiene autenticación y no depende de la API key para el body. Con la key seteada, el funnel anónimo sigue accesible por diseño, y `claim_audit` sigue sin validar al caller.
- **S4 (router duplicado) — sigue presente**, cada ruta del funnel existe en dos paths.

**Acción inmediata recomendada, por orden:**

1. **Rotar `JWT_SECRET` en Render inmediatamente** (invalida todos los tokens firmados con la clave pública) y agregar la guarda de fail-closed (S1 fix) para que no vuelva a pasar.
2. Verificar/corregir S3 (`claim_audit` sin auth) — sigue abierto.
3. Tratar S2 como hardening de diseño, no como urgencia operativa.

---

## El hallazgo de fondo: el código va muy por delante de su propia documentación

Este es el resultado más importante de la auditoría, y condiciona todo lo demás.

`PROJECT.md` y `STACK.md` describen una **herramienta personal, sin autenticación, single-user**. El código implementa un **SaaS multi-tenant con billing**:

| Lo que dicen los docs | Lo que hace el código |
|---|---|
| Herramienta personal, el autor es el único usuario | Cuentas con email, password hasheado, refresh tokens |
| Sin auth | `JWT_SECRET` + access/refresh tokens, middleware de auth, roles `job_seeker` / `recruiter` / `service` |
| Sin monetización | Billing de Stripe: checkout, portal, webhooks, 4 `STRIPE_PRICE_*` |
| Sin aislamiento de datos | Row-Level Security en Postgres (migraciones `011`, `016`) |
| Sin multiusuario | Embudo de auditoría anónimo + funil recruiter con consent gate |
| Sin límites de uso | Tier limits con contadores de uso por plan |

La documentación describe **un producto que ya no existe**. Eso importa por dos razones distintas: (a) cualquiera que lea `README.md` / `PROJECT.md` para operar o contributorar el sistema toma decisiones sobre supuestos falsos, y (b) el equipo tiende a evaluar el código contra un producto que no está implementado, lo que produce falsos positivos y falsos negativos por igual. **Corregir el drift documental es parte del plan, no un extra** (Fase 3), pero el drift no exime de los hallazgos: el código es lo que está desplegado.

---

## Plan de ataque

Cuatro fases, ordenadas por *blast radius decreciente y dependencia ascendente*. El orden no es por severidad individual: es por **radio de daño**. Un error de auth (Fase 0) invalida cualquier test que escribamos sobre las fases siguientes; un bug funcional (Fase 1) se reproduce sobre un backend que ya no es explotable.

### Fase 0 — Seguridad (P0, hacer primero)

- **Objetivo:** cerrar la superficie de acceso antes de tocar nada más. Nada de lo que sigue es confiable mientras un atacante pueda obtener un `CurrentUser` arbitrario.
- **Por qué va primera:** los hallazgos S1 y S2 son *precondiciones* de la corrección de todos los demás. Un test de RLS per-user escrito hoy corre contra un backend donde el modo abierto devuelve `role="service"`; un test de billing escrito hoy pasa mientras el `AttributeError` esté tragado por el override del fixture.
- **Hallazgos:** S1 (`jwt_secret` con default público), S2 (modo abierto devuelve un service super-principal), S3 (IDOR en claim de audit), S4 (router duplicado + kill-switch incompleto).
- **Blast radius:** auth completa, aislamiento multiusuario, superficie pública de auditoría, feature flag de adaptaciones.
- **Hecho cuando:** ningún endpoint devuelve datos de otro usuario; ningún token es firmable sin secreto conocido por el operador; el `claim_audit` exige caller autenticado y usa `current_user.id`; cada endpoint del funnel de audit existe en exactamente un path; el kill-switch corta también las lecturas.

### Fase 1 — Bugs funcionales que rompen features (P0/P1)

- **Objetivo:** hacer que las features que el producto promete funcionen de punta a punta.
- **Por qué va segunda:** presupone la Fase 0 (F1 toca el mismo módulo de auth que S1; F3 toca RLS que S2 expone). Es más barata de corregir sobre una base segura.
- **Hallazgos:** F1 (billing 500: `CurrentUser` no tiene `email` / `email_verified_at`), F2 (el audit "CV vs JD" nunca manda el CV al LLM), F3 (la cuota de adaptaciones nunca se consume).
- **Blast radius:** checkout de Stripe, verificación de email, el score del funnel público de auditoría, límites de plan pago.
- **Hecho cuando:** un usuario verificado puede comprar un plan; un audit con CV distintivo refleja ese CV en el score; N adaptaciones incrementan `adaptations_used` en N y el tope de un plan pago se hace cumplir.

### Fase 2 — Honestidad del LLM + deuda de tests/CI (P1)

- **Objetivo:** que la promesa central del producto (*"jamás inventa skills o logros"*) sea una garantía y no un eslogan, y que exista una red que detecte regresiones.
- **Por qué va tercera:** L1 es la mayor riesgo de **reputación** del producto, pero no es una vulnerabilidad ni rompe un flujo — se puede endurecer sin bloquear a nadie. La deuda de tests/CI (T1) es la condición para que las fases 0 y 1 no se pudran: sin tests de frontend en CI y con el hook global de RLS, cualquier fix que hagamos puede revertirse en silencio.
- **Hallazgos:** L1 (validación léxica, los números nunca se verifican) + T1 (CI no corre tests de frontend, el path RLS per-user nunca se ejercita, sin `permissions:`).
- **Blast radius:** integridad del output del LLM, capacidad de detección de regresiones.
- **Hecho cuando:** una adaptación que inventa `"40% revenue growth"` ausente del CV fuente es **rechazada**; una que reutiliza métricas reales pasa; CI falla si un test de frontend se rompe; existe un test de aislamiento RLS per-user vía el DI real.

### Fase 3 — Docs, stubs y deuda menor (P2)

- **Objetivo:** que la documentación describa el producto real y que el andamiaje que promete funcionar funcione.
- **Por qué va última:** es deuda de mantenimiento, no riesgo de datos. Pero es la fase que más rápido se desincroniza si no se hace al final, una vez congelado el comportamiento real.
- **Hallazgos:** drift de docs (README/STACK/PROJECT/ROADMAP describen pre-auth SaaS en GCP; el código es SaaS en Render), `Makefile` con `setup`/`test`/`lint`/`deploy` como stubs TODO que el README documenta como funcionales, `infra/README.md` describiendo infraestructura inexistente, código muerto.
- **Blast radius:** experiencia de quien llega al repo, tiempo del siguiente que hace onboarding, y confianza en el resto de la documentación.
- **Hecho cuando:** alguien que llega al repo por primera vez puede hacer setup y deploy siguiendo los documentos sin descubrir stubs; Outreach y Tracking Pipeline o existen o están explícitamente fuera de scope.

---

## Leyenda de severidad

| Nivel | Significado | Criterio |
|---|---|---|
| **P0** | Seguridad o feature core rota | Acceso indebido a datos, IDOR, bypass de auth; o una feature anunciada que no se puede comprar / no funciona en absoluto |
| **P1** | Correctness / integridad | Datos falsos, límites no aplicados, RLS que no se aplica post-commit, silent exceptions |
| **P2** | Mantenibilidad / deuda | Docs desincronizados, stubs, código muerto, deuda de CI |
| **P3** | Cosmético | Duplicación de mapas de i18n, naming, mensajes sin traducir |

---

## Cómo usar este documento

- **Cada hallazgo tiene un ID estable** (`S*` seguridad, `F*` funcional, `L*` LLM/honestidad, `T*` test/CI, `A*` apéndice). Citalo por ID en issues, PRs y cambios de OpenSpec; los IDs no se renumeran.
- **La evidencia es `file:line`**, no párrafos. Un fix se acepta cuando la referencia deja de describir el problema, y eso se comprueba releyendo la línea.
- **Cada fix debería terminar como un cambio SDD** bajo `openspec/changes/`, no como un commit suelto — ver [`plantilla-cambio.md`](./plantilla-cambio.md). Este directorio **no** es un artefacto SDD a propósito: es el conocimiento que *informa* esos cambios, no el lugar donde viven.
- **Archivos de este set:**
  - [`README.md`](./README.md) — este índice y el plan de ataque.
  - [`00-hallazgos.md`](./00-hallazgos.md) — los hallazgos del plan en profundidad: 9 detallados + 3 de Fase 3 resumidos.
  - [`90-catalogo-completo.md`](./90-catalogo-completo.md) — apéndice con el resto de los hallazgos, en tabla.
  - [`plantilla-cambio.md`](./plantilla-cambio.md) — plantilla para abrir un cambio SDD desde un hallazgo.

## Índice de hallazgos del plan

| ID | Título | Severidad | Fase | Estado en producción |
|---|---|---|---|---|
| S1 | `jwt_secret` con default público y sin guarda | P0 | 0 | 🔴 **CONFIRMADO EXPLOTADO** — acepta tokens firmados con la clave del repo |
| S2 | Modo abierto devuelve un service super-principal sin verificar credencial | P0 | 0 | 🟡 Mitigado por config (`BACKEND_API_KEY` seteada); sigue siendo riesgo de diseño |
| S3 | IDOR en claim de audit (escribe cross-user, sin auth) | P0 | 0 | 🔴 Sigue explotable (sin auth, independiente de la key) |
| S4 | Router de audit montado dos veces + kill-switch incompleto | P0 | 0 | 🟠 Sigue presente (cada ruta en dos paths) |
| F1 | Billing checkout/portal 500: lee atributos que `CurrentUser` no tiene | P0 | 1 | Sin verificar en prod |
| F2 | El audit "CV vs JD" nunca manda el CV al LLM | P0 | 1 | Sin verificar en prod |
| F3 | La cuota de adaptaciones nunca se consume (RLS GUC no bindeado) | P1 | 1 | Sin verificar en prod |
| L1 | "Nunca inventa experiencia" se cumple solo léxicamente | P1 | 2 | Sin verificar en prod |
| T1 | CI no corre tests de frontend; el path RLS/auth nunca se ejercita | P1 | 2 | Sin verificar en prod |
| D1 | Drift documental: los docs describen un producto que no existe | P2 | 3 | n/a |
| D2 | `Makefile` con stubs documentados como funcionales | P2 | 3 | n/a |
| D3 | Código muerto acumulado | P2 | 3 | n/a |

Los nueve primeros están desarrollados en profundidad en [`00-hallazgos.md`](./00-hallazgos.md). D1–D3 se resumen ahí y su detalle vive en el catálogo, porque son deuda de mantenimiento y no riesgo. El resto de la auditoría (~90 hallazgos) está en [`90-catalogo-completo.md`](./90-catalogo-completo.md).
