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

## Guard de la base de test (fail-closed)

El suite es **destructivo por diseño**: `tests/conftest.py` corre `DROP SCHEMA public CASCADE` una vez por sesión y `TRUNCATE ... CASCADE` sobre ~20 tablas (`users`, `payments`, `audit_uploads`, `subscriptions`, ...) después de cada test. Como la resolución de la URL hace fallback a `DATABASE_URL` — que es la variable de la **aplicación** (`app/db/session.py` lee el mismo nombre) — exportar la connection string de producción y correr `pytest` borraba el schema de producción.

`tests/conftest.py` agrega un guard que aborta la sesión si el destino no es demostrablemente descartable. Corre **en el import del conftest**, o sea antes de cualquier fixture: si falla, pytest corta en collection y **nada** llega al `DROP SCHEMA` (ni siquiera un skip). Esto también cubre `tests/test_migrations.py`, que resuelve su propia `TEST_DATABASE_URL` y corre `alembic downgrade base` sin pasar por el fixture `test_db`.

El guard **rechaza** cuando:

| Check | Condición | Ejemplo que cae |
|---|---|---|
| 1. Parseable | la URL no identifica una base | URL malformada, sin nombre de base |
| 2. Misma base | `TEST_DATABASE_URL` y `DATABASE_URL` resuelven al mismo host + puerto + base + usuario | `TEST_DATABASE_URL` apuntando a producción |
| 3. Nombre descartable | el nombre de la base no contiene `test` como token | `neondb`, `asistcv` |
| 4. Host remoto | el host no es loopback y no hubo opt-in | cualquier Neon/RDS |

Pasa el path local sin ninguna configuración extra (`localhost` / `127.0.0.1` → el contenedor de `make db-up` en 5433).

### `ALLOW_REMOTE_TEST_DATABASE`

Opt-in explícito para correr el suite contra una base de test **remota** (por ejemplo, un branch de Neon descartable). Cubre los checks 3 y 4:

```bash
export TEST_DATABASE_URL="postgresql://USER:PASS@ep-xxx.us-east-2.aws.neon.tech/asistcv_test?sslmode=require"
export ALLOW_REMOTE_TEST_DATABASE=1
uv run pytest
```

Dos cosas importantes:

- **Va en el entorno real, no en `.env`.** pydantic-settings carga `.env` dentro de `Settings` y nunca puebla `os.environ`, así que el guard (que lee `os.environ`) no vería un valor posto sólo en `.env`.
- **No hay flag para saltear el check 2.** Si la URL de test y la de la app apuntan a la misma base, hay que corregir la URL, no levantar una bandera. `ALLOW_REMOTE_TEST_DATABASE` no lo destraba.

La comparación de "misma base" es por identidad completa (host + puerto + base + usuario) y **no** por host: una branch de Neon comparte host con su parent y sólo se diferencia en el nombre de la base, así que comparar por host bloquearía las branches (falso positivo) o dejaría pasar la base de producción (falso negativo). El nombre de la base es el discriminante.

El check 2 sólo corre cuando `TEST_DATABASE_URL` fue seteado explícitamente. Sin él, el destino de test **es** `DATABASE_URL` por declaración propia — que es lo que hace el CI de arriba, apuntando al Postgres descartable del service container. Ese caso lo cubren los checks 3 y 4: una `DATABASE_URL` de producción es remota y no se llama `*_test`, así que cae igual.

### Alcance de `CREATE ROLE`

El `CREATE ROLE asistcv_rls` (para los tests de RLS) queda **habilitado también en bases remotas**: los roles son de CLUSTER en Postgres, no de base, así que ese `CREATE` escribe en el namespace de roles del endpoint completo. La decisión es mantenerlo porque en una branch de Neon el cluster ya está aislado de producción, y porque `NOLOGIN NOSUPERUSER NOBYPASSRLS` no otorga ningún acceso. Lo que sí es database-scoped (`GRANT USAGE ON SCHEMA public`, `REASSIGN OWNED`) sólo toca la base guardada. Cuando el destino no es loopback, el suite imprime un aviso por stderr con la instrucción de limpieza manual (`DROP ROLE asistcv_rls;`) por si el endpoint no fuera una branch aislada.

## Debugging

- Si un job falla, el log de cada step está en **Actions → CI → run → job**.
- Para reproducir `test-backend` localmente: levantar `pgvector/pgvector:pg16` en el puerto 5432 con user/pass/db `asistcv_test`, exportar `DATABASE_URL` y correr `alembic upgrade head && pytest --cov=app`.
- Errores de "port is already allocated" en CI no deberían ocurrir: cada runner es efímero y el servicio publica en el 5432 del runner.
