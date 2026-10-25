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

## Informe de QA E2E (2026-10-23) — 3 bugs encontrados, todos corregidos localmente

Veredicto: **FAIL en prod**, **PASS en local** con los fixes aplicados. Nada commiteado
todavía (rama `fix/clerk-key-parser`); el deploy lo hace el usuario.

### Bug 1 — Frontend: la publishable key nunca llegaba al bundle (prod: login roto)

- `frontend/src/lib/clerk.ts` leía `mod.PUBLIC_CLERK_PUBLISHABLE_KEY` del módulo
  `$env/dynamic/public`. Ese módulo solo exporta un objeto `env`, así que la
  propiedad era **siempre `undefined`** → `Clerk keys are missing from your environment`.
- Evidencia dura: el chunk de prod `chunks/public.kW5yuSB0.js` es exactamente
  `const e=globalThis.__sveltekit_14hnqxh.env;export{e as env};` — el namespace
  nunca exporta nombres individuales. La key **sí** estaba en prod
  (`/_app/env.js` la expone), el consumo era el roto.
- Fix: `import { PUBLIC_CLERK_PUBLISHABLE_KEY } from '$env/static/public'` (inlined
  en build, mismo patrón que `src/lib/api/base.ts`).
- No usar `import.meta.env.VITE_*`: Vite solo expone prefijo `VITE_` y en
  Cloudflare Pages la variable se llama `PUBLIC_`.

### Bug 2 — Frontend: faltaba el bundle de UI de Clerk v6 (Core 3)

- `@clerk/clerk-js` 6.40.0 **no** incluye los componentes prebuilt. Sin el bundle,
  `clerk.load()` deja el renderer desconectado y `mountSignIn()` lanza
  `Clerk was not loaded with Ui components`.
- El paquete npm `@clerk/ui` es React (no sirve para Svelte). El bundle correcto es
  el standalone del CDN del Frontend API:
  `https://{fsa}/npm/@clerk/ui@1/dist/ui.browser.js`, que define
  `window.__internal_ClerkUICtor` (exactamente lo que espera `ui.ClerkUI`).
- Fix: helper `loadClerkUIBundle()` que deriva el `fsa` del publishable key
  (`atob(pk.split('_')[2]).slice(0, -1)`), inyecta el `<script>` y **espera** a que
  cargue **antes** de `clerk.load({ ui: { ClerkUI: window.__internal_ClerkUICtor } })`.

### Bug 3 — Backend: dos defectos en la verificación del session token

**3a. Issuer con barra final.** `clerk_auth.py` construía
`issuer = f"https://{fsa}/"`, pero Clerk emite el `iss` **sin** barra
(`https://immense-lamb-7783.clerk.accounts.dev`). PyJWT compara literal →
`InvalidIssuerError` → `Token issuer mismatch` → **401 `Invalid credentials`**.
Era el causa raíz del 401 en prod (verificado offline con el token real).
Fix: `issuer = f"https://{fsa}"`.

**3b. `verify_api_key` no reenviaba la sesión de DB.** La firma era
`verify_api_key(api_key_header)` y llamaba `get_current_user(api_key_header)`,
dejando el default `Depends(get_session)` (un marcador, no una sesión) en el camino
de Clerk. Cualquier request autenticado por Clerk al router `/v1/users` reventaba con
`AttributeError: 'Depends' object has no attribute 'execute'` → **HTTP 500**.
Fix: inyectar `db: AsyncSession = Depends(get_session)` y reenviarlo.

> Nota: 3b era **latente** — sólo se manifiesta cuando 3a ya está corregido.

### Bug 4 — Frontend: el fallo de Clerk quedaba invisible (spinner eterno)

**Síntoma reportado por el usuario: "el signup se queda cargando".**

- `initClerk()` **rechazaba** (launch) cuando faltaba la publishable key o no se
  podía cargar el bundle de UI. `onMount(async () => { await initClerk(); })` en
  `login/+page.svelte` y `signup/+page.svelte` **no tenía catch** → rechazo no
  manejado → `clerkReady` nunca fluctuaba a `true` → el bloque
  `{#if loading}` seguía renderizando el spinner **para siempre**, sin texto de
  error. `+layout.svelte` hacía `void initClerk()` (promesa flotante) → el
  rejection aparecía sólo como error de consola.
