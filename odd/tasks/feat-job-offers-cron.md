# Feature: Cron de ofertas de empleo (#55) — v2.0 slice 1

## Decisión de diseño principal

**Lazy catch-up cron** en lugar de APScheduler puro: Render free DUERME tras 15 min de inactividad — un scheduler in-process muere con el sleep y un cron de 24h jamás dispararía. El diseño que sobrevive: al despertar la app (lifespan startup) y en cada actividad del usuario, si el `last_offer_run_at` del usuario es más viejo que su frecuencia configurada, corre el job ahora. Sin dependencia nueva, sin pings externos. APScheduler entra recién con múltiples instancias (pagar Render).

## Specs

> **S1**: Migración `027`: tabla `job_offers` (id, owner_user_id FK users, title, company, url, snippet, published_date, score, status: new|archived, search_query, created_at) **con RLS habilitado desde el día uno** (patrón 023: enable RLS + policy owner_user_id = current). Columna JSONB `offer_preferences` en `users` (frequency_hours default 24, top_n default 5, filters: remote/location/salary).

> **S2**: Tavily search client en el backend (puerto del patrón del MCP adapter `search_client.py`: Tavily POST con api_key en body, taxonomía de errores tipada SearchError/SearchAuthError/SearchRateLimitError, published_date str|None).

> **S3**: Worker `run_offer_search(user)`: lee perfil + preferencias → construye query de búsqueda (template con skills del perfil; LLM opcional después) → Tavily → rankea contra el perfil (embedding Gemini del snippet + cosine vs perfil — reusa el pipeline) → persiste nuevas ofertas (dedupe por URL) → actualiza `last_offer_run_at`. Logs estructurados por corrida.

> **S4**: Endpoints: `POST /v1/job-offers/run` (dispara manualmente el job del usuario — el catch-up automático lo llama también), `GET /v1/job-offers` (lista paginada con filtro status), `POST /v1/job-offers/{id}/archive`. Preferencias: `PUT /v1/me/offer-preferences`.

> **S5**: Catch-up automático en el lifespan startup: para usuarios activos con preferencias y `last_offer_run_at` stale → encola el job. Fire-and-forget con timeout; nunca bloquea el startup.

> **S6**: Email resumen (Resend, el servicio existe): formato resumen con top N ofertas nuevas. Configurable daily/weekly via preferencias (email_frequency: none|daily|weekly).

> **S7**: UI mínima en frontend: sección "Ofertas para vos" en /profile (o página propia /job-offers): lista con title/company/score/link out/archive.

> **S8**: Tests: unitarios del client (httpx mock), del worker (dedupe, ranking, stale logic), de endpoints (auth + RLS), migración 027. CI verde.

## Fuera de alcance de este slice

- LLM para refinar queries (el template con skills basta para v1)
- JD bookmarks (no existen en el schema; el perfil + preferencias bastan)
- Integración directa con job boards (LinkedIn/Indeed TOS — Tavily genérico primero)
- Config de rango salarial (el JSONB filters lo permite después)

## Criterio de aceptación (del issue, mapeado a este slice)

- [ ] Usuario activa el cron desde /profile con preferencias (S4/S7)
- [ ] El job corre on catch-up y persiste ofertas nuevas en job_offers (S3/S5)
- [ ] Endpoint /v1/job-offers lista con paginación (S4)
- [ ] Email resumen (S6)
- [ ] UI básica (S7)
- [ ] Tests de integración del job (S8)
- [ ] Logs estructurados por corrida (S3)

## Tasks

> **T1**: Migración 027 (job_offers + RLS + offer_preferences JSONB) + models.py

> **T2**: Tavily client backend (test-first, httpx mock)

> **T3**: Worker run_offer_search (test-first: dedupe, stale, ranking)

> **T4**: Endpoints job-offers + preferencias

> **T5**: Catch-up en lifespan startup

> **T6**: Email resumen (Resend)

> **T7**: UI mínima frontend

> **T8**: ✅ PR #107 mergeada (4f24d0b) — CI 7/7 verde (backend 4m49s). Issue #55 CLOSED. Fix de reversibilidad: el downgrade de 027 dropea la tabla (preservarla rompía el ciclo reversible de 002).

## Log

- L1: Usuario eligió #55 ("Cron de ofertas") como próximo trabajo — "es un sprint, no un parche", se planifica por slices
- L2: web_search (#59) ya existe en el MCP adapter con Tavily; el backend necesita su propio client (misma API, otra base/autenticación pattern documentado)
- L3: Tavily free tier ~1000 créditos/mes sin tarjeta — 1 crédito por búsqueda; un usuario a 24h = ~30/mes
- L5: QA en prod del cron completo (2026-10-09/18): migración 027 aplicada, endpoints 200, catch-up automático CORRIÓ solo al reiniciar el backend (validación del diseño lazy en prod), run manual forzado con #111 (found:10, new_offers:10 persistidas), dedupe por URL verificado
- L6: Fix de QA: las ofertas persistían con score NULL (_rank_results computaba el score pero lo dropeaba al devolver) — PR #112 mergeada (28e4a5e): los pares (score, resultado) fluyen hasta la persistencia; el fallback degradado persiste score=None visiblemente. Las 10 ofertas previas quedaron con score NULL (datos viejos); las nuevas traen score
- L7: Limitación conocida del enfoque genérico (Tavily web search): los resultados son PÁGINAS de portales (remote.co, LinkedIn search, Reddit), no ofertas individuales — el issue lo anticipaba ("adapter por board si el genérico no es suficiente"). Slice 2: query refinada con LLM o adapters por board

## Slice 2: calidad de resultados (2026-10)

- L8: El QA en prod mostró la limitación del enfoque genérico: Tavily devuelve PÁGINAS de portales (remote.co, LinkedIn search, Reddit), no ofertas individuales. El score de ranking las dejó pasar (cosine alto por keywords remotas).
- L9: Tavily soporta include_domains — restringir a job boards es el fix más barato y determinista.

> **T9**: Calidad de búsqueda en el worker: (a) include_domains con job boards desde settings (OFFER_SEARCH_INCLUDE_DOMAINS, default linkedin.com/jobs, indeed.com, computrabajo.com.co, occtalent.com), (b) LLM refina la query desde los skills del perfil (Groq, detrás de OFFER_SEARCH_LLM_QUERY default true si hay groq), (c) clasificación LLM de resultados (descarta lo que no sea oferta individual). Test-first con mocks.

> **T10**: UI: selects de ubicación/remoto y rango salarial en las preferencias (el JSONB filters ya existe).

> **T11**: Suite + PR.
- L10: Slice 2 COMPLETO — PR #114 mergeada (CI 7/7): include_domains (job boards), query refinada con LLM (Groq, prompt sin inventar skills, fallback al template), clasificación LLM de resultados (descarta portales/artículos/reddit, fallback keep-all), LLMProvider.generate_structured (Groq lo implementa, Gemini/HF stub), filtros estructurados en preferencias (remote_only/location/salary_min con 422 matrix) + UI Modalidad/Ubicación/Salario. 3 settings nuevos documentados en .env.example.
