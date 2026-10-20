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
deployed backend. All of them authenticate with the `BACKEND_API_KEY`
secret via the `X-Backend-API-Key` header and **fail closed (401)** when
that key is unset, so `BACKEND_API_KEY` must be configured on the service
for any of them to run.

| Workflow | Endpoint | Cadence | Deletes |
|---|---|---|---|
| `audit-retention.yml` | `POST /internal/audit/cleanup` | daily 03:17 UTC | expired `audit_uploads` |
| `adaptation-sweeper.yml` | `POST /internal/adaptations/cleanup` | every 15 min | completed/orphaned `cv_adaptations` |
| `refresh-token-sweeper.yml` | `POST /internal/auth/refresh-tokens/cleanup` | daily 04:23 UTC | consumed/revoked `users_refresh_tokens` older than `REFRESH_TOKEN_RETENTION_DAYS` |


**Note on the port**: Render auto-detects the port exposed by the Dockerfile
(EXPOSE 7860) via its `PORT` mechanism. If the service doesn't bind, set
explicitly: Environment → `PORT` = `7860`.

## 3. Verify the deploy

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

## 4. Automatic deploys

By default, Render **auto-deploys on every push to `main`**. Combined with the
GitHub Actions CI (which must pass first if you enable branch protection), the
flow is:

```
push to main → CI green → Render auto-deploy → new version live
```

To make CI gate the deploy: Render → Settings → **Build & Deploy** →
**Deploy Hook** or enable "Wait for CI" via GitHub Checks (Render → Settings →
"Prevent deploy if build fails" / GitHub integration settings).

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
