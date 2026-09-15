# Tasks: Sprint 0 — Fundación técnica de AsistCV

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~960–1190 (total sprint, 5 PRs) |
| Review budget risk (600 líneas) | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (#6) → PR 2 (#7) → [PR 3 (#12) ∥ PR 4 (#9)] → PR 5 (#13) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main (decisión de usuario: 1 PR por issue, cada PR mergeable independientemente) |

```text
Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High
```

> Nota: budget efectivo del proyecto = 600 líneas (`openspec/config.yaml`). La guard line conserva el nombre canónico `400-line budget risk` para matching downstream.
> Buckets de tamaño: low <50 · medium 50–150 · high 150–300 líneas.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Monorepo scaffolding | PR 1 → main | `make help` + `git status --porcelain` vacío | N/A — solo archivos estáticos, sin runtime | Revert PR 1 (borra dirs/config raíz, nada más depende aún) |
| 2 | FastAPI skeleton | PR 2 → main (tras PR 1) | `cd backend && uv run pytest -q` | `uv run uvicorn app.main:app` + `curl :8000/health` | Revert PR 2; PR 1 queda intacto |
| 3 | Mock LLM provider | PR 3 → main (tras PR 2) | `cd backend && uv run pytest tests/llm -q` | Backend con `LLM_PROVIDER=mock` + `curl -X POST :8000/v1/match` | Revert PR 3; `/v1/match` vuelve a stub 501 |
| 4 | Alembic + Postgres local | PR 4 → main (tras PR 2, paralelo a PR 3) | `make migrate && make migrate-down` | `docker compose -f infra/docker-compose.yml up -d db` | Revert PR 4 + `alembic downgrade base` si aplicó |
| 5 | MCP adapter stdio | PR 5 → main (tras PR 3) | `cd mcp-adapter && uv run pytest -q` | Backend en `:8000` con mock + `uv run asistcv-mcp` (smoke stdio) | Revert PR 5; backend queda intacto |

## Resumen de tasks

| ID | Task | Issue | PR | Deps | Tamaño |
|----|------|-------|----|------|--------|
| 1.1 | Esqueleto de directorios + READMEs stub | #6 | 1 | — | low |
| 1.2 | `.gitignore` raíz | #6 | 1 | — | low |
| 1.3 | `Makefile` con `help` | #6 | 1 | 1.1 | low |
| 1.4 | README raíz (stack + quickstart) | #6 | 1 | 1.1 | medium |
| 2.1 | Proyecto UV `backend/` | #7 | 2 | PR 1 | medium |
| 2.2 | `settings.py` pydantic-settings | #7 | 2 | 2.1 | low |
| 2.3 | App FastAPI: `/health`, `/v1/ping`, `/docs` | #7 | 2 | 2.2 | medium |
| 2.4 | Logging JSON con structlog | #7 | 2 | 2.3 | low |
| 2.5 | Placeholder `POST /v1/match` (501) | #7 | 2 | 2.3 | low |
| 2.6 | Tests smoke FastAPI | #7 | 2 | 2.3–2.5 | low |
| 3.1 | Protocolo `LLMProvider` + modelos | #12 | 3 | PR 2 | medium |
| 3.2 | `MockProvider` determinista + fixtures | #12 | 3 | 3.1 | medium |
| 3.3 | `VertexAIProvider` stub | #12 | 3 | 3.1 | low |
| 3.4 | Factory por `LLM_PROVIDER` | #12 | 3 | 3.1–3.3 | low |
| 3.5 | Conectar `/v1/match` al factory | #12 | 3 | 3.4, 2.5 | low |
| 3.6 | Tests LLM (determinismo, factory) | #12 | 3 | 3.2–3.5 | low |
| 4.1 | `infra/docker-compose.yml` pgvector | #9 | 4 | PR 2 | low |
| 4.2 | Deps: alembic, sqlmodel, psycopg | #9 | 4 | 2.1 | low |
| 4.3 | `alembic.ini` + `env.py` vía settings | #9 | 4 | 4.2, 2.2 | medium |
| 4.4 | Migración inicial (tablas placeholder) | #9 | 4 | 4.3, 4.1 | medium |
| 4.5 | Targets Make: `db-up`, `migrate`, `migrate-down` | #9 | 4 | 4.1–4.4 | low |
| 4.6 | Verificar upgrade/downgrade en local | #9 | 4 | 4.5 | low |
| 5.1 | Proyecto UV `mcp-adapter/` | #13 | 5 | PR 1 | low |
| 5.2 | Servidor stdio (SDK `mcp`) | #13 | 5 | 5.1 | medium |
| 5.3 | Tool `ping` → "pong" | #13 | 5 | 5.2 | low |
| 5.4 | Tool `evaluate_match` → `/v1/match` | #13 | 5 | 5.2, PR 3 | medium |
| 5.5 | README Claude Desktop | #13 | 5 | 5.2 | low |
| 5.6 | Tests adapter | #13 | 5 | 5.3–5.4 | medium |

## Phase 1: Monorepo Foundation (PR 1 → issue #6)

- [x] 1.1 Crear `backend/`, `frontend/`, `mcp-adapter/`, `infra/`, `docs/` con `README.md` stub por directorio (rol + stack). **AC**: `ls` muestra los 5 dirs con README; `git status` limpio. (low)
- [x] 1.2 Crear `.gitignore` raíz: Python (`__pycache__/`, `.venv/`), Node/SvelteKit (`node_modules/`, `.svelte-kit/`, `build/`), secrets (`.env`, `.env.*`). **AC**: `git check-ignore .env` matchea; artefactos generados no aparecen en `git status`. (low)
- [x] 1.3 Crear `Makefile` con target `help` autodocumentado (lista targets desde comentarios). **AC**: `make help` lista targets sin error. (low)
- [x] 1.4 Crear `README.md` raíz: stack cerrado, prereqs (Python 3.12 + UV, Node 20 + npm, Docker), mapa del monorepo, quickstart placeholder. **AC**: comandos del quickstart existentes corren sin error. (medium)

## Phase 2: FastAPI Skeleton (PR 2 → issue #7, base: post-PR1)

- [ ] 2.1 `backend/pyproject.toml`: proyecto UV, `requires-python >=3.12`; deps `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `structlog`; dev `pytest`, `httpx`. **AC**: `uv sync` resuelve lockfile. (medium)
- [ ] 2.2 Crear `backend/app/settings.py` (pydantic-settings): `APP_ENV`, `LLM_PROVIDER` (default `mock`), `DATABASE_URL` opcional, `BACKEND_API_KEY` opcional. **AC**: instancia carga sin env vars obligatorias ni credenciales GCP. (low)
- [ ] 2.3 Crear `backend/app/main.py` + `backend/app/api/routes.py`: `GET /health` → `{"status":"ok"}`, `GET /v1/ping` → `{"pong":true}`, `/docs` habilitado. **AC**: `curl :8000/health` y `curl :8000/v1/ping` → 200; `curl -I :8000/docs` → 200. (medium)
- [ ] 2.4 Crear `backend/app/logging.py`: structlog en JSON + middleware de request log. **AC**: cada request emite 1 línea JSON parseable en stdout. (low)
- [ ] 2.5 Crear `backend/app/api/v1/match.py`: `POST /v1/match` placeholder con schemas pydantic request/response, retorna 501 "provider not wired". **AC**: curl → 501 con cuerpo JSON. (low)
- [ ] 2.6 Crear `backend/tests/test_smoke.py`: health 200, ping 200, match 501, `/docs` accesible. **AC**: `cd backend && uv run pytest -q` verde. (low)

## Phase 3: Mock LLM Provider (PR 3 → issue #12, base: post-PR2)

- [ ] 3.1 Crear `backend/app/llm/base.py`: protocolo `LLMProvider` con `evaluate_match(jd, cv) -> MatchEvaluation` + modelos pydantic de resultado. **AC**: importable, type-checks. (medium)
- [ ] 3.2 Crear `backend/app/llm/mock.py`: `MockProvider` determinista sobre fixtures `backend/tests/fixtures/match_*.json`. **AC**: misma entrada → misma salida byte-idéntica. (medium)
- [ ] 3.3 Crear `backend/app/llm/vertex.py`: `VertexAIProvider` stub que lanza error explícito si faltan credenciales GCP (sin lógica de inference). **AC**: con env sin creds → error claro, no crash silencioso. (low)
- [ ] 3.4 Crear `backend/app/llm/factory.py`: `get_llm_provider()` según `settings.llm_provider` (`mock` | `vertex`). **AC**: `LLM_PROVIDER=mock` → MockProvider; `vertex` → VertexProvider. (low)
- [ ] 3.5 Reescribir handler de `/v1/match` (2.5) para delegar en factory. **AC**: con `LLM_PROVIDER=mock`, POST → 200 con evaluación fixture determinista. (low)
- [ ] 3.6 Crear `backend/tests/llm/`: determinismo del mock (2 llamadas iguales), selección de factory por env, vertex sin creds → error. **AC**: `uv run pytest tests/llm -q` verde. (low)

## Phase 4: Alembic + Postgres Local (PR 4 → issue #9, base: post-PR2, paralelo a PR 3)

- [ ] 4.1 Crear `infra/docker-compose.yml`: servicio `db` con `pgvector/pgvector:pg16`, puerto 5432, volumen, healthcheck. **AC**: `docker compose up -d db` queda healthy; `\dx` lista `vector`. (low)
- [ ] 4.2 Agregar a `backend/pyproject.toml`: `alembic`, `sqlmodel`, `psycopg[binary]`. **AC**: `uv sync` resuelve. (low)
- [ ] 4.3 Crear `backend/alembic.ini` + `backend/alembic/env.py` leyendo `DATABASE_URL` de settings (default a Postgres local docker). **AC**: `uv run alembic revision --autogenerate` genera revisión. (medium)
- [ ] 4.4 Crear migración inicial `0001_placeholder` con tablas placeholder (`users_stub`, `matches_stub`) — el schema de dominio real es owner de Slice 1. **AC**: `alembic upgrade head` crea tablas en la db local. (medium)
- [ ] 4.5 Agregar targets al `Makefile`: `db-up`, `migrate` (upgrade head), `migrate-down` (downgrade -1). **AC**: `make migrate` y `make migrate-down` ejecutan sin error manual. (low)
- [ ] 4.6 Verificación AC de issue contra local (sustituye Cloud SQL de #8, diferido): ciclo completo `alembic upgrade head` → `downgrade -1` → `upgrade head`. **AC**: las 3 corridas OK, tablas aparecen/desaparecen. (low)

## Phase 5: MCP Adapter (PR 5 → issue #13, base: post-PR3)

- [ ] 5.1 Crear `mcp-adapter/pyproject.toml`: proyecto UV independiente, `requires-python >=3.12`, deps `mcp`, `httpx`; entry point `asistcv-mcp`. **AC**: `uv sync` resuelve; `uv run asistcv-mcp --help` no rompe. (low)
- [ ] 5.2 Crear `mcp-adapter/src/asistcv_mcp/server.py`: servidor stdio con SDK `mcp` y registro de tools. **AC**: proceso arranca en stdio y responde handshake MCP. (medium)
- [ ] 5.3 Implementar tool `ping` → retorna `"pong"`. **AC**: llamada al tool devuelve "pong". (low)
- [ ] 5.4 Implementar tool `evaluate_match(jd_url, cv_text)` → `POST {BACKEND_URL}/v1/match` con `Authorization: Bearer $BACKEND_API_KEY` solo si la env var existe; error manejable si backend inaccesible. **AC**: contra backend con `LLM_PROVIDER=mock` retorna evaluación mock. (medium)
- [ ] 5.5 Crear `mcp-adapter/README.md`: config de Claude Desktop (JSON de ejemplo con `uv run asistcv-mcp`) + env vars documentadas. **AC**: el JSON de ejemplo es válido. (low)
- [ ] 5.6 Crear `mcp-adapter/tests/`: `ping` → pong; `evaluate_match` contra backend mockeado (httpx MockTransport) retorna payload. **AC**: `cd mcp-adapter && uv run pytest -q` verde. (medium)

## Phase 6: Verificación Cruzada del Sprint (sin PR propio; al cerrar PR 5)

- [ ] 6.1 Ejecutar checklist de Success Criteria del proposal end-to-end (boot sin creds, endpoints, migraciones, tools MCP, Makefile, .gitignore). 
- [ ] 6.2 Confirmar #8/#10/#11 congelados: sin código GCP en el diff; comentario en cada issue con estado "deferred, scope frozen".
- [ ] 6.3 Auditar `git log`: 5 PRs con conventional commits, uno por issue.

## Plan de PRs Encadenados (stacked-to-main)

| Orden | PR | Issue | Base | Merge después de | Mergeable independiente |
|-------|----|-------|------|------------------|-------------------------|
| 1 | PR 1 | #6 | `main` | — | ✅ |
| 2 | PR 2 | #7 | `main` (branch desde post-PR1) | PR 1 | ✅ |
| 3a | PR 3 | #12 | `main` (branch desde post-PR2) | PR 2 | ✅ |
| 3b | PR 4 | #9 | `main` (branch desde post-PR2) | PR 2 (paralelo a PR 3, cualquier orden) | ✅ |
| 4 | PR 5 | #13 | `main` (branch desde post-PR3) | PR 3 | ✅ |

Regla: cada PR depende solo de merges **anteriores**, nunca de merges futuros. Al merge de cada PR, el diff visible es exclusivamente su issue.

## Forecast de Líneas por PR vs Budget (600)

| PR | Issue | Líneas est. | vs 600 |
|----|-------|-------------|--------|
| 1 | #6 | ~150–200 | ✅ bajo |
| 2 | #7 | ~250–300 | ✅ bajo |
| 3 | #12 | ~180–220 | ✅ bajo |
| 4 | #9 | ~180–220 | ✅ bajo |
| 5 | #13 | ~200–250 | ✅ bajo |
| **Total** | | **~960–1190** | ⚠️ excede → cadena obligatoria |
