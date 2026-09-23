# Deploy — HuggingFace Spaces

How to deploy the AsistCV backend (FastAPI) to HuggingFace Spaces using the Docker SDK.

## Prerequisites

- A HuggingFace account with access to Spaces.
- Docker installed locally (to test the image before pushing).
- The backend Dockerfile lives at `backend/Dockerfile`. HF requires the Dockerfile
  at the **root** of the Space repository, so we push only the `backend/` subtree
  (see [Push to HF](#push-to-hf)).

## 1. Create the Space

1. Go to https://huggingface.co/new-space
2. Fill in:
   - **Space name**: `asistcv-backend`
   - **SDK**: **Docker** → template **Blank**
   - **Hardware**: **CPU basic** (2 vCPU, no GPU — enough for the API)
   - **Visibility**: public or private (private works; the Space URL then requires
     your HF token for API calls)
3. Click **Create Space**.

The Space repository will contain a `README.md`. Make sure it has this front-matter
so HF knows it is a Docker Space and which port the app listens on:

```yaml
---
title: AsistCV Backend
emoji: 📄
sdk: docker
app_port: 7860
---
```

`app_port: 7860` matches the `EXPOSE 7860` in the Dockerfile.

## 2. Configure Secrets

In the Space: **Settings → Variables and secrets → New secret**.

| Secret | Example value | Purpose |
|--------|---------------|---------|
| `DATABASE_URL` | `postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require` | Neon Postgres connection string (the app reads `DATABASE_URL`; a secret named `NEON_DATABASE_URL` would be ignored) |
| `GROQ_API_KEY` | `gsk_...` | Groq LLM provider |
| `HUGGINGFACE_API_KEY` | `hf_...` | HF Inference API (embeddings, BGE-M3) |
| `BACKEND_API_KEY` | random string | Shared key for the MCP adapter |
| `LLM_PROVIDER` | `groq` | Selects the Groq provider (`groq`, not `mock`) |

Notes:

- Secrets are injected as environment variables at container start.
- Never commit secrets to the repo; HF secrets are the only supported way.
- CORS: if the frontend will call the Space, add the frontend origin to the
  `CORS_ORIGINS`-style config or extend `cors_origins` in `backend/app/core/config.py`.

## 3. Connect the local repo to HF

```bash
git remote add huggingface https://huggingface.co/spaces/<user>/asistcv-backend.git
```

Authenticate if needed (HF CLI or token in URL):

```bash
huggingface-cli login
# or: git remote add huggingface https://<user>:<hf_token>@huggingface.co/spaces/<user>/asistcv-backend.git
```

## 4. Push to HF

HF looks for `Dockerfile` at the root of the Space repo, but in this monorepo it
lives under `backend/`. Push only that subtree:

```bash
git subtree push --prefix backend huggingface main
```

If the Space repo already has commits (e.g. the initial README) and the subtree
push conflicts, force the history with `--force` on a fresh Space or use:

```bash
git subtree split --prefix=backend -b hf-deploy
git push huggingface hf-deploy:main --force
```

## 5. Verify the deploy

1. Open the Space page and check the build logs (**Logs → Build**), then runtime
   logs (**Logs → Container**).
2. Hit the health endpoint:

```bash
curl https://<user>-asistcv-backend.hf.space/health
# → {"status":"ok"}
```

3. Interactive docs: `https://<user>-asistcv-backend.hf.space/docs`

Migrations are **not** run automatically on deploy. Run them against Neon from
your local machine:

```bash
cd backend
export DATABASE_URL="postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require"
uv run python scripts/test_neon_connection.py   # verify connection + pgvector
uv run alembic upgrade head
```

## Known limitations

- **Cold start**: free Spaces sleep after ~48h of inactivity; the next request
  takes ~1–2 min while the container rebuilds/boots.
- **CPU basic**: 2 vCPU, 16 GB RAM, no GPU. Fine for API + small LLM calls
  (Groq runs remotely), slow for anything compute-heavy.
- **Ephemeral storage**: the container filesystem is reset on restart; never
  store state locally (that is what Neon is for).
- **Single instance**: no horizontal scaling on the free tier.
