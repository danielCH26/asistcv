# Feature: c8-docs-makefile

> **Issue**: #51 (Fase 3 del audit, milestone v1.0)
> **Branch**: `feat/c8-docs-makefile`
> **Owner**: maintainer (Daniel)
> **Target**: v1.0 release (2026-10-14)
> **Scope**: One feature document for the cohesive change "make project truth match the deployed product". Substantial work — multiple files (~12 source files, ~10 commits), spans Makefile, env templates, docs, and dead code.

---

## Specs

### S1 — Makefile stubs must do work or not exist

Quote (issue #51, verbatim): *"`Makefile` — `setup` (`:42-44`), `test` (`:46-48`), `lint` (`:50-52`) y `deploy` (`:54-56`) solo imprimen `TODO` y salen con código 0. `README.md:27` y `:41` le dicen al usuario que corra `make setup` y `make test`. Un script que envuelva `make setup` no puede detectar el fallo porque el código de salida es 0."*

Decision (issue #51, verbatim): *"Implementar `setup`/`test` es lo más útil; un stub que sale con 0 es peor que un target inexistente."*

Acceptance:
- `make setup` exits non-zero when prerequisites are missing; runs real install steps when they are present.
- `make test` runs the working test suites (backend, mcp) and reports failures with non-zero exit.
- `make lint` runs the linters that work (backend `ruff`, frontend) and reports non-zero exit on findings.
- `make deploy` is either deleted (with README updates) OR wired to a real, documented target.
- The exit code of `make setup` and `make test` is observable to wrapper scripts.

Checks (one RED test per rule):
- RED test `test_makefile_setup_exits_nonzero_without_prereqs` — invokes `make setup` in a clean env without `uv`/`node` and asserts exit code != 0.
- RED test `test_makefile_test_runs_backend_suite` — invokes `make test` and asserts it executes `pytest` (not just echoes TODO).
- RED test `test_makefile_lint_runs_ruff` — invokes `make lint` and asserts `ruff check .` runs.

### S2 — `backend/.env.example` must document every var read by `Settings`

Quote (issue #51, verbatim): *"`backend/.env.example` documenta 12 de las 26 variables que lee `config.py`. Faltan `JWT_SECRET`, `AUDIT_CLEANUP_TOKEN`, `ADAPTATION_ENABLED`, `FRONTEND_URL`, 4× `STRIPE_PRICE_*` y 3× `RETRIEVAL_*`."*

Acceptance:
- Every field in `backend/app/core/config.py::Settings` appears in `backend/.env.example` with the exact validation alias and a comment line stating its purpose and whether it is required.
- `API_PREFIX` is either honored by config OR removed from the example (decision: remove — see T4 rationale).

Checks:
- RED test `test_env_example_covers_all_settings` — diffs `Settings.__fields__` aliases against `backend/.env.example` parsed keys; fails if any alias is missing from the example.
- RED test `test_env_example_jwt_secret_is_required_marker` — asserts `JWT_SECRET=` has no default value comment that matches the published literal `dev-secret-change-in-production`.

### S3 — `infra/.env.example` must point at the published port

Quote (issue #51, verbatim): *"`infra/.env.example:5` apunta a `localhost:5432` pero `docker-compose.yml:6` publica **5433** y `config.py:26` también usa 5433. Copiarlo produce un fallo de conexión."*

Acceptance:
- `infra/.env.example` uses port `5433` (matching `infra/docker-compose.yml` host publish and `Settings.database_url` default).

Checks:
- RED test `test_infra_env_port_matches_docker_compose` — parses `infra/docker-compose.yml` host port for the `db` service and asserts `infra/.env.example` `DATABASE_URL` references the same port.

### S4 — `frontend/.env.example` must not advertise forbidden public env vars

Quote (issue #51, verbatim): *"`frontend/.env.example:9` documenta `PUBLIC_BACKEND_API_KEY`, una variable que `scripts/check-env.mjs` y `ci.yml:163-166` tratan como violación que rompe el build."*

Acceptance:
- `frontend/.env.example` does not contain any `PUBLIC_*_API_KEY` entry that would be stripped/forbidden by `frontend/scripts/check-env.mjs`.

Checks:
- RED test `test_frontend_env_example_no_public_api_key` — reads `frontend/.env.example`, fails if any key matches `^PUBLIC_.*_API_KEY$`.
- RED test `test_frontend_env_passes_check_env_guard` — runs `node frontend/scripts/check-env.mjs` against a temp env that includes the example values; asserts exit 0.

### S5 — CORS docs must match the parser

Quote (issue #51, verbatim): *"Contradicción de formato CORS: `docs/DEPLOY.md:111-113` indica setear `CORS_ORIGINS` como CSV, pero `config.py:4-9` lo exige como array JSON y lo advierte en el docstring del módulo. Seguir la guía de troubleshooting rompe el CORS del frontend en producción."*

Acceptance:
- `docs/DEPLOY.md` (and any other deployment doc) instructs the reader to set `CORS_ORIGINS` as a JSON array string, matching `Settings.cors_origins`'s parser contract.

Checks:
- RED test `test_deploy_md_cors_is_json_array` — fails if `docs/DEPLOY.md` contains `CORS_ORIGINS=...` written as a comma-separated list (no `[]` brackets, no `json` keyword in the surrounding paragraph).
- Manual QA on Render: with `CORS_ORIGINS='["https://asistcv.example.com"]'`, `/v1/ping` returns 200 with the expected `Access-Control-Allow-Origin` header.

### S6 — README describes the deployed product

Quote (issue #51, verbatim list of drifts): *"Sprint 0 en curso", "Licencia: TBD" vs Apache 2.0 badge, "Cloud: GCP (Cloud Run, Cloud SQL)", "Match JD ↔ perfil, adaptar CV + outreach, tracking pipeline" (last two don't exist), "`make setup`" / "`make test`" stubs."*

Acceptance:
- `README.md` status line reflects v1.0 sprint state, not "Sprint 0 en curso".
- License section uses one badge and one body statement, matching.
- Cloud section names Render as backend, Cloudflare Pages as frontend.
- Capabilities section names only Match and Adaptación. Outreach/Tracking are explicitly out-of-scope or labelled "deferred to v2.0".
- `make setup` / `make test` references match the now-functional targets from T1.

Checks:
- RED test `test_readme_no_sprint_zero_in_progress` — fails if `README.md` contains `Sprint 0 en curso`.
- RED test `test_readme_no_gcp_runtime_claims` — fails if `README.md` contains `Cloud Run`, `Cloud SQL`, or `Artifact Registry` outside a "what we left behind" footnote.
- RED test `test_readme_capabilities_match_codebase` — for each capability named in the README "Capabilities" section, asserts at least one route/model/service exists.

### S7 — PROJECT.md reflects current state

Quote (issue #51, verbatim): *"`PROJECT.md:9` dice que el próximo paso es arrancar Slice 1; Slice 1 y Slice 2 ya están mergeados. `PROJECT.md:64-70` lista como pendientes la migración free tier y el deploy, ambos hechos (#38-#43, #41, #42)."*

Acceptance:
- `PROJECT.md` "Next step" no longer says "arrancar Slice 1"; it points at v1.0 polish and v2.0 scope.
- Closed items (#38–#43, deploy, free-tier migration) are not listed as pending.

Checks:
- RED test `test_project_md_no_completed_milestones_listed_as_pending` — fails if `PROJECT.md` lists as pending any issue numbered ≤#43 or any item in the free-tier migration list.

### S8 — ROADMAP uses real endpoints and tool names

Quote (issue #51, verbatim): *"`ROADMAP.md:39,58` documenta endpoints que no existen con esos paths (`POST /jobs/evaluate` es `POST /v1/match`; `POST /jobs/{id}/adapt` es `POST /v1/adaptations`). `ROADMAP.md:41,60` documenta tools MCP (`evaluate_job`, `read_profile`, `update_profile`, `adapt_for_job`) que no están implementadas; existen `ping`, `get_health` y `evaluate_match`."*

Acceptance:
- ROADMAP names `/v1/match`, `/v1/adaptations`, and `mcp-adapter` tools that exist in `mcp-adapter/src/asistcv_mcp/tools.py`.

Checks:
- RED test `test_roadmap_endpoints_exist` — for every path in ROADMAP.md, parses `backend/app/api/v1/*.py` route table and asserts the path exists.
- RED test `test_roadmap_mcp_tools_exist` — for every tool name in ROADMAP.md MCP section, asserts it appears in the MCP adapter's tool registry.

### S9 — STACK names Render as the backend deploy

Quote (issue #51, verbatim): *"`STACK.md:27` dice que el backend se despliega en **HuggingFace Spaces**; el deploy real es **Render**."*

Acceptance:
- `STACK.md` "Hosting" / "Deploy" section names Render for backend, Cloudflare Pages for frontend.

Checks:
- RED test `test_stack_md_backend_is_render` — fails if `STACK.md` backend deploy is `HuggingFace Spaces` (without a "previously hosted on" historical note) or any other provider.

### S10 — `infra/README.md` describes the real infra

Quote (issue #51, verbatim): *"`infra/README.md:5-16` describe Cloud Run, Cloud SQL, Artifact Registry, Terraform y Cloud Build. El directorio contiene un `docker-compose.yml` y un `.env.example`."*

Acceptance:
- `infra/README.md` describes `docker-compose.yml` and `.env.example` as the actual infra. A historical "previously on GCP" footnote is allowed.

Checks:
- RED test `test_infra_readme_no_gcp_runtime_claims` — same rule as S6 but scoped to `infra/README.md`.

### S11 — Dead code catalog sweep

Quote (issue #51, verbatim): *"`TokenRevocation` (blacklist de access tokens inerte), la tabla `Payment` (nunca escrita), el servicio `cv_storage` (solo referenciado en líneas comentadas), `init_db`/`close_db` (nunca llamados), helpers de consent sin callers, `stripe_client.create_customer`, `ROLE_IMMUTABLE` check inalcanzable, y varios más."*

Acceptance — each of these is deleted with no test breakage:
- `TokenRevocation` model — `backend/app/db/models.py` (catalog path stale; A60)
- `Payment` model — `backend/app/db/models.py` (A61)
- `cv_storage` service — `backend/app/services/cv_storage.py` (A62)
- `init_db` / `close_db` — `backend/app/db/session.py:92,99` (A63)
- `consume_token`, `get_recruiter_consent`, `create_recruiter_consent` — `backend/app/services/consent_gate.py`, `backend/app/api/v1/recruiter_consent.py` (A64)
- `ROLE_IMMUTABLE` branch — `backend/app/schemas.py` (A65)
- `stripe_client.create_customer` — `backend/app/services/stripe_client.py` (A66)
- `Embedding.provider` default — `backend/app/db/models.py` (A67)
- `pdf_parser.CHUNK_SIZE`, `pdf_parser.validate_file_size` — `backend/app/services/pdf_parser.py` (A68)
- `_debug_safe_headers` — `mcp-adapter/src/asistcv_mcp/http_client.py` (A69)
- `/history/[id]/+page.svelte` — `frontend/src/routes/history/[id]/+page.svelte` (A70 — unreachable)

Checks:
- RED test `test_no_token_revocation_table` — fails if a `TokenRevocation` model is registered in the Alembic metadata.
- RED test `test_no_payment_model` — same for `Payment`.
- RED test `test_no_cv_storage_service` — fails if `backend/app/services/cv_storage.py` exists.
- RED test `test_no_init_db_call` — fails if `app/main.py` lifespan calls `init_db`.
- RED test `test_no_consume_token` — fails if `consume_token` is exported from `consent_gate.py`.
- RED test `test_no_stripe_create_customer` — fails if `stripe_client.create_customer` is defined.
- RED test `test_no_unreachable_role_branch` — fails if `schemas.py` references `ROLE_IMMUTABLE`.
- RED test `test_no_orphaned_history_id_route` — fails if `frontend/src/routes/history/[id]/+page.svelte` exists and is referenced from any nav/layout.

### S12 — Catalog paths corrected

Quote (90-catalogo-completo.md): references to `backend/app/models.py` (A2, A7, A18, A60, A67) while actual file is `backend/app/db/models.py`.

Acceptance:
- `docs/audit/90-catalogo-completo.md` file:line references match the actual file tree (no `backend/app/models.py` references that don't exist).

Checks:
- RED test `test_catalogo_paths_resolve` — parses every `file:line` in the catalog and asserts the path exists in the repo.

---

## Tasks

Each task = one work-unit commit on `feat/c8-docs-makefile`. Test-first (RED → GREEN → REFACTOR). Conventional Commits.

| ID | Title | Route | Linked S# | Commit |
|---|---|---|---|---|
| T1 | Makefile: implement `setup`/`test`/`lint` (delete `deploy`) | direct + tests | S1 | `feat(make): implement setup/test/lint targets` |
| T2 | Add RED test that asserts `backend/.env.example` covers every `Settings` alias | delegated writer | S2 | `test(env): RED examples pin distinct Settings aliases` |
| T3 | Complete `backend/.env.example` (all 14 missing aliases + JWT_SECRET marker) | direct | S2 | `docs(env): document every backend Settings var` |
| T4 | Drop `API_PREFIX` from `backend/.env.example` (not honored by config) | direct | S2 | `docs(env): remove API_PREFIX no longer honored` |
| T5 | Fix `infra/.env.example` port 5432 → 5433 | direct + test | S3 | `fix(env): align infra DATABASE_URL with docker-compose port` |
| T6 | Remove `PUBLIC_BACKEND_API_KEY` from `frontend/.env.example` | direct + test | S4 | `fix(env): drop forbidden PUBLIC_BACKEND_API_KEY` |
| T7 | Rewrite CORS paragraph in `docs/DEPLOY.md` to JSON-array format | direct + test | S5 | `docs(deploy): CORS_ORIGINS as JSON array` |
| T8 | Rewrite `README.md` against deployed product (v1.0 status, Render, capabilities, license, makes) | direct + tests | S6 | `docs(readme): rewrite against deployed product` |
| T9 | Rewrite `PROJECT.md` "Next step" + pending list | direct + test | S7 | `docs(project): reflect current state` |
| T10 | Rewrite `ROADMAP.md` endpoints and tools sections | direct | S8 | `docs(roadmap): real endpoints and tools names` |
| T11 | Rewrite `STACK.md` deploy destination | direct | S9 | `docs(stack): backend on Render, frontend on Pages` |
| T12 | Rewrite `infra/README.md` against docker-compose | direct | S10 | `docs(infra): drop GCP, describe docker-compose` |
| T13 | Delete dead-code symbols (A60–A70) with RED tests | delegated writer | S11 | `docs(audit): delete dead code A60-A70` |
| T14 | Correct stale `models.py` paths in `90-catalogo-completo.md` | direct | S12 | `docs(audit): correct file:line catalog paths` |
| T15 | Final QA + commit `feat(c8): docs and audit complete, closes #51` | direct | all | `feat(c8): docs and audit complete, closes #51` |

---

## Log

### L1 — User's verbatim request (2026-10-07)

> "Sigue la ruta que consideres mas optima, pusheas, haces testeo qa cuando sea pertinente si se necesita migrar la db o alguna cosa que si o si no puedas hacer tu me lo pides y te aviso para continuar"

Implied scope: continue through the remaining issues using ODD methodology; push when ready; do own QA when automatable; defer migrations/secrets work to the maintainer with a heads-up.

### L2 — Route decision (2026-10-07)

Optimal path under ODD: start with #51 (Fase 3 C8, foundation-truth work), then v1.0 features (#54 → #61 → #59), then the housekeeping task T5 (GH issue closures #77–#87/#84).

Rationale: #51 is medium-sized but cohesive; it unblocks #33/#34 (also touched in audit scope); it touches the same files many later features will reference; closing it removes the "Fase 3 incomplete" signal from the v1.0 board.

### L3 — Scope discoveries (2026-10-07)

- `frontend-test` target invokes `vitest run` but `frontend/tests/` is empty. Not in this feature (lives in #50 follow-up) — note for handoff.
- `make migrate` invokes `app.db.seed`; not blocking. Verified manually outside this feature.
- `_debug_safe_headers` in `mcp-adapter/src/asistcv_mcp/http_client.py` — confirmed unused; deletion in T13.
- `ROLE_IMMUTABLE` branch in `schemas.py` — needs grep confirmation before T13 deletes it (catalog says "unreachable" but the branch may live elsewhere).

### L4 — Items deferred to maintainer (cannot do from here)

- `JWT_SECRET` rotation on Render dashboard (issue #44 item 0.1) — already done; not in scope.
- DB migrations against Neon (migrations are applied via Render release command, not from this branch). No DB migration needed for #51 — dead code sweep keeps DB schema intact (deleted symbols are Python-only or already absent from migrations).
- Secrets in `backend/.env.example` are documented with empty values; the maintainer must populate Render env from these values.

### L5 — Evidence / commits (appended as work progresses)

- TBD per task.