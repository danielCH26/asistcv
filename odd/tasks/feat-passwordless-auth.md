# Feature: Passwordless auth (email + código) sin Clerk

Estado: EN PROGRESO — rama `feat/passwordless-auth` (worktree `asistcv-wt-auth`, base `origin/main` = `6c74769`).

## Objetivo

Reemplazar Clerk por auth propia passwordless (email + código de 6 dígitos) para desbloquear el signup/login en producción (`asistcv-frontend.pages.dev`) sin dominio propio. Email transaccional vía proveedor sin dominio (Brevo 300/día o SendGrid 100/día, remitente único verificado) con adaptador común y dev-fallback por consola.

## Decisiones

1. **Passwordless only** (spec original). Sin contraseñas en v1; `users.password_hash` ya es nullable en origin/main. Botón Google: fase 2.
2. **Sesión = token pair HS256 legacy** (access 15 min + refresh 30 días con rotación) — se recupera `security.py`/`deps.py` de `1857a9e` (merge-base, contenido completo en el historial).
3. **Código OTP**: tabla nueva `auth_email_codes` (migración 021), SHA256 del código, TTL 10 min, un solo uso, máx 5 intentos, throttle por email (60 s) y tope por IP/hora, respuesta genérica (sin enumeración de usuarios).
4. **Email provider**: `email_service.py` (ya en main, httpx, fallback silencioso) se extiende con proveedor `brevo` + `console` (dev). `EMAIL_PROVIDER` selecciona. SendGrid queda como segundo adaptador si hace falta.
5. **Clerk queda fuera del camino de código nuevo**: `deps.py` vuelve a two-path legacy (JWT + API key). Las env vars CLERK_* en Render quedan inertes; limpieza posterior.
6. **Cloudflare build**: `check-env.mjs` deja de exigir `PUBLIC_CLERK_PUBLISHABLE_KEY`.
7. El flujo verify-email por LINK queda obsoleto (el passwordless verifica al primer login); la tabla `email_verification_tokens` se conserva, sin endpoints nuevos.

## Tareas

- [x] **S1a — Backend base**: recuperar `security.py` + `deps.py` two-path (con `bind_rls_context` y compat `billing.py:207`); migración 021 `auth_email_codes`; config (`brevo_api_key`, `email_code_ttl_seconds`, `email_code_max_attempts`); tests.
- [x] **S1b — Endpoints OTP**: servicio de códigos (create/verify + límites) + router `auth.py` v2 (`POST /auth/email-code/request`, `POST /auth/email-code/verify`, `/auth/refresh`, `/auth/logout`, `GET /auth/me`) + proveedor `brevo` en `email_service.py` + tests RED→GREEN.
- [ ] **S2 — Frontend**: `client.ts`/`session.ts` nativos (de `1857a9e`), páginas login/signup passwordless (email → código), guards, logout, `check-env.mjs` sin Clerk, tests vitest.
- [ ] **S3 — QA local**: E2E con navegador (pedir código → ver código en log/consola → entrar → `/v1/auth/me` → logout) + `svelte-check` + suites backend/frontend.
- [ ] **S4 — Deploy + E2E prod**: commit/merge (decisión usuario), Render (nuevas env vars EMAIL_*, CORS con pages.dev; CLERK_* inertes), Cloudflare rebuild, E2E en producción.

## Evidencia

- Mapa de exploración (subagent mvqe0poa-1-xx5d): legacy auth completo en `1857a9e`; `email_service.py` + migración `020_email_verification_tokens` + tests ya en `origin/main`; frontend en origin/main = versión Clerk (worktree `asistcv-wt-clerk`).
- Verificación directa: `auth.py`/`security.py`/`test_auth.py` NO en `origin/main`; `deps.py` sin path legacy JWT; merge-base local/origin = `1857a9e` (local sin contenido único).

## Commits

- f978485 feat(auth): restore native JWT auth base and add email-code data layer (S1a; 39 tests passed)
- f978485 feat(auth): restore native JWT auth base and add email-code data layer (S1a; 39 tests passed)
- (S1b: commit propio — endpoints email-code, proveedor Brevo+console, 11+4 tests; suite completa 786+ verde)