- En prod esto es exactamente lo que se ve: el build viejo lanza
  "Clerk keys are missing from your environment" y la página queda colgada en
  "Cargando acceso seguro…" / "Preparando tu cuenta…" sin explicación.
- Fix: `initClerk()` **no rechaza nunca**; publica el motivo en el nuevo store
  `clerkError` (y resuelve `null`, permitiendo reintento). `login/` y `signup/`
  reactionan a `$clerkError`, detienen el spinner y muestran el mensaje i18n
  (`clerk.initError`) más el detalle técnico.
- Tests de regresión: `src/tests/signup-page.test.ts` (spinner detenido + alert
  visible) y `src/tests/login-page.test.ts` (nuevo). RED→GREEN verificado
  revirtiendo el fix en ambas páginas.

### Estado de prod al momento de este informe

Prod **sirve el build viejo** (el chunk `chunks/clerk.D6Gd4bD3.js` sigue siendo
el que corre; la publishable key **no** aparece inlineada en ningún chunk). Por
eso el login/signup en prod sigue en spinner eterno con
"Clerk keys are missing from your environment" en consola.

**El fix del frontend es local y sin commitear — hace falta un rebuild de
Cloudflare Pages con `PUBLIC_CLERK_PUBLISHABLE_KEY` en las variables de build.**

### Verificación (local, con la key real de Clerk y un token de sesión real)

- Token de sesión real extraído del browser (`alg=RS256`, `kid=ins_3KyXjEm3ylo4QQMlpyCJnTk0SxU`,
  `azp=https://asistcv-frontend.pages.dev`, TTL ~60 s).
- Backend local (Postgres en `:5433`, `CLERK_PUBLISHABLE_KEY` + `CLERK_AUTHORIZED_PARTIES`
  con el origen de prod):
  - con 3a sin corregir → 401 `Invalid credentials` (reproduce prod exactamente);
  - con 3a corregido y usuario preexistente → **200** con el perfil real;
  - con 3a corregido y `CLERK_SECRET_KEY` faltando → 401 `USER_PROVISION_FAILED`
    (el fetch a `api.clerk.com` da 401 → prueba que la cadena JWKS+firma+azp+iss
    pasa y sólo falta la secret key);
  - auto-provisioning con el API de Clerk simulado → crea la fila con
    `clerk_id`, `email`, `role` (de `public_metadata`), `full_name`, `locale`,
    `avatar_url`, `email_verified_at` → `auth_method="clerk"`.
- Tests backend: 30/30 en `test_clerk_auth.py` (2 nuevos de regresión para el issuer),
  11/11 en `test_deps_clerk.py` (1 nuevo de regresión para `verify_api_key`).
  Suite completa: 736 passed, 8 failed **preexistentes** (offer_catchup,
  config_embedding_model, retrieval — verificados idénticos sin mis cambios).
- Frontend: 132/132 tests (129 previos + 3 nuevos de regresión del spinner),
  `npm run build` OK con la key inlineada en
  `build/_app/immutable/chunks/clerk.tj2mR4fW.js`, `svelte-check` 0 errores.
  Browser real: camino feliz (form de signup con email + password + "Continuar
  con Google") y camino de error (con el bundle de UI bloqueado → mensaje
  "Failed to load @clerk/ui bundle from https://…" y **sin** spinner).
- E2E de browser: signup real (verificación por email vía mail.tm) → perfil →
  login → sesión activa, con los componentes `SignIn`/`SignUp` montando bien.

### Discriminante: ¿Render tiene `CLERK_PUBLISHABLE_KEY`?

**No parece tenerlo.** A/B de latencia contra `/v1/users/me` con token RS256 de
`kid` desconocido (fuerza 2 fetches JWKS si Clerk está activo) vs. token HS256
(sin `kid`, va directo al path de API key):

| Target | RS256+kid desconocido | HS256 sin kid | delta |
|---|---|---|---|
| Local **con** Clerk | 1051 ms | 2 ms | **+1049 ms** |
| **Prod** | 215 ms | 202 ms | **+13 ms** |

