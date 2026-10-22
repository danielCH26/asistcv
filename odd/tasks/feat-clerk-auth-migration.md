# Feature: Migración de auth a Clerk (passwordless)

## Contexto

Resend no está enviando ningún email (ni confirmaciones de correo ni resúmenes del cron de ofertas) — el flujo de verificación queda inservible. Decisión del usuario: migrar login y autenticación a **Clerk**, que gestiona el envío de códigos nativamente.

## Decisiones de diseño (del usuario, 2026)

1. **Passwordless por código de email** — sin contraseñas; Clerk envía el código de 6 dígitos.
2. **Fresh start** — sin script de migración de usuarios; los usuarios existentes se re-registran en Clerk.
3. **Componentes de Clerk** — `<SignIn/>` / `<SignUp/>` prebuilt con appearance teal + localization es/en.
4. Resend roto por completo → el email de ofertas del cron queda como **issue aparte** (Clerk no envía emails de cron).

## Decisión técnica clave: SDK

`svelte-clerk` 1.x exige `svelte ^5.29` (proyecto usa Svelte 4.2.19) → **NO**. Se usa **`@clerk/clerk-js` vanilla** (SDK oficial, framework-agnostic):

- `new Clerk(pk)` + `await clerk.load()` en el layout raíz (SPA ssr=false, sin hooks.server).
- `clerk.mountSignIn(el)` / `clerk.mountSignUp(el)` en /login y /signup.
- Token por request: `await clerk.session?.getToken()` → `Authorization: Bearer` al backend (reemplaza access+refresh rotation; los session tokens de Clerk viven ~60s y se renuevan solos).
- `@clerk/localizations` → `esES` en `clerk.load()`.

## Arquitectura backend

- **`app/services/clerk_auth.py`**: verifica el session JWT de Clerk — firma RS256 vía JWKS (`https://{CLERK_DOMAIN}/.well-known/jwks.json`, cache en memoria por `kid`, re-fetch en `kid` desconocido), `exp`, `azp` contra orígenes autorizados. Extrae `sub` (`user_...`).
- **`deps.py get_current_user`**: Clerk JWT → local user por `users.clerk_id`. **Auto-provisioning on miss**: `GET /v1/users/{id}` con `CLERK_SECRET_KEY` → crea fila local (email, verified, nombre, avatar, role: `publicMetadata.role` o `job_seeker`) → RLS binding intacto. API key (MCP adapter) queda igual.
- **Webhook `POST /v1/webhooks/clerk`** (svix HMAC-SHA256 manual con stdlib, sin dep nueva): `user.updated` sincroniza perfil/verified; `user.deleted` log + conserva fila (integridad FK).
- **Migración 029**: `users.clerk_id` (nullable, unique, indexed) + `password_hash` nullable (los fresh-start no tienen contraseña).
- **Remoción del auth legacy**: endpoints `/auth/register|login|refresh|logout|verify-email/*` fuera; `RefreshToken`/`LoginAttempt`/`EmailVerificationToken` dejan de usarse (las tablas NO se dropean en este slice — decisión separada).
- Role recruiter: todo signup nuevo entra `job_seeker`; upgrade vía flujo de consent existente (post-signup, en profile).

## Specs

> **S1 — Backend core**: config (CLERK_DOMAIN, CLERK_SECRET_KEY, CLERK_WEBHOOK_SIGNING_SECRET, authorized parties), migración 029, `clerk_auth.py` (JWKS + claims), deps.py con ruta Clerk + auto-provisioning, `/users/me` intacto. Tests con JWKS mock.

> **S2 — Webhook + limpieza legacy**: endpoint webhook svix-verified, remoción de endpoints y maquinaria legacy, `main.py` sin router auth, test_auth.py reescrito. ruff + mypy + pytest verde.

> **S3 — Frontend clerk-js**: deps `@clerk/clerk-js` + `@clerk/localizations`, `lib/clerk.ts` (singleton + stores Svelte), apiClient con `getToken()`, rework de `stores/session.ts` (fuera rotation timer, sessionEvent banners), /login y /signup con mountSignIn/mountSignUp + appearance teal + esES, guards requireSession/requireRole sobre clerk state, logout → `clerk.signOut()`. Tests vitest actualizados.

> **S4 — Docs/env + cierre**: `.env.example` (backend + frontend), README (sección auth), checklist de setup del dashboard Clerk (keys, allowed origins, webhook URL), suite completa (pytest, vitest, ruff, mypy, svelte-check), issue GitHub para el email de ofertas (Resend roto).

## Fuera de alcance

