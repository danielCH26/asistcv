# Deploy — Render

How to deploy the AsistCV backend (FastAPI + Docker) to Render's free tier.

> **Why Render (and not HuggingFace Spaces)?** HF's free tier only allows
> Static Spaces (file hosting, no runtime, no secrets). Render's free tier
> offers a real Web Service: 750h/month, no credit card, native GitHub
> integration. Previously documented plan B from the stack migration.

## Prerequisites

- A Render account (https://render.com — sign up with GitHub, no card needed)
- The repo pushed to GitHub (danielCH26/asistcv)
- Working secrets: `GROQ_API_KEY`, `HUGGINGFACE_API_KEY`, `DATABASE_URL` (Neon)
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
| `GROQ_API_KEY` | your Groq key (`gsk_...`) |
| `HUGGINGFACE_API_KEY` | your HF token (`hf_...`) |
| `DATABASE_URL` | Neon connection string (`postgresql://neondb_owner:...@ep-...neon.tech/asistcv?sslmode=require&channel_binding=require`) |
| `LLM_PROVIDER` | `groq` |

Click **Save Changes** — Render redeploys automatically after env changes.

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
- **502/timeout right after Live**: the container is still waking up (cold
  start). Retry after 30-60s.
- **`DATABASE_URL` errors at runtime**: confirm the Neon string includes
  `?sslmode=require&channel_binding=require` — our SQLAlchemy config strips
  libpq-only params for asyncpg automatically (see `app/db/session.py`).
- ** CORS errors from the frontend**: add the Cloudflare Pages domain to
  `CORS_ORIGINS` env var (comma-separated), e.g.
  `CORS_ORIGINS=http://localhost:5173,https://asistcv-frontend.pages.dev`.