Prod no paga el fetch de JWKS → `is_clerk_enabled()` es `False` en Render →
`CLERK_PUBLISHABLE_KEY` **no está seteada**, y el token cae al path de API key
(401 genérico). Confirmado además por el hecho de que el parser viejo
(`05ae8fe`) **falla al parsear la key de prod** (`pk_test_aW1tZW5zZS1sYW1iLTc3ODMuY2xlcmsuYWNjb3VudHMuZGV2JA`
decodifica a `immense-lamb-7783.clerk.accounts.dev$`, con el `$` adentro — el
parser viejo lo rompe; el tolerant parser `71047d3` ya lo arregla).

> Los valores de env de Render no son verificables desde afuera; esto es
> inferencia fuerte por latencia + parseo, no una lectura del dashboard.

### Riesgos / flags de seguridad y configuración

1. **`PUBLIC_BACKEND_API_KEY` filtrada en prod**: `/_app/env.js` la expone pública
   (valor `6e121ee4…`). Es la misma key que Render usa como `BACKEND_API_KEY`
   (probado: 403 `ROLE_FORBIDDEN` al mandarla como Bearer). **Rotar ambas.**
2. **Instancia Clerk de desarrollo en prod**: la key es `pk_test_` → badge
   "Development mode", límites estrictos de uso, y la instancia se llama
   **"Eptus"** (no AsistCV). Prod debería usar `pk_live_`.
3. **Factor password activo**: la instancia ofrece password + código de email;
   la spec (`odd/tasks/feat-clerk-auth-migration.md`) pide **passwordless** (sólo
   código por email).
4. **Webhook en `/api/v1/webhooks/clerk`**: correcto (patrón lemonsqueezy/stripe),
   pero **difiere del prefijo `/v1` del resto de la API** — mantener el `/api/v1`
   en el dashboard de Clerk.
5. `CLERK_SECRET_KEY` ausente en Render → sin auto-provisioning, el primer login
   devolverá 401 hasta que se setee.
6. `CLERK_AUTHORIZED_PARTIES` debe incluir **exactamente**
   `https://asistcv-frontend.pages.dev` (el `azp` del token lo claim-ea).

### Orden de deploy (corregido)

1. Backend (Render) con **3a + 3b** → redeploy.
2. Render: setear `CLERK_PUBLISHABLE_KEY` (la `pk_` que matchee la instancia),
   `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SIGNING_SECRET`, `CLERK_AUTHORIZED_PARTIES=https://asistcv-frontend.pages.dev`.
3. Frontend (Cloudflare Pages): rebuild con `PUBLIC_CLERK_PUBLISHABLE_KEY` en las
   variables de build.
4. Clerk dashboard: webhook `https://asistcv-backend.onrender.com/api/v1/webhooks/clerk`
   con `user.created`/`user.updated`/`user.deleted`; allowed origins con el
   dominio de Pages.
5. Rotar `BACKEND_API_KEY` / `PUBLIC_BACKEND_API_KEY` y sacarla del bundle público.
6. Smoke test: signup → `/v1/users/me` crea la fila → login → match.

### Artefactos QA

- `frontend/scripts/qa-token-collector.mjs` (nuevo, sin commitear): helper local
  para extraer el session token del browser sin errores de transcripción.
  **Es tooling de QA, no código de producto** — decidir si se commitea o se borra.
- `frontend/.env.local` (gitignored): `VITE_CLERK_PUBLISHABLE_KEY` →
  `PUBLIC_CLERK_PUBLISHABLE_KEY`.

