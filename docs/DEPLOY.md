# Deploy — Render

How to deploy the AsistCV backend (FastAPI + Docker) to Render's free tier.

> **Why Render (and not HuggingFace Spaces)?** HF's free tier only allows
> Static Spaces (file hosting, no runtime, no secrets). Render's free tier
> offers a real Web Service: 750h/month, no credit card, native GitHub
> integration. Previously documented plan B from the stack migration.

## Prerequisites

- A Render account (https://render.com — sign up with GitHub, no card needed)
- The repo pushed to GitHub (danielCH26/asistcv)
- Working secrets: `JWT_SECRET`, `GROQ_API_KEY`, `HUGGINGFACE_API_KEY`, `DATABASE_URL` (Neon)
- The backend Dockerfile lives at `backend/Dockerfile` (already validated)

## 1. Create the Web Service

1. Go to https://dashboard.render.com → **New** → **Web Service**
2. **Connect** the GitHub repo `danielCH26/asistcv` (grant Render access if asked)
3. Configure:

| Setting | Value |
|---|---|
| **Name** | `asistcv-backend` |
| **Project** | `asistcv` (optional, groups the service) |
| **Language / Runtime** | **Docker** (auto-detected from `backend/Dockerfile`) |
| **Root Directory** | `backend` ← important: monorepo, Dockerfile is inside backend/ |
| **Region** | closest to you (e.g. São Paulo if available, otherwise Oregon/Virginia) |
| **Branch** | `main` |
| **Instance Type** | **Free** |

4. Click **Deploy Web Service** (first deploy takes 3-5 min: Docker build + image pull)

## 2. Environment Variables

In the service → **Environment** → **Add Environment Variable** (Render calls
secrets "environment variables"; they are injected at runtime, not committed):

| Key | Value |
|---|---|
| `JWT_SECRET` | **Required.** Secret that signs the access tokens. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. The deploy aborts at startup if it is missing or still holds the built-in default. |
| `GROQ_API_KEY` | your Groq key (`gsk_...`) |
| `HUGGINGFACE_API_KEY` | your HF token (`hf_...`) |
| `DATABASE_URL` | Neon connection string (`postgresql://neondb_owner:...@ep-...neon.tech/asistcv?sslmode=require&channel_binding=require`) |
| `BACKEND_API_KEY` | **Required.** Shared key for the protected `/v1` surface and for the internal cleanup crons. Setting it also disables `/docs` and `/openapi.json`. It must be byte-identical to the `BACKEND_API_KEY` **Actions secret** on GitHub and to `BACKEND_API_KEY` in the mcp-adapter settings — see Retention sweepers. |
| `AUDIT_CLEANUP_TOKEN` | **Required for the audit retention cron.** Compared with the `{"token": ...}` body of `POST /internal/audit/cleanup`. Must be byte-identical to the `AUDIT_CLEANUP_TOKEN` **Actions secret** on GitHub. |
| `LLM_PROVIDER` | `groq` |
| `REFRESH_TOKEN_RETENTION_DAYS` | Optional. Days of history kept for consumed/revoked rows in `users_refresh_tokens` by the `refresh-token-sweeper` cron. Defaults to `90`. Consumed/revoked rows are audit evidence, not active state, so the window is sized for incident response. **Active tokens are never deleted** — raising the value can never shorten a live session, and it does not affect the 30-day absolute session lifetime (`JWT_REFRESH_TTL`). |
| `BILLING_PROVIDER_ACTIVE` | Billing provider switch. Set to `stripe` in production. `mock` is the default (local dev / tests). Slice 1 of issue #56. |
| `STRIPE_SECRET_KEY` | **Required for Stripe.** Stripe secret key (`sk_live_...` or `sk_test_...`). |
| `STRIPE_WEBHOOK_SECRET` | **Required for Stripe.** Stripe webhook signing secret (`whsec_...`). |
| `STRIPE_PRICE_JOB_SEEKER_MONTHLY` | Stripe Price ID for the job_seeker_monthly plan. |
| `STRIPE_PRICE_RECRUITER_STARTER` | Stripe Price ID for the recruiter_starter plan. |
| `STRIPE_PRICE_RECRUITER_BUSINESS` | Stripe Price ID for the recruiter_business plan. |
| `STRIPE_PRICE_RECRUITER_AGENCY` | Stripe Price ID for the recruiter_agency plan. |
| `LEMON_SQUEEZY_API_KEY` | Lemon Squeezy API key. Configure in slice 2 of issue #56. |
| `LEMON_SQUEEZY_STORE_ID` | LS store ID. Configure in slice 2. |
| `LEMON_SQUEEZY_WEBHOOK_SECRET` | LS webhook HMAC secret. Configure in slice 2. |
| `LEMON_SQUEEZY_VARIANT_JOB_SEEKER_MONTHLY` | LS variant ID for job_seeker_monthly. Configure in slice 2. |
| `LEMON_SQUEEZY_VARIANT_RECRUITER_STARTER` | LS variant ID for recruiter_starter. Configure in slice 2. |
| `LEMON_SQUEEZY_VARIANT_RECRUITER_BUSINESS` | LS variant ID for recruiter_business. Configure in slice 2. |
| `LEMON_SQUEEZY_VARIANT_RECRUITER_AGENCY` | LS variant ID for recruiter_agency. Configure in slice 2. |
| `LEMON_SQUEEZY_TEST_MODE` | Use LS test-mode checkouts. Defaults to `true`; flip to `false` only when using live API keys. |
| `MERCADOPAGO_ACCESS_TOKEN` | **Required for Mercado Pago.** Access token (`APP_USR-...`) from the Mercado Pago dashboard. Without it the checkout with esta pasarela devuelve 503. |
| `MERCADOPAGO_PUBLIC_KEY` | Mercado Pago public key (la que ve el navegador). |
| `MERCADOPAGO_WEBHOOK_SECRET` | **Required for the Mercado Pago webhook.** Signing secret de la notificación. |
| `MERCADOPAGO_NOTIFICATION_URL` | **Required for Mercado Pago.** URL pública del backend donde MP notifica los pagos: `https://<backend>/api/v1/webhooks/mercadopago`. Sin esto el checkout se crea pero la suscripción nunca se activa (el usuario paga y no le llega nada). |
| `MERCADOPAGO_TEST_MODE` | `true` para el sandbox; `false` solo con claves de producción. |
| `WOMPI_PRIVATE_KEY` | **Required for Wompi.** Private key (`prv_...`) del aplicativo en panel.wompi.co. |
| `WOMPI_PUBLIC_KEY` | **Required for Wompi.** Public key (`pub_...`) del mismo aplicativo. |
| `WOMPI_WEBHOOK_SECRET` | **Required for the Wompi webhook.** Secret de eventos del panel (se usa para el checksum `X-Event-Checksum`). |
| `WOMPI_INTEGRITY_KEY` | Integrity key del aplicativo: firma la transacción contra el checkout de Wompi. |
| `WOMPI_ACCEPTANCE_TOKEN` | Token de aceptación (términos). El vigente se pide a `GET /v1/merchants/info` con la public key en el header `x-merchant-public-key`. |
| `WOMPI_TEST_MODE` | `true` para `sandbox.wompi.co`; `false` para `production.wompi.co`. |
| `JWT_SECRET` | **Requerido.** Secreto HS256 con el que el backend firma el access token (15 min) y el refresh token (30 días). Debe ser largo y aleatorio: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Si cambia, caducan todas las sesiones. |
| `EMAIL_PROVIDER` | `resend` (default), `brevo` o `console`. En producción está en `brevo`. `console` imprime el código en el log del servicio — solo para QA local. |
| `RESEND_API_KEY` | Clave de Resend (`re_...`), cuando `EMAIL_PROVIDER=resend`. **Hoy es solo plan B**: sin dominio emisor verificado, Resend no entrega a destinatarios distintos del titular de la cuenta. |
| `BREVO_API_KEY` | Clave de Brevo (`xkeysib-...`), cuando `EMAIL_PROVIDER=brevo`. Funciona con un **remitente verificado** sin dominio propio — es el camino de $0 mientras eptus no tenga dominio. |
| `EMAIL_FROM` | Remitente: `eptus <eptus.asistcv@gmail.com>` en producción. Brevo exige que la dirección esté verificada en su panel (Settings → *Senders, domains, IPs*). |
| `EMAIL_CODE_TTL_SECONDS` | Vigencia del código (default `600` = 10 minutos). |
| `EMAIL_CODE_MAX_ATTEMPTS` | Intentos fallidos antes de bloquear un código (default `5`). |
| `EMAIL_CODE_LENGTH` | Longitud del código numérico (default `6`). |
| `CLERK_PUBLISHABLE_KEY` | **Opcional.** Solo si se retoma Clerk (ver "Clerk (archivado)" más abajo). Vacío = el login nativo por código es el único camino. |
| `CLERK_SECRET_KEY` | **Opcional.** Auto-provisionado de usuarios de Clerk. Vacío con el login nativo. |
| `CLERK_WEBHOOK_SIGNING_SECRET` | **Opcional.** Firma del webhook de Clerk. Vacío con el login nativo. |
| `CLERK_AUTHORIZED_PARTIES` | **Opcional.** Orígenes permitidos en el claim `azp`. Vacío = solo Clerk. |

### Autenticación passwordless (código de email) — activa

El login ya **no** depende de Clerk: es propio. El usuario escribe su email,
recibe un código de 6 dígitos y se crea la cuenta en el primer login
verificado. No hay contraseñas (la columna `users.password_hash` es nullable
desde la migración 029).

**Flujo completo:**

| Endpoint | Qué hace |
|---|---|
| `POST /api/v1/auth/email-code/request` | Genera el código (SHA-256, TTL 10 min, un solo uso), lo envía por email y responde `202 {"detail":"CODE_SENT"}` siempre — genérico a propósito, para no filtrar si la cuenta existe. |
| `POST /api/v1/auth/email-code/verify` | Valida el código y devuelve el par de tokens (`access` 15 min + `refresh` 30 días con rotación). Crea la cuenta si es la primera vez. |
| `POST /api/v1/auth/refresh` | Rota el refresh token. Detecta reuso y revoca toda la familia. |
| `POST /api/v1/auth/logout` | Revoca el refresh token. |

**Variables de entorno en Render** (ver la tabla de arriba): `JWT_SECRET`,
`EMAIL_PROVIDER`, `RESEND_API_KEY` o `BREVO_API_KEY`, `EMAIL_FROM`.

**Protección contra abuso** (ya implementada, no tocar sin tests):

- Ventana de fuerza bruta compartida: 5 intentos fallidos en 15 min, por
  **email y por IP** (mismo corte para `request` y `verify`).
- Cooldown de 60 s por email entre códigos.
- Tope de 10 códigos por email por hora (anti *mail bombing*).
- 5 intentos por código antes de bloquearlo.
- Respuestas genéricas: nunca se distingue "ese email no existe" de "el código
  no era correcto".

**Qué proveedor usar hoy:**

| Proveedor | Costo | Requisito | Límite free |
|---|---|---|---|
| `brevo` | $0 | Remitente verificado (sin dominio propio) | 300 emails/día |
| `resend` | $0 | **Dominio emisor verificado** | 3.000/mes con tope de 100/día |
| `console` | $0 | Ninguno | Solo QA: imprime el código en el log |

**Estado actual (nov 2026): `brevo` está activo en producción** con la cuenta
`eptus.asistcv@gmail.com` y la API key `eptus-backend-prod-v2` (permisos
mínimos: *Restricted*, un único scope `Transactional email = All`). Variables
en Render:

```
EMAIL_PROVIDER=brevo
BREVO_API_KEY=xkeysib-<clave de eptus-backend-prod-v2>
EMAIL_FROM=eptus <eptus.asistcv@gmail.com>
```

> **Por qué Brevo y no Resend.** Sin dominio propio, Resend solo deja enviar al
> correo de la propia cuenta: para cualquier otro destinatario la API responde
> `403` con *"You can only send testing emails to your own email address"*.
> Brevo, en cambio, acepta **destinatarios arbitrarios** con un remitente
> verificado, sin comprar dominio (300 emails/día gratis). `RESEND_API_KEY`
> sigue en Render solo como plan B; lo que decide es `EMAIL_PROVIDER`.
>
> **Verificado en producción:** `POST /v1/auth/email-code/request` →
> `202` y en el log del servicio
> `{"provider": "brevo", "status": 201, "event": "email_sent"}` con
> `POST https://api.brevo.com/v3/smtp/email → 201 Created`.
>
> **Remitente verificado.** En `app.brevo.com` → Settings → *Senders, domains,
> IPs*, el remitente `eptus <eptus.asistcv@gmail.com>` ya está en **Verified**
> (Brevo manda el código de verificación a esa misma dirección). Verificado
> además con un destinatario distinto del titular:
> `{"provider":"brevo","to":"danielcordobahoward@gmail.com","status":201,
> "event":"email_sent"}` — o sea, **el login por código ya llega a cualquier
> usuario**, no solo al dueño de la cuenta.
>
> **Entregabilidad (riesgo aceptado).** Un remitente de email gratuito
> (`gmail.com`) cae más en spam y no tiene DKIM/DMARC propios: Brevo lo avisa
> con *"Freemail domain is not recommended"*. Se acepta mientras no haya
> dominio: `eptus.com` no está disponible y las alternativas Round-Robin/
> Cloudflare cuestan USD 5–16 al año.
>
> **Cuando se compre el dominio** (recomendado a medio plazo): verificarlo en
> Brevo (Settings → *Domains*), cambiar `EMAIL_FROM` a
> `eptus <noreply@<dominio>>` y, si se quiere, habilitar Clerk.
>
> Con `EMAIL_PROVIDER=brevo` y sin `BREVO_API_KEY`, el endpoint **no falla**:
> el servicio de email loguea `email_service_disabled` y el request sigue con
> `202`. El usuario no recibe el código, pero nada se rompe.

### Clerk (archivado — requiere dominio propio)

Auth is passwordless: Clerk sends a 6-digit email code and issues a short-lived session JWT (~60 s, auto-renewed by the SDK). The frontend sends it as `Authorization: Bearer <clerk session token>`; the backend verifies the RS256 signature against Clerk's JWKS, then resolves the local `users` row by `clerk_id`.

Three things must line up, or sign-up silently fails:

| Where | What |
|---|---|
| Cloudflare Pages env | `PUBLIC_CLERK_PUBLISHABLE_KEY` — the same instance as the backend |
| Render env | `CLERK_PUBLISHABLE_KEY` (same key), `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SIGNING_SECRET` |
| Clerk dashboard | The webhook endpoint, pointing at `https://<backend>/api/v1/webhooks/clerk` (note the `/api/v1` prefix) |

**How to tell a broken publishable key apart from a broken backend.** The decisive signal is whether the browser talks to the Clerk Frontend API at all. Open `/login` with the devtools console open:

- **No request to `*.clerk.accounts.dev` at all**: the publishable key never reached Clerk, so the SDK aborted before any network call and the console shows `Clerk keys are missing from your environment`. The frontend must read the key from `$env/static/public` — `$env/dynamic/public` exports a single `env` object, so `mod.PUBLIC_CLERK_PUBLISHABLE_KEY` is always `undefined` (this was the production failure).
- **Requests to `/v1/environment` and `/v1/client` that answer HTTP 200**: the instance and the key are fine. If the page still does not render, the failure is in the UI bundle (`npm/@clerk/ui`), not in the key.

> Do not diagnose from a bare `curl` of `/v1/client`. That endpoint answers `"client": null` for a perfectly valid key when the request omits the API version Clerk JS actually sends (`__clerk_api_version=2026-08-20` for `@clerk/clerk-js` 6.x) or the `Origin` of an allowed origin. A probe that does not match what the browser sends reports a false positive.

> A `pk_test_` key on a `*.clerk.accounts.dev` domain is a development instance. Clerk deletes inactive development instances, and a dev instance is not a production identity provider. Use a production instance (`pk_live_...`) for the deployed environment.

#### El proxy de Clerk (el bloqueante actual en producción)

**Estado al 2026-11-23: PENDIENTE, a propósito.** El login no funciona y
nadie puede comprar hasta que se resuelva. Todo lo demás (Wompi, Mercado
Pago, planes en COP, migraciones) está desplegado y verificado.

**Síntoma:** `/login` y `/signup` muestran el cartel "No pudimos cargar el
acceso", y el backend rechaza todos los tokens de sesión.

**Causa real (verificada contra el panel de Clerk):** la instancia de
producción tenía **un solo dominio**: `asistcv-frontend.pages.dev`, en estado
*Checking / Unverified*. Clerk le pide un CNAME `clerk` →
`frontend-api.clerk.services` en el DNS de ese dominio. **Es imposible:**
`pages.dev` es el zone compartido de Cloudflare, no una zona de la cuenta, y
no se le pueden agregar CNAMEs ni attachar un Worker. Sin ese proxy,
`/v1/environment` y `/.well-known/jwks.json` dan 404: el login no arranca y
el backend rechaza todos los tokens.

| Extremo | Lo que pide | Resultado |
|---|---|---|
| Frontend | `GET /v1/environment` (lo llama `clerk.load()`) | 404 → `clerk.load()` falla → el cartel de error |
| Backend | `GET /.well-known/jwks.json` (para verificar el token) | 404 → **todos** los tokens de sesión se rechazan |

**Lo que ya está hecho** (para que retomarlo sea rápido):

- La app vieja de Clerk (`Eptus`, con el proxy roto) **fue borrada**. Sus
  claves en Cloudflare Pages y Render quedaron sin instancia: **el login
  está caído a propósito, no por un descuido.**
- Hay una **app nueva** en la misma organización: **`eptus`**, con instancia
  de desarrollo en el dominio nativo `uncommon-pigeon-297.clerk.accounts.dev`
  (funciona sin DNS) y una instancia de producción creada con el dominio de
  aplicación `asistcv-frontend.pages.dev` (inverificada, como la anterior).
- La cuenta de Cloudflare **no tiene ningún dominio propio**: solo el
  proyecto de Pages y Workers.

**Lo que falta, en orden:**

1. **Un dominio propio** (ej. `eptus.co`, ~10 USD/año). Es la condición para
   que Clerk sirva una instancia de producción: el FAPI queda en
   `clerk.<tu-dominio>` y necesita el CNAME + el certificado que emite Clerk.
   Con dominio, además, eptus deja de depender de `pages.dev`.
2. **El proxy** según los pasos de Clerk: CNAME `clerk` →
   `frontend-api.clerk.services` (proxy naranja) y `accounts` →
   `accounts.clerk.services` (proxy del Account Portal). El panel tiene
   **"Configure DNS automatically"** si el dominio está en la misma cuenta
   de Cloudflare.
3. **La publishable key** nueva (la del dominio nativo) en los dos lados:
   - Cloudflare Pages → `PUBLIC_CLERK_PUBLISHABLE_KEY`
   - Render → `CLERK_PUBLISHABLE_KEY`

   Y el `CLERK_SECRET_KEY` de la instancia de producción en Render.
4. **El webhook de Clerk** en la instancia nueva apuntando a
   `https://asistcv-backend.onrender.com/api/v1/webhooks/clerk`, y su
   *signing secret* en `CLERK_WEBHOOK_SIGNING_SECRET` (Render).
5. **Allowed origins** de la instancia: `https://asistcv-frontend.pages.dev`
   (y el dominio propio, cuando lo haya).

**Mientras tanto**, si hace falta un login que funcione YA, la instancia de
**desarrollo** de la app `eptus` sirve: su publishable key codifica
`uncommon-pigeon-297.clerk.accounts.dev` y no necesita DNS. Es de desarrollo:
sin SLA, con límites estrictos de uso (emails y MAU) y Clerk puede borrarla
si queda inactiva. Sirve para probar el flujo completo, no para vender.

**Cómo verificar en un comando** (no cambia nada):

```bash
cd backend
CLERK_PUBLISHABLE_KEY="pk_live_..." FRONTEND_URL="https://asistcv-frontend.pages.dev" \
  uv run python scripts/diagnose_clerk.py
```

O, contra lo que está **desplegado** (no necesita ningún secreto: la key
es pública y sale del bundle del frontend):

```bash
cd backend
DEPLOYED_FRONTEND_URL="https://asistcv-frontend.pages.dev" \
  uv run python scripts/diagnose_clerk.py
```

Imprime los dos endpoints y un veredicto. Si el proxy (o la clave) están
bien, los dos dan 200 y el script sale con 0.

**Vigilante automático:** el workflow `Clerk availability`
(`.github/workflows/clerk-check.yml`) corre este chequeo en cada push a
`main` y cada 30 minutos. **Está en rojo a propósito** mientras el login
siga caído: es la señal de que ese es el bloqueo. Cuando se arregle, se pone
verde solo.

> **CORS:** el backend responde `Access-Control-Allow-Origin` solo para los
> orígenes configurados; un origen ajeno no recibe la cabecera. Ojo con
> `http://localhost:5173` / `5174`: están permitidos para el desarrollo
> local y conviene sacarlos de `CORS_ORIGINS` en Render si no los usás —
> con el funnel de auditoría anónimo, permitir `localhost` en producción
> deja abierta una vía innecesaria.

> Lo que **no** es la causa: el `HTTP 500 "Rate exceeded."` de las
> instancias de desarrollo. Ese síntoma aparece cuando la instancia de
> desarrollo se queda sin cuota, y en su momento era lo que se sospechaba
> aquí — pero la sonda contra el dominio real muestra un 404 de
> "Deployment Not Found", no un 500 de cuota. Son fallos distintos.

**Do not put `PUBLIC_BACKEND_API_KEY` in the Cloudflare Pages environment.** With `adapter-static`, every `PUBLIC_*` variable is published in `/_app/env.js`, which is served to every visitor — the service key would be readable by anyone. The frontend authenticates exclusively with the Clerk session token; the service key belongs only in Render, the `mcp-adapter` settings and the GitHub Actions secret. The build fails on purpose if it is present (`scripts/check-env.mjs` and `scripts/check-build.mjs`).

Click **Save Changes** — Render redeploys automatically after env changes.

> **Dónde encontrar cada valor en el dashboard de Lemon Squeezy**
>
> | Valor | Dónde encontrarlo en el dashboard |
> |---|---|
> | `LEMON_SQUEEZY_API_KEY` | **Settings → API** → crear o copiar la clave `api_key`. |
> | `LEMON_SQUEEZY_STORE_ID` | Barra de URL del dashboard cuando estás en cualquier sección de tu tienda: `app.lemonsqueezy.com/settings/stores/<AQUÍ VA EL ID>` — también visible en **Settings → Stores**. |
> | `LEMON_SQUEEZY_WEBHOOK_SECRET` | **Settings → Webhooks** → signing secret (o crear un webhook nuevo para copiar el secret). |
> | `LEMON_SQUEEZY_VARIANT_*` | **Products → [tu producto] → Variants** → hacer clic en la variante → copiar el ID numérico de la URL (ej. `/variants/12345`). |

### Billing — Wompi y Mercado Pago (Colombia)

Las dos pasarelas colombianas cobran en COP y ambas son **operativas**: el
checkout crea una hosted session y el webhook activa la suscripción. Sin el
webhook montado, el usuario paga y su plan no cambia — el peor fallo posible
en el camino de cobro.

| | Wompi | Mercado Pago |
|---|---|---|
| Backend | `backend/app/services/wompi_client.py` | `backend/app/services/mercadopago_client.py` |
| Provider | `backend/app/services/providers/wompi.py` | `backend/app/services/providers/mercadopago.py` |
| Webhook | `POST /api/v1/webhooks/wompi` | `POST /api/v1/webhooks/mercadopago` |
| Firma | `X-Event-Checksum` (SHA-256) | `x-signature: ts=…,v1=…` (HMAC-SHA256) |
| Montos | centavos (`amount_in_cents`) | pesos (`unit_price`) |
| Precios COP | `backend/app/services/providers/cop_prices.py` | el mismo archivo |

Los precios en COP viven en **una sola tabla** (`cop_prices.py`) porque
Mercado Pago pide pesos y Wompi centavos; si cada provider llevara la suya,
el mismo plan se cobraría a precios distintos según el botón que el usuario
pulse.

**Dónde se configura el webhook en cada panel**

- Wompi → `comercios.wompi.co` → **Desarrollo → Programadores** → *URL de
  Eventos* → `https://<backend>/api/v1/webhooks/wompi` → **Guardar**. La misma
  pantalla muestra las llaves del API y los secretos de **Eventos** e
  **Integridad** (botón *Mostrar*), y el interruptor **Activar modo de
  pruebas** para pasar a las llaves `pub_test_`/`prv_test_` del sandbox.
- Mercado Pago → **Tus integraciones → Notificaciones → Mercado Pago → URL de
  notificación** → `https://<backend>/api/v1/webhooks/mercadopago`

**Elige una sola como activa** con `BILLING_PROVIDER_ACTIVE=wompi` o
`=mercadopago`. Con las dos configuradas, el checkout usa la que esté activa
y el frontend puede ofrecer la otra como alternativa si el país no aplica.

> **Wompi: el checkout es el Web Checkout, no la API de transacciones.**
> `POST /v1/transactions` **no** sirve para nuestro caso: Wompi responde `422`
> `INPUT_VALIDATION_ERROR` con *"payment_method.token: No está presente"*
> (exige el token de una tarjeta tokenizada) y, para PSE, pide los datos
> completos del pagador (`financial_institution_code`, `user_type`,
> `user_legal_id`, `user_legal_id_type`, `payment_description`).
>
> El camino soportado es el **Web Checkout**: el backend arma la URL
> `https://checkout.wompi.co/p/?public-key=…&currency=COP&amount-in-cents=…
> &reference=…&signature:integrity=…&redirect-url=…&customer-data:email=…` y el
> frontend redirige ahí. Wompi crea la transacción cuando el usuario paga y
> avisa por webhook (`transaction.updated`), que es lo que activa la
> suscripción. El mismo host sirve sandbox y producción: el prefijo de la llave
> pública (`pub_test_` / `pub_prod_`) decide qué entorno se cobra. El
> `reference` (`{user_id}_{plan_id}_{uniq}`) es lo único que Wompi devuelve en
> el webhook, y es con lo que se activa el plan.
>
> **Wompi: dos tokens, no uno.** `GET /v1/acceptance_tokens` ya no existe
> (404) y `GET /v1/merchants/{public_key}` quedó deshabilitado el 2026-10-31.
> El camino vigente es `GET /v1/merchants/info` con la public key en el header
> `x-merchant-public-key`, y devuelve **dos** tokens: `acceptance_token`
> (términos) y `accept_personal_auth` (datos personales).

> **Wompi: E2E verificado de punta a punta (2026-11-24).** Transaccion real de
> sandbox: `POST /v1/billing/checkout` -> **200** con la URL de
> `checkout.wompi.co/p/` -> pago con tarjeta de prueba `4242 4242 4242 4242`
> -> "Pago aprobado!" (transaccion `12230131-1175496842-97639`, referencia
> `15_job_seeker_monthly_1795496692`, $29.000) -> webhook
> `POST /api/v1/webhooks/wompi` **200** con `LS upsert sub: user=15
> plan=job_seeker_monthly status=active` -> `GET /v1/billing/subscription` con
> `status: active`. Evidencia completa en
> `qa-reports/REPORTE-QA-2026-11-07.md` (seccion 24).
>
> Dos cosas que hacen falta y no son opcionales:
>
> - `FRONTEND_URL` debe existir en Render (apunta a
>   `https://asistcv-frontend.pages.dev`). Sin ella el redirect post-pago
>   apunta a `localhost:5173` y el usuario aterriza en su propia máquina.
> - La capa `COPY --from=builder /app/.venv` de `backend/Dockerfile` puede
>   salir **CACHED** en el build de Render y servir el paquete `app` de una
>   build anterior. Por eso el Dockerfile escribe `.venv/.source-hash` y el
>   CMD usa `python -m uvicorn` (no el script de consola). Si un fix no cambia
>   el comportamiento en produccion, revisa esa capa antes de seguir
>   depurando codigo.

### Retention sweepers

Three GitHub Actions crons POST to internal cleanup endpoints on the
deployed backend. **Each one needs the credential in two places**: the
service (Render → Environment) and the repository (GitHub → Settings →
Secrets and variables → Actions). A value configured on only one side
makes the cron fail with `401` on every run.

The two auth mechanisms are different, which is easy to mix up:

| Workflow | Endpoint | Credential | GitHub secret | Cadence | Deletes |
|---|---|---|---|---|---|
| `adaptation-sweeper.yml` | `POST /internal/adaptations/cleanup` | `X-Backend-API-Key` header | `BACKEND_API_KEY` | every 15 min | completed/orphaned `cv_adaptations` |
| `audit-retention.yml` | `POST /internal/audit/cleanup` | `{"token": ...}` in the body | `AUDIT_CLEANUP_TOKEN` | daily 03:17 UTC | expired `audit_uploads` |
| `refresh-token-sweeper.yml` | `POST /internal/auth/refresh-tokens/cleanup` | `X-Backend-API-Key` header | `BACKEND_API_KEY` | daily 04:23 UTC | consumed/revoked `users_refresh_tokens` older than `REFRESH_TOKEN_RETENTION_DAYS` |

Every endpoint **fails closed (401)** when its credential is unset, by
design: an internal endpoint must never become an open DELETE-by-cron.

Set a secret from the shell without pasting it into a PR, a commit or a
screenshot:

```bash
gh secret set BACKEND_API_KEY        # prompts, hidden
gh secret set AUDIT_CLEANUP_TOKEN
```

The sweeper runs every 15 minutes and the Render free tier sleeps after
~15 min of inactivity, so a scheduled run can land on a booting container.
The two sweepers therefore retry `502/503/504` up to 3 times with backoff;
the cleanup is idempotent (it only deletes rows already past the retention
thresholds), so replaying the call is safe. Any other non-2xx status is
reported immediately, with the response body, as an Actions error
annotation.


**Note on the port**: Render auto-detects the port exposed by the Dockerfile
(EXPOSE 7860) via its `PORT` mechanism. If the service doesn't bind, set
explicitly: Environment → `PORT` = `7860`.

## 3. Apply the migrations (Neon)

**Las migraciones las aplica el contenedor al arrancar.** El `Dockerfile`
corre `alembic upgrade head` antes de levantar el servidor, y el contenedor
ya tiene `DATABASE_URL` (lo inyecta la plataforma). No hay paso manual, no
hace falta guardar el secreto de la base en GitHub Actions y no hay que
acordarse de correrlo.

```dockerfile
CMD ["sh", "-c", "uv run alembic upgrade head && exec uv run uvicorn app.main:app --host 0.0.0.0 --port 7860"]
```

`alembic upgrade head` es idempotente: sin migraciones nuevas no hace nada.
Si una migración falla, **el contenedor no levanta** — es preferible a servir
código contra un esquema que no corresponde.

> **Autoescalado:** dos contenedores arrancando a la vez podrían correr la
> misma migración en paralelo. Con una instancia (el plan actual) no puede
> pasar. Si algún día se escala, esto hay que moverlo a un paso único (un
> job de despliegue o un lock en la base).

Para aplicarlas a mano (por ejemplo, si hay que revisar algo antes de
desplegar), la shell del servicio en Render:

```bash
cd /app && uv run alembic upgrade head && uv run alembic current
```

Neon suspende el servidor después de un rato de inactividad; la primera
consulta tras el sleep suma ~500 ms. Eso no afecta a la migración.

La cadena de conexión que usa el backend es la **directa** (no la del pooler):
Neon recomienda la directa para Alembic porque el pooler no soporta
sentencias preparadas.



## 4. Verify the deploy

When the deploy status turns **Live**:

```bash
# Render assigns the URL https://asistcv-backend-XXXX.onrender.com (check the dashboard)
curl https://<your-url>.onrender.com/health
# → {"status":"ok"}

curl https://<your-url>.onrender.com/v1/ping
# → {"pong":true,...}

curl -X POST https://<your-url>.onrender.com/v1/match \
  -H 'Content-Type: application/json' \
  -d '{"jd_text":"Senior Python developer wanted for remote work with FastAPI and PostgreSQL","profile_id":1}'
# → MatchAnalysis with real score from Qwen via Groq
```

## 5. Automatic deploys

By default, Render **auto-deploys on every push to `main`**. Combined with the
GitHub Actions CI (which must pass first if you enable branch protection), the
flow is:

```
push to main → CI green → Render auto-deploy → new version live
```

To make CI gate the deploy: Render → Settings → **Build & Deploy** →
**Deploy Hook** or enable "Wait for CI" via GitHub Checks (Render → Settings →
"Prevent deploy if build fails" / GitHub integration settings).

## Deploy — Cloudflare Pages (frontend)

The frontend is a static SPA (`@sveltejs/adapter-static`, `ssr = false`). Cloudflare Pages builds it from `frontend/` and publishes `frontend/build`.

### Build settings

| Setting | Value |
|---|---|
| Build command | `npm ci && npm run build` |
| Build output directory | `build` |
| Root directory | `frontend` |

(If the project root is the repository root instead, use `cd frontend && npm ci && npm run build` with the output directory `frontend/build`.)

### Environment variables (Settings → Environment variables)

| Variable | Value | Required |
|---|---|---|
| `PUBLIC_API_URL` | `https://asistcv-backend.onrender.com` | yes |
| `PUBLIC_CLERK_PUBLISHABLE_KEY` | the `pk_...` key of the same Clerk instance the backend uses | yes |
| `PUBLIC_BACKEND_API_KEY` | **must NOT be set** | no |

Both required variables are build-time: `adapter-static` inlines them into the bundle. `scripts/check-env.mjs` (prebuild) fails the build when one is missing or when `PUBLIC_BACKEND_API_KEY` is defined in the build environment, and `scripts/check-build.mjs` (postbuild) fails when that key reaches the published artifact.

> **Set the variables for the Preview environment too, not only Production.** Cloudflare Pages runs a separate build for every pull request, and each environment has its own variable set. A preview build without these two variables fails in the prebuild guard with
> `Faltan variables de entorno requeridas para build: PUBLIC_API_URL, PUBLIC_CLERK_PUBLISHABLE_KEY`,
> which shows up as a red **Cloudflare Pages** check on the pull request. The publishable key is public by design, so it is safe in the preview environment.

### Verify the deploy

```bash
# The published env module must carry the key and nothing else
curl -s https://asistcv-frontend.pages.dev/_app/env.js
# → export const env={"PUBLIC_API_URL":"...","PUBLIC_CLERK_PUBLISHABLE_KEY":"pk_..."}

# The published Clerk chunk must carry the key inlined
curl -s https://asistcv-frontend.pages.dev/_app/immutable/chunks/clerk.*.js | grep -c 'pk_'
```

A stale build is easy to recognise: the chunk that carries the key changes its hash on every build that includes it (`chunks/clerk.<hash>.js`). **If the hash does not change between deploys, the build ran without the key.**

### Rotating the service key

`BACKEND_API_KEY` authenticates the protected `/v1` surface and the cleanup crons. It lives in three places that must change together:

1. Render → Environment → `BACKEND_API_KEY`
2. GitHub → Settings → Secrets and variables → Actions → `BACKEND_API_KEY`
3. The `mcp-adapter` settings → `BACKEND_API_KEY`

Change all three, then redeploy the backend. `PUBLIC_BACKEND_API_KEY` is **not** part of the rotation: it must not exist anywhere.

## Deploy order

Backend and frontend ship **together** — they are two halves of one feature. The frontend change (the publishable key reaching the bundle) and the backend change (the Clerk verifier) depend on each other: shipping the frontend first leaves the API rejecting every session; shipping the backend first leaves the page unable to mount Clerk.

> **Step 0 — clean the Cloudflare Pages environment BEFORE the deploy.** `PUBLIC_BACKEND_API_KEY` is currently defined there, and with the guard in `scripts/check-env.mjs` a build that finds it **fails on purpose**. A failing Pages build keeps the previous build live, so merging without removing that variable changes nothing in production and the login stays on the spinner. Remove it from the **Production** environment (and set the two required variables in **Preview** so pull-request builds go green), then deploy.

1. **Cloudflare Pages**: remove `PUBLIC_BACKEND_API_KEY` from Production; add `PUBLIC_API_URL` and `PUBLIC_CLERK_PUBLISHABLE_KEY` to **Preview** as well; trigger a new build from `main` with a cleared build cache.
2. **Backend** (Render): set the four Clerk variables, then redeploy.
3. **Neon**: `alembic upgrade head` (the Dockerfile does NOT run migrations on startup — see "Apply the migrations").
4. **Clerk dashboard**: register the webhook at `https://<backend>/api/v1/webhooks/clerk` for `user.created`, `user.updated`, `user.deleted`.
5. **Smoke test**: sign up with an email code → the first `/v1/users/me` creates the row → sign in → run a match.

If the Pages build cannot be triggered before the backend is ready, deploy the backend first: the old frontend build keeps showing its own error, which is a better failure mode than a frontend that mounts Clerk while the backend cannot verify its tokens.

## Limitations of the free tier

- **Cold starts**: after ~15 min without traffic, the service spins down.
  The next request takes **30-50s** to respond (container boot). For the MCP
  adapter, raise its timeout (`TIMEOUT_SECONDS=60` in mcp-adapter settings).
- **750 hours/month**: enough for one always-on service (a month has ~744h).
  A second service (e.g. frontend preview) consumes from the same pool.
- **512 MB RAM / shared CPU**: plenty for FastAPI; the heavy work (LLM,
  embeddings) happens in Groq/HF, not here.
- **Sleep on inactivity**: the Neon serverless DB also auto-suspends; first
  query after inactivity adds ~500ms. Acceptable for single-user.

## Update an existing deploy

Push to `main` (auto-deploy) or use **Manual Deploy** → **Deploy latest commit**
from the service dashboard.

## Troubleshooting

- **Service "Deploy failed"**: check the **Logs** tab; most common cause is a
  missing env var (RuntimeError at startup) or the Dockerfile build error.
- **`JWT_SECRET must be set to a secret value...` at startup**: Render is not
  injecting the variable, or it still holds the repo's old default. Set
  `JWT_SECRET` in Environment to a freshly generated value and redeploy.
- **502/timeout right after Live**: the container is still waking up (cold
  start). Retry after 30-60s.
- **A sweeper fails with `HTTP 401`**: the GitHub secret and the Render env
  var are missing or not byte-identical. Copy the existing value from the
  service into the secret; do **not** generate a new one, because
  `mcp-adapter` authenticates with `BACKEND_API_KEY` too and a rotation
  breaks it until that side is updated as well.
- **A sweeper fails with `Missing secret`**: the credential is not set in
  the repository at all. The run aborts before touching the service.
- **A sweeper fails with `HTTP 502/503/504`**: the Render container is
  asleep or down. The run already retried 3 times; check the service status
  in the Render dashboard.
- **`AUDIT_CLEANUP_TOKEN` mismatched (the retention cron answers HTTP 401)**:
  the token in Render and the GitHub Actions secret are different values, or
  the Render one is unset. The endpoint compares the body `{"token": ...}`
  with `AUDIT_CLEANUP_TOKEN` using `hmac.compare_digest` and fails closed
  when unset. Copy the value from the service into the secret — do **not**
  generate a new one.
- **Sign-up page loads forever**: read the console first. A missing publishable key aborts the Clerk SDK before any request leaves the browser (`Clerk keys are missing from your environment`). A page that keeps the spinner without that message is an initialization that never settled: the initialization is bounded (15 s) and then renders an error with a retry button, so a spinner that never ends means the deployed build predates that bound. The backend staying healthy rules none of this out — `/health` never exercises Clerk.
- **`DATABASE_URL` errors at runtime**: confirm the Neon string includes
  `?sslmode=require&channel_binding=require` — our SQLAlchemy config strips
  libpq-only params for asyncpg automatically (see `app/db/session.py`).
- ** CORS errors from the frontend**: add the Cloudflare Pages domain to
  the `CORS_ORIGINS` env var. **The value MUST be a JSON array string** —
  pydantic-settings parses list-typed fields as JSON, not CSV (see
  `backend/app/core/config.py` for the field definition and parser note).
  Format: `CORS_ORIGINS='["http://localhost:5173","https://asistcv-frontend.pages.dev"]'`.
  Anything that is not a single string starting with `[` and ending with `]`
  will fail validation and the backend will not boot.
