# CI Setup — GitHub Actions

Configuración de CI/CD para AsistCV (issue #43, Sprint 0.5).

## Qué corre y cuándo

El workflow `.github/workflows/ci.yml` se ejecuta en:

- **push a `main`**
- **pull requests apuntando a `main`**

Los jobs corren en paralelo:

| Job | Qué hace | Comandos clave |
|---|---|---|
| `lint` | Ruff en backend y mcp-adapter | `uv run ruff check .` en cada proyecto |
| `typecheck` | mypy en backend y mcp-adapter | `uv run mypy app/` / `uv run mypy src/` |
| `test-backend` | Migraciones + pytest con cobertura, contra Postgres+pgvector real | `alembic upgrade head`, `pytest --cov=app` |
| `test-mcp` | pytest del adapter (sin DB) | `uv run pytest` |
| `docker-build` | Verifica que la imagen del backend compila (sin push) | `docker build -t asistcv-backend:ci ./backend` |
| `frontend-i18n-parity` | Paridad de claves entre `es.json` y `en.json` del frontend (spec match-ui) | `npm ci && node scripts/check-i18n-keys.mjs` en `frontend/` |

Detalles importantes:

- **Python 3.12** en todos los jobs, con **UV** (`astral-sh/setup-uv@v4`) y cache de dependencias habilitado (cachea según `uv.lock`).
- **test-backend** usa un service container `pgvector/pgvector:pg16` con health check `pg_isready`. GitHub Actions espera a que el servicio esté sano antes de correr los steps, así que no hay que "dormir" nada. El job exporta `DATABASE_URL=postgresql://asistcv_test:asistcv_test@localhost:5432/asistcv_test`.
- **docker-build** está condicionado a que exista `backend/Dockerfile` (`hashFiles`). Si el Dockerfile no está en el branch, el job se saltea solo.
- `concurrency` con `cancel-in-progress`: pushes sucesivos al mismo branch cancelan el run anterior (ahorra minutos).

## Branch protection (configuración manual en GitHub)

Para que no se pueda mergear a `main` con CI rojo:

1. Ir a **Settings → Branches → Add branch protection rule** (o **Rules → Rulesets** en la UI nueva).
2. Branch name pattern: `main`.
3. Activar **Require status checks to pass before merging**.
4. Buscar y agregar estos checks (aparecen después del primer run del workflow):
   - `Lint (ruff)`
   - `Typecheck (mypy)`
   - `Tests (backend)`
   - `Tests (mcp-adapter)`
   - `Frontend i18n parity`

   > Los nombres de check son los `name:` de cada job. Si preferís referirte por job id, son `lint`, `typecheck`, `test-backend`, `test-mcp`, `frontend-i18n-parity`.
5. Opcional pero recomendado:
   - **Require branches to be up to date before merging** (evita mergear código que pasó CI sobre un `main` distinto).
   - **Require a pull request before merging** si querés forzar revisión.

## Secrets

Para los futuros workflows de deploy (no usados por CI de validación), el repo ya tiene configurados estos secrets (Settings → Secrets and variables → Actions):

- `GROQ_API_KEY` — API key de Groq para el LLM
- `HF_TOKEN` — token de HuggingFace para embeddings
- `NEON_DATABASE_URL` — connection string de la DB en producción (Neon)

CI de validación **no** necesita secrets: los tests usan `LLM_PROVIDER=mock` por defecto y la DB del service container.

## Debugging

- Si un job falla, el log de cada step está en **Actions → CI → run → job**.
- Para reproducir `test-backend` localmente: levantar `pgvector/pgvector:pg16` en el puerto 5432 con user/pass/db `asistcv_test`, exportar `DATABASE_URL` y correr `alembic upgrade head && pytest --cov=app`.
- Errores de "port is already allocated" en CI no deberían ocurrir: cada runner es efímero y el servicio publica en el 5432 del runner.