## Issue aparte (Resend)
- Resend no envía NINGÚN email: las confirmaciones las resuelve Clerk, pero el resumen de ofertas del cron (#55) sigue roto → issue GitHub dedicado.

## Reconciliación con main y estado final (2026-10-25)

PR #123 (`6b8823a`) ya estaba mergeado en `main` y attackaba el mismo incidente
con otro enfoque: timeout de 15 s, `ClerkInitError` con códigos, store
`clerkError`, botón de retry y guardas de build. Sus tests (`clerk-init.test.ts`,
`clerk-init-error.test.ts`) y el doc de deploy también quedaron en main.

**Lo que main NO arreglaba** (y por eso el spinner seguía en producción):

1. Leía la key de `$env/dynamic/public` → `mod.PUBLIC_CLERK_PUBLISHABLE_KEY`
   es siempre `undefined` → Clerk aborta antes de tocar la red.
2. No cargaba el bundle `@clerk/ui` → en Clerk v6 los componentes prebuilt
   vienen aparte y `mountSignIn()` falla con "Clerk was not loaded with Ui
   components".

### Cadena causal verificada (browser real, prod + build local)

| | Prod (`asistcv-frontend.pages.dev`) | Build local reconciliado |
|---|---|---|
| Chunk servido | `chunks/clerk.D6Gd4bD3.js` (1108 B, código viejo) | `chunks/clerk.CPTx7UI4.js` |
| Lectura de la key | `$env/dynamic/public` → `undefined` | `$env/static/public` → inlineada |
| Requests al FAPI | **0** (Clerk aborta antes de la red) | `/v1/environment` + `/v1/client` → 200 |
| Bundle `@clerk/ui` | nunca se pide | se pide → 200 |
| Resultado | spinner eterno en `/login` **y** `/signup` | form de Clerk renderizado |

> **Corrección al informe anterior**: el `"client": null` observado contra
> `/v1/client` es un artefacto del probe. Ese endpoint devuelve `null` para
> una key **válida** cuando la request omite la versión de API que Clerk JS
> sí manda (`__clerk_api_version=2026-08-20` para `@clerk/clerk-js` 6.x) o el
> `Origin` de un origen permitido. La instancia de Clerk **está bien
> configurada** — el build local monta los componentes con la misma key.
> Por eso **no hace falta tocar el dashboard de Clerk** para que el login
> funcione.

### Commits de esta reconciliación

| Commit | Alcance |
|---|---|
| `48d43be` | Backend: issuer de Clerk sin barra final + `verify_api_key` reenvía la sesión de DB (3a/3b) |
| `a6604d7` | Frontend: key desde `$env/static/public`, carga del bundle `@clerk/ui`, store `clerkError`, guard de build |
| `1d2411c` | Merge de `main`: se conserva el init acotado + retry, y se suma la key estática + bundle UI |
| `7ba4a84` | Docs: deploy de Cloudflare Pages, orden de deploy, rotación de la key, diagnóstico de Clerk corregido |

Tres correcciones durante el merge:

- La carga del bundle UI se movió a `$lib/clerk-ui` (mockeable) y **dentro**
  del timeout de inicialización: un CDN que no responde tiene que dar timeout,
  no la espera eterna que este trabajo existe para eliminar.
- El auto-merge dejó **dos bloques `clerk`** en cada locale → la clave
  duplicada anulaba `errorTitle`/`errorBody`/`retry` de main. Los locales
  quedaron como en `main`.
- `login-page.test.ts` se eliminó: `clerk-init-error.test.ts` de main ya fija
  el camino de fallo del login y el retry; el archivo viejo afirmaba un
  contrato que ya no existe (`initClerk` resolviendo `null`).

### Verificación

- Frontend: **138 tests** verdes (14 archivos), `svelte-check` 0 errores.
- Backend: **744 passed, 1 skipped**.
- Build: prebuild y postbuild guards OK; key inlineada en `chunks/clerk.*.js`;
  `build/_app/env.js` sin `PUBLIC_BACKEND_API_KEY`.
- Browser (Orca, build de producción local): `/signup` y `/login` renderizan
  el form de Clerk, `spinner=false`, 2 inputs de Clerk.

### Lo que falta para producción (acciones del usuario)

1. **Cloudflare Pages**: redeploy con `PUBLIC_CLERK_PUBLISHABLE_KEY` — la
   variable **ya está** seteada (visible en `/_app/env.js` de prod); lo que
   faltaba era el código que la consumiera. Sacar `PUBLIC_BACKEND_API_KEY`
   del entorno de build (el guard va a fallar el build hasta que lo hagas).
2. **Render**: `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`,
   `CLERK_WEBHOOK_SIGNING_SECRET`, `CLERK_AUTHORIZED_PARTIES`.
3. **Clerk dashboard**: webhook en `https://<backend>/api/v1/webhooks/clerk`.
4. **Rotación**: `BACKEND_API_KEY` sigue expuesta en `/_app/env.js` de prod
   (mismo valor que usa Render) → rotar en Render + GitHub Actions +
   mcp-adapter.
5. **Higiene** (no bloqueante): la key de prod es `pk_test_` (instancia de
   desarrollo "Eptus"), el factor password sigue activo y la instancia no se
   llama AsistCV.

