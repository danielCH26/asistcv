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
| `MERCADOPAGO_ACCESS_TOKEN` | Mercado Pago access token. Configure in slice 3 of issue #56. |
| `MERCADOPAGO_PUBLIC_KEY` | Mercado Pago public key. Configure in slice 3. |
| `MERCADOPAGO_WEBHOOK_SECRET` | Mercado Pago webhook secret. Configure in slice 3. |
| `CLERK_PUBLISHABLE_KEY` | **Required for Clerk auth.** The publishable key of the Clerk instance (`pk_live_...` in production). The backend derives the Frontend API domain from it to fetch the JWKS and validate session tokens. Must be the **same** key the frontend uses — otherwise the backend cannot resolve the signing keys. See "Clerk authentication" below. |
| `CLERK_SECRET_KEY` | **Required for Clerk auth.** Clerk Backend API key (`sk_live_...`). Enables auto-provisioning: when a Clerk token arrives for an unknown user, the backend fetches the profile from `api.clerk.com` and creates the local row. |
| `CLERK_WEBHOOK_SIGNING_SECRET` | **Required for the Clerk webhook.** Svix signing secret (`whsec_...`) from the Clerk dashboard endpoint's "Signing Secret". The webhook verifies the HMAC-SHA256 signature manually — no extra dependency. |
| `CLERK_AUTHORIZED_PARTIES` | Comma-separated list of origins allowed in the `azp` claim, e.g. `https://asistcv-frontend.pages.dev`. Empty falls back to `frontend_url`. |

### Clerk authentication

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

> **A `pk_test_` key on a `*.clerk.accounts.dev` domain is a development instance.** Clerk deletes inactive development instances, and a dev instance is not a production identity provider. Use a production instance (`pk_live_...`) for the deployed environment.

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

The Dockerfile does **not** run migrations on startup — `alembic upgrade head` is a separate, manual step against Neon:

```bash
cd backend
uv sync --all-extras
uv run alembic upgrade head
uv run alembic current   # → <revision> (head)
```

Run it whenever the migration chain gains a revision. The backend serves traffic against the schema it finds; a missing migration shows up as a runtime error (`column "clerk_id" does not exist`), not as a failed boot.

Neon suspends the server after inactivity; the first query after the sleep adds ~500 ms. That is expected and does not affect the migration step.

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

1. **Backend** (Render): set the four Clerk variables, then redeploy.
2. **Frontend** (Cloudflare Pages): set `PUBLIC_CLERK_PUBLISHABLE_KEY`, then trigger a new build.
3. **Neon**: `alembic upgrade head` (the Dockerfile does NOT run migrations on startup — see "Apply the migrations").
4. **Clerk dashboard**: register the webhook at `https://<backend>/api/v1/webhooks/clerk` for `user.created`, `user.updated`, `user.deleted`.
5. **Smoke test**: sign up with an email code → the first `/v1/users/me` creates the row → sign in → run a match.

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