- Script de migración de usuarios existentes (fresh start decidido).
- Drop de tablas legacy (users_refresh_tokens, auth_login_attempts, email_verification_tokens) — decisión separada post-verificación.
- Fix del envío de ofertas (Resend roto) — issue aparte.
- MFA / social login (Google) — se puede agregar después desde el dashboard sin código.

## Criterio de aceptación

- [ ] Login/signup con código por email vía componentes Clerk (es/teal)
- [ ] API acepta session JWT de Clerk y resuelve usuario local con RLS intacto
- [ ] Auto-provisioning: primer request post-signup crea la fila users
- [ ] Webhook svix verificado sincroniza updated/deleted
- [ ] MCP adapter (API key) sigue funcionando sin cambios
- [ ] Endpoints legacy eliminados; tests backend + frontend verdes
- [ ] Checklist de deploy (env vars en Render + Cloudflare Pages) documentado

## Tasks

> **T0**: ✅ Worktree `feat/clerk-auth-migration` desde main (protege WIP Wompi del árbol principal)

> **T1 (S1)**: ✅ Backend core Clerk (commit `116579a`) — config + migración 029 + clerk_auth.py + deps + auto-provisioning + tests

> **T2 (S2)**: ✅ Webhook svix + remoción auth legacy (commit `3d5eef1`, suite 730 passed)

> **T3 (S3)**: ✅ Frontend clerk-js (commit `fc725f9`, 129 tests + build ok) — provider, páginas, client, session store, guards + tests

> **T4 (S4)**: ✅ Docs/env + checklist deploy + issue Resend-ofertas


## Checklist de deploy (del usuario)

### 1. Dashboard de Clerk (clerk.com — cuenta nueva)
- [ ] Crear aplicación: habilitar **Email code** (passwordless) como método de primer factor
- [ ] Copiar `Publishable key` (pk_...) y `Secret key` (sk_...)
- [ ] **Allowed origins / redirect**: producción (dominio de Cloudflare Pages) + `http://localhost:5173` para dev
- [ ] **Webhooks → Add endpoint**: URL `https://<render-backend>/api/v1/webhooks/clerk`, eventos `user.created`, `user.updated`, `user.deleted`; copiar el `Signing secret` (whsec_...)
- [ ] Branding: nombre/logo AsistCV (los componentes heredan teal vía appearance)

### 2. Render (backend)
- [ ] `CLERK_PUBLISHABLE_KEY` (activa la verificación Clerk)
- [ ] `CLERK_SECRET_KEY` (habilita auto-provisioning)
- [ ] `CLERK_WEBHOOK_SIGNING_SECRET` (verificación svix)
- [ ] `CLERK_AUTHORIZED_PARTIES` = orígenes del frontend separados por coma (default: FRONTEND_URL)
- [ ] `JWT_SECRET` sigue requerido por config (legacy sin uso — se limpia al dropear tablas legacy)

### 3. Cloudflare Pages (frontend)
- [ ] `PUBLIC_CLERK_PUBLISHABLE_KEY` (build-time, adapter-static lo inlinea)

### 4. Neon (DB)
- [ ] Migración 029: `alembic upgrade head` con el `DATABASE_URL` de Render INLINE en el comando

### 5. Orden de deploy
- [ ] Backend y frontend despliegan JUNTOS (S2 es breaking: tokens legacy ya no verifican)
- [ ] Smoke test: signup con código de email → primer /users/me crea la fila → login → flujo match completo

## Estado de QA / deploy (2026-10)

- [x] PR #121 mergeado (squash `05ae8fe`), CI 7/7, issue #120 cerrado
- [x] Migración 029 aplicada en Neon (verificada: clerk_id nullable + ix_users_clerk_id, 13 usuarios intactos)
- [x] Backend en prod con código nuevo: `/v1/auth/login` → 404 (legacy fuera)
- [x] Webhook vivo en **`/api/v1/webhooks/clerk`** (prefijo /api/v1, patrón lemonsqueezy): probe sin firma → 400 MISSING_SVIX_HEADERS
- [x] Frontend en prod con build nuevo (clerk-js incluido en chunks)
- [ ] `PUBLIC_CLERK_PUBLISHABLE_KEY` inlineada en el build de Cloudflare Pages (la key tiene que aparecer en `chunks/clerk.*.js`; si el hash de ese chunk no cambia entre deploys, el build corrió sin ella)
- [ ] Webhook registrado en dashboard Clerk (URL con /api/v1)
- [ ] QA E2E: signup con código → auto-provisioning en users → login → match

## Issue aparte (Resend)
- Resend no envía NINGÚN email: las confirmaciones las resuelve Clerk, pero el resumen de ofertas del cron (#55) sigue roto → issue GitHub dedicado.
