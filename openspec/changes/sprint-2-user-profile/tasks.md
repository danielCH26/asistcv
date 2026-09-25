# Tasks: Sprint 2 — Cuentas de usuario, CV y Billing (Slice 2)

## Review Workload Forecast

| Campo | Valor |
|---|---|
| Líneas estimadas totales | ~2410 en 7 PRs (código + tests + migraciones) |
| Budget por PR (config: `review_budget_lines`) | 600 |
| Riesgo de budget | Medium — PR1 ~480l y PR7 ~450l superan la guard default de 400, pero quedan bajo el budget del proyecto (600) |
| PRs encadenados recomendados | Yes |
| Split sugerido | PR1 → {PR2 ∥ PR3 ∥ PR4 ∥ PR5} → PR6 → PR7 |
| Delivery strategy | auto-chain |
| Estrategia de cadena | Stacked to Main (cada PR mergea a main en orden; cerrada en design §13) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

**Decisión antes de apply**: NO se requiere `size:exception`. Los 7 PRs quedan bajo el budget de 600l del proyecto (máximo PR1 ~480l). La guard default de 400 se cubre con el split; PR1 y PR7 se marcan como los de mayor carga de review (~480l y ~450l, revisables en ~30 min según design §13.5).

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Auth foundation: dual JWT + API key, RBAC, refresh rotation | PR1 | `pytest backend/tests -k "auth or users or dual"` | Registro + login + refresh en dev; MCP smoke con API key post-merge | Revert PR1 + `alembic downgrade 002_add_vector_columns`; sistema vuelve a API-key-only |
| 2 | CV management: upload PDF streaming + editor estructurado | PR2 | `pytest backend/tests -k "cv or parser"` | Upload PDF real ≤10MB en dev; PATCH editor; DELETE | Revert PR2 + `alembic downgrade 003_users_and_refresh_tokens` (aditiva) |
| 3 | Free audit: funnel anónimo + rate limit + retención 30d | PR3 | `pytest backend/tests -k "audit or rate_limit"` | POST /v1/audit con PDF real; 4ª llamada → 429; cleanup manual | Revert PR3 + `alembic downgrade` de 006; deshabilitar workflow GH |
| 4 | Recruiter roster: CRUD + ToS gate + ranking híbrido | PR4 | `pytest backend/tests -k "recruiter or ranking or consent"` | Registro recruiter + consent; add candidato; ranked con JD real | Revert PR4 + `alembic downgrade` de 005 |
| 5 | Billing: Stripe Checkout + webhook idempotente + tier enforcement | PR5 | `pytest backend/tests -k "billing or stripe or webhook"` | Checkout sandbox (card + PSE); webhook CLI de Stripe; 402 al agotar plan | Revert PR5 + `alembic downgrade` de 007; Stripe en test mode, sin downgrade de datos |
| 6 | RLS: policies + tests de aislamiento cross-user/role | PR6 | `pytest backend/tests -k "rls or isolation"` | Manual cross-user en Neon branch (canary checklist) antes de prod | Revert PR6 + `alembic downgrade 007_subscriptions_payments` (drop policies; checks de servicio persisten) |
| 7 | Frontend: sesión JWT + rutas nuevas + onboarding | PR7 | `npm run build && npm run check && npm run test` (frontend/) | Flujo completo login → CV → match → audit contra staging | Revert PR7 + re-deploy frontend con `PUBLIC_BACKEND_API_KEY` (modo pre-Sprint 2) |

## Resumen de tasks

| ID | Task | Capacidad | PR | Depende | Tamaño |
|---|---|---|---|---|---|
| A1 | Deps: `passlib[bcrypt]`, `PyJWT`, `python-multipart`, `email-validator` | authentication | PR1 | — | S |
| A2 | Migración 003: `users`, `users_refresh_tokens`, `token_revocation`, `auth_login_attempts`, `auth_security_events` + `owner_user_id` en `profiles`/`analyses` | user-accounts | PR1 | A1 | M |
| A3 | Modelos: `User`, `RefreshToken` + soporte; columnas owner en `Profile`/`Analysis` | user-accounts | PR1 | A2 | M |
| A4 | `core/config.py`: `JWT_SECRET`, `JWT_ALGORITHM`, TTLs access/refresh | authentication | PR1 | — | S |
| A5 | `core/security.py`: hash bcrypt (cost 12), encode/decode JWT HS256 con `jti` | authentication | PR1 | A4 | M |
| A6 | `services/rls_context.py`: context manager `SET LOCAL app.current_user_id/role` | cv-management | PR1 | A2 | S |
| A7 | `api/deps.py`: `get_current_user` dual (JWT-first, API key fallback → `CurrentUser(id=0, role="service")`) + `require_role` | authentication | PR1 | A5 | L |
| A8 | `api/v1/auth.py`: register, login, refresh (rotación + TOKEN_REUSED), logout, verify-email request/confirm | user-accounts | PR1 | A5, A6 | L |
| A9 | `api/v1/users.py`: GET/PATCH `/users/me` (ROLE_IMMUTABLE), POST `/users/me/password` | user-accounts | PR1 | A7 | M |
| A10 | Dual auth en `/v1/match` + `analyses.py`: persiste/filtra `owner_user_id` (checks de servicio, RLS llega en PR6) | match-analysis | PR1 | A7 | M |
| A11 | Tests PR1: dual-auth parity, RBAC, rotación/reuso, brute force, register (25 tests) | authentication | PR1 | A8–A10 | L |
| B1 | Deps: `pypdf`, `pdfminer.six` | cv-management | PR2 | PR1 mergeado | S |
| B2 | Migración 004: `users_cvs` (BYTEA, JSONB, vector(1024)) + índice HNSW | cv-management | PR2 | B1 | M |
| B3 | Modelo `UserCV` | cv-management | PR2 | B2 | S |
| B4 | `services/pdf_parser.py`: streaming 64KB pypdf + fallback pdfminer.six | cv-management | PR2 | B1 | M |
| B5 | `api/v1/cvs.py`: POST/GET/GET{id}/PATCH/DELETE con checks de servicio por owner | cv-management | PR2 | B3, B4 | L |
| B6 | Re-cálculo de embedding en PATCH (async, no bloquea 200) | cv-management | PR2 | B5 | M |
| B7 | Tests PR2: upload, 413/415/422/503, CRUD, cross-user 404, editor (12 tests) | cv-management | PR2 | B5, B6 | M |
| C1 | Migración 006: `audit_uploads` + `audit_funnel_events` + índices parciales | free-audit | PR3 | PR1 mergeado | M |
| C2 | `api/v1/audit.py`: POST `/v1/audit` (pipeline §5.1) + rate limit 3/IP/día | free-audit | PR3 | C1 | L |
| C3 | capture-email: validación RFC, 410 AUDIT_EXPIRED, cookie `audit_link` httpOnly | free-audit | PR3 | C2 | M |
| C4 | `services/audit_retention.py` + `POST /internal/audit/cleanup` con `AUDIT_CLEANUP_TOKEN` | free-audit | PR3 | C1 | S |
| C5 | `.github/workflows/audit-retention.yml` (cron 03:17 UTC + workflow_dispatch) | free-audit | PR3 | C4 | S |
| C6 | Tests PR3: rate limit + Retry-After, capture-email, retención, funnel events (8 tests) | free-audit | PR3 | C2–C4 | M |
| D1 | Migración 005: `recruiter_candidates`, `recruiter_candidates_cvs`, `recruiter_consent`, `recruiter_analyses`, `recruiter_audit_log` + trigger append-only | recruiter-roster | PR4 | PR1 mergeado | M |
| D2 | Modelo Recruiter: `RecruiterCandidate` + soporte | recruiter-roster | PR4 | D1 | M |
| D3 | Gate de consent: register recruiter exige ToS (422); endpoints exigen consent (403); pantalla forzada (endpoint de re-consent derivado de §6.1) | recruiter-roster | PR4 | D1 | M |
| D4 | `api/v1/recruiter.py`: CRUD candidatos (multipart PDF, 409 CANDIDATE_DUPLICATED) + audit log sha256 | recruiter-roster | PR4 | D2 | L |
| D5 | Match de candidato: reusa pipeline, persiste en `recruiter_analyses`, hook de usage (no-op hasta 007) | recruiter-roster | PR4 | D4 | M |
| D6 | `GET /v1/recruiter/candidates/ranked`: prefiltro top-K=10 HNSW, LLM N=10 paralelo, caché por hash JD, `score × exp(-d/30)` con floor 0.5 | recruiter-roster | PR4 | D5 | L |
| D7 | Tests PR4: CRUD, consent gate, duplicado, ranking (unit math), immutabilidad audit log, cross-recruiter (12 tests) | recruiter-roster | PR4 | D3–D6 | M |
| E1 | Migración 007: `subscriptions` + `stripe_webhook_events` | billing | PR5 | PR1 mergeado | M |
| E2 | Deps + config: `stripe`, `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, `FRONTEND_URL`, mapa plan→price | billing | PR5 | E1 | S |
| E3 | `services/billing.py`: checkout (Idempotency-Key, card + PSE CO), portal, catálogo con caché 5 min | billing | PR5 | E2 | L |
| E4 | `api/v1/billing.py`: plans (público), checkout (JWT + email verificado hard gate), portal (NO_CUSTOMER), subscription | billing | PR5 | E3 | M |
| E5 | `api/v1/webhooks/stripe.py`: raw body + firma + dedupe `event.id` + 4 handlers | billing | PR5 | E1 | L |
| E6 | `enforce_plan_limit` + `check_can_match` en `/v1/match` y match recruiter (402, contador en transacción) | billing | PR5 | E1, D5 | M |
| E7 | Tests PR5: idempotencia checkout, dedupe webhook, tier enforcement, 402, paridad firma (15 tests) | billing | PR5 | E4–E6 | L |
| F1 | Migración 008: ENABLE+FORCE RLS + policies en `users_cvs`, `recruiter_candidates`, `subscriptions`, `analyses`/`profiles` (owner) | cv-management | PR6 | PR2+PR4+PR5 | M |
| F2 | Integración `rls_context.py`: toda query sobre tablas RLS en transacción con `SET LOCAL`; traducción `AUTH_CONTEXT_MISSING` | authentication | PR6 | F1 | M |
| F3 | Tests PR6: cross-user SELECT/INSERT/UPDATE/DELETE por tabla, cross-role, GUC ausente, service context (10 tests) | cv-management | PR6 | F1, F2 | M |
| F4 | Canary checklist: validación manual cross-user en Neon branch antes de aplicar a prod | cv-management | PR6 | F3 | S |
| G1 | `stores/session.ts`: JWT + refresh en `localStorage`, auto-refresh <60s, `isAuthenticated`/`isRecruiter` | account-ui | PR7 | PR1–PR6 | M |
| G2 | Rehacer `api/client.ts`: Bearer JWT, refresh silencioso, 401 → `/login?reason=expired`, banner TOKEN_REUSED | account-ui | PR7 | G1 | M |
| G3 | Rutas auth: `/login`, `/register` (wizard por rol + ToS), `/verify-email` | account-ui | PR7 | G2 | M |
| G4 | Rutas CV: `/cvs` (listado), `/cvs/upload`, `/cvs/[id]` (editor estructurado) | account-ui | PR7 | G2 | L |
| G5 | Ruta `/audit` (funnel anónimo, sin auth) | account-ui | PR7 | G2 | M |
| G6 | Rutas recruiter: `/recruiter/candidates` + `[id]` + guard `isRecruiter && hasAcceptedConsent` | account-ui | PR7 | G2 | M |
| G7 | Rutas billing: `/billing/plans` + `/billing/subscription` (estados success/cancel) | account-ui | PR7 | G2 | M |
| G8 | Onboarding 3 pasos (`/onboarding/role`, `/cv`, `/match`) con paso en `localStorage` | account-ui | PR7 | G3, G4 | M |
| G9 | Historial `/history` + `/analyses/[id]`: migrar a JWT + filtro user-bound | match-ui | PR7 | G2 | S |
| G10 | CI: paridad i18n + guard `rg "PUBLIC_BACKEND_API_KEY"` en `frontend/src/` (falla si aparece) | match-ui | PR7 | G9 | S |
| G11 | Tests PR7: smoke E2E build + navegación + i18n parity (8 tests) | account-ui | PR7 | G3–G10 | M |

## Breakdown por PR

### PR1 — Auth foundation (~480 l) — authentication, user-accounts, match-analysis (mod)

- [ ] A1. Agregar `passlib[bcrypt]`, `PyJWT`, `python-multipart`, `email-validator` a `backend/pyproject.toml`
  - AC: imports sin error en CI; mypy stubs declarados.
- [ ] A2. Crear `backend/alembic/versions/003_users_and_refresh_tokens.py` (100% aditiva)
  - AC: `users` (email CITEXT, password_hash, role CHECK, verificación email), `users_refresh_tokens` (token_hash UNIQUE, consumed_at, revoked_at, índice parcial activo), `token_revocation` (jti, TTL=exp), `auth_login_attempts`, `auth_security_events`; extensión `citext` si falta; `owner_user_id` NULLable en `profiles` y `analyses` (derivado de §3.2: historial user-bound; RLS en 008); up/down validado en Neon branch.
- [ ] A3. Actualizar `backend/app/db/models.py`
  - AC: modelos `User`, `RefreshToken`, `TokenRevocation`, `LoginAttempt`, `SecurityEvent`; `Profile`/`Analysis` con `owner_user_id`; roundtrip ORM verificado.
- [ ] A4. Agregar `JWT_SECRET`, `JWT_ALGORITHM=HS256`, `JWT_ACCESS_TTL=900`, `JWT_REFRESH_TTL=2592000` a `backend/app/core/config.py`
  - AC: settings opcionales con defaults; override por env cubierto en tests.
- [ ] A5. Crear `backend/app/core/security.py`
  - AC: `hash_password`/`verify_password` (bcrypt cost 12); `create_access_token`/`create_refresh_token` (opaco 32 bytes) con `jti`; `decode_access_token` exige `exp`+`sub`.
- [ ] A6. Crear `backend/app/services/rls_context.py`
  - AC: context manager según §2.3; `user_id=None` → `app.current_user_id='0'`, `role='service'`; `SET LOCAL` (no `SET`).
- [ ] A7. Reescribir `backend/app/api/deps.py` con `get_current_user` dual + `require_role`
  - AC: JWT primero (heurística `ey`, check `jti` contra revocation), API key fallback con `compare_digest` → `CurrentUser(id=0, role="service", auth_method="api_key")`; sin credencial → 401; `require_role` rechaza `service` con 403 ROLE_FORBIDDEN; `/health` público y `/ping` por API key preservados (sin regresión MCP).
- [ ] A8. Crear `backend/app/api/v1/auth.py`
  - AC register: 201 + tokens; `EMAIL_TAKEN` 409; recruiter sin `accept_tos`/`good_faith_declaration`/`tos_version` → 422 CONSENT_REQUIRED (fila de consent se persiste desde PR4; recruiters de la ventana reciben re-consent en primer acceso, igual que cuentas pre-sprint §6.1). AC login: `INVALID_CREDENTIALS` 401 genérico; brute force → 429 RATE_LIMITED vía `auth_login_attempts`; actualiza `last_login_at`. AC refresh: rotación; expirado/revocado → 401 TOKEN_INVALID; reuso → 401 TOKEN_REUSED + revoca cadena + `auth_security_events(event='token_reuse')`. AC logout: revoca refresh + inserta jti en `token_revocation`. AC verify-email: request (JWT) + confirm (token en body, hash + expiración).
- [ ] A9. Crear `backend/app/api/v1/users.py`
  - AC: GET/PATCH `/v1/users/me`; PATCH intenta `role` → 422 ROLE_IMMUTABLE; POST `/v1/users/me/password` verifica hash actual y revoca toda la cadena de refresh.
- [ ] A10. Modificar `backend/app/api/v1/match.py` y `analyses.py`
  - AC: `/v1/match` acepta JWT (persiste `owner_user_id`) o API key (owner NULL, comportamiento actual); `GET /v1/analyses` filtra por `owner_user_id` del JWT (checks de servicio); `GET /v1/analyses/{id}` de otro user → 404; paridad de respuesta JWT vs API key.
- [ ] A11. Tests PR1 (base `backend/tests/test_dual_auth.py`, `test_auth_flow.py`, `test_users.py`)
  - AC: un test por escenario de specs authentication/user-accounts; incluye paridad dual-auth de §11.2, reuso de refresh, brute force, ROLE_IMMUTABLE; piso: 117 + ~25 = **≥142 tests en verde**.

**Tests requeridos (PR1)**: dual-auth parity (JWT válido/inválido, API key, sin credencial 401, API key en `/users/me` → 403), RBAC `require_role`, rotación y reuso de refresh, revocación por logout y cambio de password, brute-force login, register job_seeker/recruiter (ToS), verify-email happy+expirado, migración 003 up/down.

**Verificación**: `alembic upgrade head && alembic downgrade -1` (Neon branch) · `pytest backend/tests` · `mypy backend/app` · `ruff check backend` · smoke MCP contra Render con API key (sin regresión).

**Rollback**: revert PR1 + `alembic downgrade 002_add_vector_columns`. Dual auth es retrocompatible: sin PR1 el sistema sigue API-key-only.

### PR2 — CV management (~380 l) — cv-management

- [x] B1. Agregar `pypdf`, `pdfminer.six` a `backend/pyproject.toml`.
- [x] B2. Crear `backend/alembic/versions/004_users_cvs.py`
  - AC: `users_cvs` según §2.1 (BYTEA, raw_text, structured JSONB, embedding vector(1024), HNSW `vector_cosine_ops`); `CREATE INDEX CONCURRENTLY` donde sea posible; up/down en Neon branch.
- [x] B3. Agregar modelo `UserCV` a `backend/app/db/models.py`.
- [x] B4. Crear `backend/app/services/pdf_parser.py`
  - AC: lectura en chunks de 64KB; `pypdf.PdfReader(strict=False)`; `MemoryError`/excepción → retry `pdfminer.six`; ambos fallan → `PDFParseFailed` (503 PDF_PARSE_FAILED) sin persistir nada.
- [x] B5. Crear `backend/app/api/v1/cvs.py` (CRUD completo)
  - AC POST: Content-Length >10MB → 413 FILE_TOO_LARGE; Content-Type ≠ pdf → 415; sin texto extraíble → 422 PDF_NO_TEXT; guarda blob+texto+structured con checks de servicio `owner_user_id`. AC GET: listado y detalle sólo propios (cross-user → 404). AC PATCH: editor estructurado, `last_edited_at`, `ROLE_IMMUTABLE` no aplica (sin role). AC DELETE: 204 + CASCADE lógico.
- [ ] B6. Re-cálculo de embedding en PATCH (tarea B6 de B5)
  - AC: recalc en background tras PATCH (no bloquea 200); cliente recibe `last_edited_at` inmediato; embedding vigente en próximo match. (DEFERRED - background tasks out of scope for MVP)
- [x] B7. Tests PR2 (`backend/tests/test_cvs.py`, `test_pdf_parser.py`, `test_cv_storage.py`)
  - AC: un test por escenario del spec cv-management; incluye cross-user 404 a nivel servicio (RLS cubierto en PR6); piso: **≥154 tests**.

**Tests requeridos (PR2)**: upload happy path, 413, 415, PDF_NO_TEXT 422, PDF_PARSE_FAILED 503 (mock de doble fallo), CRUD own-only, cross-user 404, PATCH editor + re-cálculo embedding, migración 004 up/down, fallback pdfminer sobre PDF patológico.

**Verificación**: `alembic upgrade head && alembic downgrade -1` (Neon branch) · `pytest backend/tests -k "cv or parser"` · `pytest backend/tests` · `mypy backend/app` · `ruff check backend`.

**Rollback**: revert PR2 + `alembic downgrade 003_users_and_refresh_tokens`. Migración aditiva, sin pérdida de datos.

### PR3 — Free audit (~280 l) — free-audit

- [ ] C1. Crear `backend/alembic/versions/006_audit_uploads_and_funnel.py`
  - AC: `audit_uploads` (audit_funnel_id UUID UNIQUE, ip_hash, jd_text, pdf_blob, result JSONB, email_captured, linked_user_id, expires_at) + índices parciales `idx_audit_expires`/`idx_audit_linked`; `audit_funnel_events`; sin RLS (anónima).
- [ ] C2. Crear `backend/app/api/v1/audit.py` — `POST /v1/audit`
  - AC: pipeline §5.1 completo en orden: jd_text <50 → 422 JD_TOO_SHORT; Content-Type → 415; >10MB → 413; rate limit 3/IP/día (contador sobre `audit_uploads` exitosos por `ip_hash`) → 429 con `Retry-After`; INSERT + `SET LOCAL` modo servicio; parse streaming; fallo → 503 + ROLLBACK; respuesta 200 con `Cache-Control: no-store` y `X-Robots-Tag: noindex`.
- [ ] C3. Agregar `POST /v1/audit/{audit_id}/capture-email`
  - AC: RFC 5322 → 422 EMAIL_INVALID; >1h → 410 AUDIT_EXPIRED; UPDATE `email_captured`; setea cookie `audit_link` httpOnly (Max-Age 30d, SameSite=Lax, Secure); envía email con HTML del análisis + CTA `/register?ref=audit_<id>`; 202.
- [ ] C4. Crear `backend/app/services/audit_retention.py` + endpoint interno
  - AC: `delete_expired()` ejecuta DELETE con `linked_user_id IS NULL AND expires_at < NOW()` RETURNING id y emite `audit_funnel_events(step='audit_purged')`; `POST /internal/audit/cleanup` valida `AUDIT_CLEANUP_TOKEN` con `compare_digest`; path excluido del router de API key (token propio).
- [ ] C5. Crear `.github/workflows/audit-retention.yml`
  - AC: `cron: '17 3 * * *'` + `workflow_dispatch`; curl con bearer desde secrets (`AUDIT_CLEANUP_TOKEN`); job loguea resultado.
- [ ] C6. Tests PR3 (`backend/tests/test_audit.py`, `test_audit_rate_limit.py`)
  - AC: rate limit con `freezegun` (3×200 + 429 con Retry-After), capture-email (410, 422, 202), PDF inválido → 422 PDF_INVALID, retención (sólo borra no vinculadas), funnel events, cookie audit_link; piso: **≥162 tests**.
- [x] C7. Extensión de scope por el owner (post-commit): upload de PDF en la auditoría anónima — `POST /v1/audit/anonymous` pasa a multipart con `cv_file` (PDF ≤ 10 MB → 415/413/422 PDF_NO_TEXT/503 PDF_PARSE_FAILED, semántica igual a `POST /v1/cvs`) o `cv_text` (exactamente uno requerido → 422 CV_REQUIRED / CV_TOO_SHORT); respuesta, audit_token, rate limit, retención y RLS sin cambios
  - AC: tests en `tests/test_audit.py` (PDF válido 200+token, escaneado 422, oversized 413, .txt 415, basura 503, sin CV 422, cv_text corto 422, rate limit 429 en file path).
- [x] C8. Extensión de scope por el owner (post-commit): UI `/audit` con modo "Subir PDF" (default) / "Pegar texto", input `accept=".pdf"` con nombre+tamaño y pre-check 10MB client-side, mapeo de errores 413/415/422/503 vía i18n (es+en); resto del funnel (Retry-After, email capture, CTA signup) sin cambios
  - AC: tests de store (`audit.test.ts`: envía `cv_file`, no `cv_text`; 422 expone `errorCode`) y de página (`audit-page.test.ts`: multipart con file, render de error PDF_NO_TEXT); paridad i18n OK.

**Tests requeridos (PR3)**: rate limit 3/IP/día + Retry-After, JD_TOO_SHORT, 415, 413, parse fail → 503 sin persistir, capture-email (202/410/422), cleanup sólo expiradas no vinculadas, emisión de funnel events.

**Verificación**: `alembic upgrade head && alembic downgrade -1` (Neon branch) · `pytest backend/tests -k "audit or rate_limit"` · `pytest backend/tests` · `mypy backend/app` · `ruff check backend` · `act` o dispatch manual del workflow (smoke).

**Rollback**: revert PR3 + `alembic downgrade` de 006; deshabilitar workflow en GitHub (sin cron → sin llamadas).

### PR4 — Recruiter roster (~320 l) — recruiter-roster

- [x] D1. Crear `backend/alembic/versions/005_recruiter_candidates.py`
  - AC: 5 tablas de §6 (candidates, candidates_cvs, consent, analyses, audit_log); índice único `(recruiter_id, COALESCE(email,''))`; trigger `reject_modification` BEFORE UPDATE/DELETE en `recruiter_audit_log`; up/down en Neon branch.
- [x] D2. Agregar modelos Recruiter a `backend/app/db/models.py`.
- [x] D3. Implementar gate de consent
  - AC: endpoints de roster exigen `recruiter_consent.accepted_at IS NOT NULL` → 403 CONSENT_REQUIRED; recruiters creados entre merge de PR1 y PR4 (y cuentas pre-sprint) quedan cubiertos por el flujo de re-consent §6.1; exponer envío de consent desde la pantalla forzada (endpoint `POST /v1/recruiter/consent`, adición mínima derivada de §6.1).
- [x] D4. Crear `backend/app/api/v1/recruiter.py` — CRUD candidatos
  - AC: `require_role("recruiter")` + consent; multipart PDF ≤10MB con mismo validador de PR2; INSERT cvs + candidate en transacción; `recruiter_audit_log(action='candidate_added', sha256(pdf_bytes))`; email duplicado → 409 CANDIDATE_DUPLICATED; listado paginado `page/page_size` con `last_analysed_at`; DELETE con CASCADE a analyses y cvs.
- [x] D5. Agregar `POST /v1/recruiter/candidates/{id}/match`
  - AC: reusa pipeline de match con CV del candidato; persiste en `recruiter_analyses`; incrementa usage en `subscriptions` si la tabla existe (hook no-op hasta PR5; enforcement 402 formal llega en PR5).
- [x] D6. Agregar `GET /v1/recruiter/candidates/ranked`
  - AC: prefiltro top-10 por similitud HNSW; N=10 LLM en paralelo con semáforo asyncio; caché por hash de JD; `effective_score = match_score × exp(-días/30)`; floor `0.5 × match_score` si `match_score ≥ 0.7`; orden descendente; respuesta indica "top 10 de N" si hay más.
- [x] D7. Tests PR4 (`backend/tests/test_recruiter.py`, `test_ranking.py`)
  - AC: CRUD, consent gate (403), duplicado (409), math de ranking con fixtures deterministas, immutabilidad del audit log (UPDATE/DELETE → excepción), cross-recruiter isolation a nivel servicio; piso: **≥174 tests**.

**Tests requeridos (PR4)**: CRUD own-only, consent gate, CANDIDATE_DUPLICATED, ranking (prefiltro, decay, floor, orden), trigger append-only, audit log sha256, delete en cascada, paginación.

**Verificación**: `alembic upgrade head && alembic downgrade -1` (Neon branch) · `pytest backend/tests -k "recruiter or ranking or consent"` · `pytest backend/tests` · `mypy backend/app` · `ruff check backend`.

**Rollback**: revert PR4 + `alembic downgrade` de 005 (drop tablas roster; users intactos).

### PR5 — Billing (~380 l) — billing

- [x] E1. Crear `backend/alembic/versions/007_subscriptions_payments.py`
  - AC: `subscriptions` (plan_id, status CHECK, stripe_customer_id, stripe_subscription_id UNIQUE, período, usage_matches_this_month) + índice parcial activo; `stripe_webhook_events` (event_id PK, type, payload, processed_at); up/down en Neon branch.
- [x] E2. Agregar `stripe` a deps y `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, `FRONTEND_URL`, `PLAN_TO_PRICE_ID` a `backend/app/core/config.py`.
- [x] E3. Crear `backend/app/services/billing.py`
  - AC: `create_checkout` según §7.2 (card y PSE con `payment_method_options.country=CO`, metadata user_id/plan_id, `idempotency_key`, success/cancel URL); portal de facturación; catálogo desde `stripe.Price.list` con caché en memoria 5 min invalidable por `price.updated`; sin dependencia de FastAPI.
- [x] E4. Crear `backend/app/api/v1/billing.py`
  - AC: `GET /v1/billing/plans` público; `POST /v1/billing/checkout` JWT + hard gate `email_verified_at IS NOT NULL` (403 si no verificado); `POST /v1/billing/portal` sin customer → 400 NO_CUSTOMER; `GET /v1/billing/subscription` del propio user.
- [x] E5. Crear `backend/app/api/v1/webhooks/stripe.py`
  - AC: raw body con `await request.body()` ANTES de cualquier parseo; firma `construct_event` → 400 si falla; dedupe INSERT `ON CONFLICT DO NOTHING` → duplicado responde 200 sin procesar; handlers: `checkout.session.completed` (upsert active), `customer.subscription.deleted` (canceled), `invoice.payment_failed` (past_due), `customer.subscription.updated` (períodos); `processed_at` al final; montado sin auth dependency y `include_in_schema=False`.
- [x] E6. Agregar `enforce_plan_limit` + `check_can_match` a `backend/app/services/billing.py` y conectar en `/v1/match` y match recruiter
  - AC: free job_seeker 3/mes; recruiter sin plan 0; exceeded → 402 PLAN_LIMIT_REACHED; contador se incrementa dentro de la transacción del match antes de COMMIT.
- [x] E7. Tests PR5 (`backend/tests/test_billing.py`, `test_stripe_idempotency.py`, `test_stripe_webhook.py`)
  - AC: escenarios §11.2 (checkout idempotente misma URL, webhook dedupe 1 fila, firma inválida 400, raw body preservado) + tier enforcement 402 + hard gate email; mocks de SDK Stripe; piso: **≥189 tests**.

**Tests requeridos (PR5)**: idempotencia checkout (misma Idempotency-Key → misma URL), webhook dedupe por event.id, firma inválida → 400, handlers de 4 eventos, PLAN_LIMIT_REACHED 402, NO_CUSTOMER 400, gate de email verificado, contador atómico en transacción.

**Verificación**: `alembic upgrade head && alembic downgrade -1` (Neon branch) · `pytest backend/tests -k "billing or stripe or webhook"` · `pytest backend/tests` · `mypy backend/app` · `ruff check backend` · `stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe` (smoke sandbox).

**Rollback**: revert PR5 + `alembic downgrade` de 007. Stripe en test mode hasta validar webhooks; si se revierte en prod, `/v1/billing/checkout` → 503 y el handler de webhook captura tabla ausente respondiendo 200 (evita retries infinitos, §9.3). Sin downgrade de datos en Stripe.

### PR6 — RLS policies (~120 l) — cv-management, authentication (RLS), recruiter-roster, billing

- [x] F1. Crear `backend/alembic/versions/008_rls_policies.py` (ÚLTIMA migración del sprint) — aplicada como `011_rls_policies.py` en la numeración real (megas PR)
  - AC: `ENABLE` + `FORCE ROW LEVEL SECURITY` y policies select/insert/update/delete por tabla: `users_cvs` (owner_user_id), `recruiter_candidates` (recruiter_id), `subscriptions` (user_id), `analyses`/`profiles` (owner_user_id, decisión #2 del design); patrón uniforme §2.2 con GUC `app.current_user_id`/`app.current_role`; tablas anónimas/append-only sin RLS; migraciones de datos documentadas con rol BYPASSRLS; up/down validado en Neon branch.
  - Nota apply: migración real = `011_rls_policies.py`. Bypass único = GUC `app.current_user_id='0'` (service id=0; MCP/cron/webhook). `profiles` y `users` SIN RLS en esta migración — razón documentada en el docstring (login/signup sin contexto; profiles aún sin owner en su create-path). GUC de rol renombrado a `app.user_role` (`current_role` es keyword reservada de PG). Downgrade verificado por `test_migrations`.
- [x] F2. Integrar `rls_context.py` en los servicios que tocan tablas RLS
  - AC: toda query sobre tablas con RLS corre en transacción explícita con `SET LOCAL`; error `AUTH_CONTEXT_MISSING` se traduce antes de propagar (500 controlado); modo servicio (API key/free-audit) usa contexto `id=0/service` según §2.3.
  - Nota apply: `rls_context.py` reescrito con helpers async (`set_rls_user/service/anonymous`, `bind_rls_context`); deps nuevos `get_db`/`get_db_optional`; wiring en cvs, recruiter (candidates/consent/gate), billing, match (4 sesiones + `owner_user_id` persistido en analyses), analyses (filtro servicio owner + 404), audit (anonymous/service), stripe webhook (service), auth register (consent vía service), tier_limits (re-bind tras commit interno).
- [x] F3. Tests PR6 (`backend/tests/test_rls.py`)
  - AC: escenarios §11.2 — cross-user SELECT/INSERT/UPDATE/DELETE por tabla, cross-role (recruiter no ve cvs de job_seeker), GUC ausente → error manejado, service context no lee filas de usuarios; piso: **≥199 tests**.
  - Nota apply: 15 tests en `tests/test_rls.py` — aislamiento DB-level vía `SET ROLE` a rol NOBYPASSRLS (superusers bypasean RLS; rol creado en conftest), endpoints 404-no-403 con JWT real, bypass service, auditoría anónima, cron cleanup, control positivo owner, default-deny sin GUC.
- [ ] F4. Ejecutar canary checklist
  - AC: validación manual cross-user en Neon branch sin filtración de datos antes de aplicar a producción; checklist documentado en la descripción del PR.

**Tests requeridos (PR6)**: aislamiento RLS por operación (SELECT/INSERT/UPDATE/DELETE) y por tabla, cross-role, contexto ausente, FORCE RLS (owner también respeta), integración `rls_context` end-to-end vía API.

**Verificación**: `alembic upgrade head && alembic downgrade -1` (Neon branch) · `pytest backend/tests -k "rls or isolation"` · `pytest backend/tests` · `mypy backend/app` · `ruff check backend` · canary manual en Neon (F4).

**Rollback**: revert PR6 + `alembic downgrade 007_subscriptions_payments` (drop policies/triggers). Los checks de servicio de PR2/PR4/PR5 siguen protegiendo (defense in depth). Puede entrar como hotfix posterior si se atrasa (§13.4).

### PR7 — Frontend (~450 l) — account-ui, match-ui (mod)

- [x] G1. Crear `frontend/src/lib/stores/session.ts`
  - AC: interface `Session` §8.1; persistencia en `localStorage` clave `asistcv.session`; `isAuthenticated`/`isRecruiter` derivados; `startSessionRefresh` proactivo si faltan <60s para expirar.
  - Nota apply: sesión con access+refresh+user+expiresAt (exp decodificado del JWT con fallback 15 min); refresh single-flight; helpers `requireSession`/`requireRole`; onboarding 3 pasos y audit-token pendiente también viven acá.
- [x] G2. Rehacer `frontend/src/lib/api/client.ts`
  - AC: Bearer JWT desde la sesión (sin API key build-time); refresh silencioso en 401 y reintento único; 401 definitivo → limpia sesión y `goto('/login?reason=expired')`; 401 con TOKEN_REUSED → banner "Tu sesión fue invalidada por seguridad".
  - Nota apply: base URL desde `PUBLIC_API_URL` (`$lib/api/base`, fallback dev `http://localhost:8000`); reintento único verificado en tests; TOKEN_REUSED → `sessionEvent` → banner en /login.
- [x] G3. Crear rutas `/login`, `/register` (wizard por rol con ToS recruiter), `/verify-email`
  - AC: register recruiter exige ToS; banner persistente de verificación (soft gate); login redirige por rol.
  - Nota apply: registro implementado en `/signup` (scope cerrado del orquestador); ToS + declaración de buena fe obligatorios para recruiter (checkboxes → submit bloqueado); login redirige por rol (recruiter→/recruiter, seeker→/profile). `/verify-email` diferida (backend es stub 202 sin envío real).
- [x] G4. Rutas CV: `/cvs` (listado), `/cvs/upload`, `/cvs/[id]` (editor estructurado)
  - AC: upload PDF ≤10MB con mensajes de 413/415/422/503 localizados; editor guarda vía PATCH con `last_edited_at`.
  - Nota apply: consolidado en `/profile` (scope cerrado): listado + upload PDF + editor estructurado (componente `CvStructuredForm`) + delete + match contra JD con 402→upsell. Mensajes 413/415/422/503 localizados vía `apiErrorMessage`.
- [x] G5. Crear ruta `/audit` (pública, sin auth)
  - AC: JD + PDF sin sesión; 429 muestra Retry-After; capture-email tras resultado.
  - Nota apply: funnel con CV texto (multipart admite `cv_text` además de PDF); 429 con Retry-After (minutos); capture-email opcional al final; CTA a `/signup` con claim automático vía audit token persistido.
- [x] G6. Crear rutas `/recruiter/candidates` + `/recruiter/candidates/[id]`
  - AC: guard `isRecruiter && hasAcceptedConsent`; 403 CONSENT_REQUIRED → pantalla de consent forzada; ranked con aviso "top 10 de N".
  - Nota apply: consolidado en `/recruiter` (scope cerrado): guard `requireRole('recruiter')`, consent gate con re-consent (POST `/v1/recruiter/consent`), roster CRUD, match por candidato, ranked con aviso truncado/full.
- [x] G7. Crear rutas `/billing/plans` + `/billing/subscription`
  - AC: catálogo desde `/v1/billing/plans`; checkout con Idempotency-Key generado; estados `?status=success/cancel`; bloqueo si email no verificado.
  - Nota apply: consolidado en `/billing` (scope cerrado): plan+usage actual, cards con selector card/PSE, checkout redirect (Idempotency-Key), portal con NO_CUSTOMER → prompt, 403 → mensaje de verificar email.
- [x] G8. Onboarding 3 pasos
  - AC: paso actual en `localStorage` (`asistcv.onboarding_step`); al completar paso 3, remove + redirect.
  - Nota apply: wizard inline en `/profile` (scope cerrado) — paso 1 rol, paso 2 CV (upload o editor), paso 3 match; step persistido en `asistcv.onboarding_step`; flag activo en `asistcv.onboarding` desde el registro.
- [x] G9. Migrar `/history` y `/analyses/[id]` a JWT
  - AC: historial user-bound con el JWT; sin API key en runtime.
  - Nota apply: sin cambios de código — `historyStore`/`apiClient` ya viajan sobre el client nuevo (Bearer JWT, sin API key). `/profile` ejecuta match user-bound.
- [x] G10. CI: paridad i18n + guard de API key
  - AC: `rg "PUBLIC_BACKEND_API_KEY" frontend/src/` falla si encuentra literal en runtime.
  - Nota apply: step "Guard - no build-time API key in frontend source" en el job `frontend-i18n-parity` (renombrado); guard equivalente también en `scripts/check-env.mjs` (prebuild). El literal no aparece en `src/` (ni en comentarios).
- [x] G11. Tests PR7 (smoke frontend)
  - AC: build genera sitio estático; navegación de rutas nuevas; paridad i18n; guardas de ruta; piso: +8 tests frontend.
  - Nota apply: vitest + jsdom + @testing-library/svelte agregados (devDeps). 25 tests: session store (6), api client Bearer/refresh-retry (5), signup consent-gate componente (3), reglas signup/password/redirect (6), auditStore funnel (5). i18n parity cubierta por script CI.

**Tests requeridos (PR7)**: smoke E2E de build, navegación login → cvs → match, guardas de ruta por rol/consent, refresh silencioso, banner TOKEN_REUSED, paridad i18n, guard de API key.

**Verificación**: `npm run build && npm run check && npm run test` (frontend/) · `rg "PUBLIC_BACKEND_API_KEY|BACKEND_API_KEY" frontend/src/` (debe fallar/vacío en runtime) · flujo manual contra staging: registro → CV → match → audit → billing sandbox.

**Rollback**: revert PR7 + re-deploy del frontend pre-Sprint 2 con `PUBLIC_BACKEND_API_KEY` (API key del backend sigue activa; sin pérdida).

## Dependencias entre PRs

```
PR1 (gate universal)
 ├──► PR2 (users_cvs)
 ├──► PR3 (audit — independiente del resto)
 ├──► PR4 (roster)
 └──► PR5 (billing)
PR2 + PR4 + PR5 ──► PR6 (RLS, ÚLTIMA migración: policies asumen columnas de 003–007)
PR1–PR6 ──► PR7 (frontend consume API completa deployada)
```

- PR2, PR3, PR4, PR5 son **paralelos** tras PR1: tablas y endpoints no colisionan.
- PR6 requiere las tres tablas user-owned existentes (por eso es la migración final).
- PR7 requiere backend completo en staging; usa `PUBLIC_BACKEND_URL` (no API key).
- Estrategia **stacked-to-main**: cada PR mergea a main en orden de dependencias; PR2–PR5 rebase sobre main fresco antes de review (riesgo #1 del design).

## Forecast de líneas por PR vs budget 600

| PR | Contenido | Código | Tests | Migración | Total est. | Budget 600 | Margen |
|---|---|---|---|---|---|---|---|
| PR1 | Auth foundation | ~230 | ~170 | ~80 | ~480 | OK | ~120 |
| PR2 | CV management | ~180 | ~130 | ~70 | ~380 | OK | ~220 |
| PR3 | Free audit | ~130 | ~90 | ~60 | ~280 | OK | ~320 |
| PR4 | Recruiter roster | ~160 | ~110 | ~50 | ~320 | OK | ~280 |
| PR5 | Billing | ~190 | ~140 | ~50 | ~380 | OK | ~220 |
| PR6 | RLS policies | ~30 | ~70 | ~20 | ~120 | OK | ~480 |
| PR7 | Frontend | ~330 | ~90 | — | ~450 | OK | ~150 |
| **Total** | | **~1250** | **~800** | **~330** | **~2410** | 7 PRs | Ningún PR excede 600 |

PRs por encima de la guard default de 400 (pero dentro del budget del proyecto): **PR1 (~480l)** y **PR7 (~450l)**. Ninguno requiere `size:exception`.

## Decisión antes de apply

- **No se requiere `size:exception`**: los 7 PRs quedan bajo `review_budget_lines=600` (config.yaml). Máximo: PR1 ~480l.
- Estrategia cerrada en session preflight: **auto-chain** con **stacked-to-main** → el orquestador procede con PR1 sin decisión adicional del usuario.
- Si en apply algún PR proyectara superar 600l, el fallback documentado es scope-trim (§13.1: diferir PSE, ranking híbrido o editor estructurado) — no aumentar el PR.

## Riesgos de ejecución (heredados del design §12, con task de mitigación)

1. Drift entre merges paralelos (PR2–PR5) → rebase sobre main antes de cada review.
2. Policy RLS mal escrita expone CVs → F3 exhaustivo + canary F4 en Neon antes de prod.
3. Dual auth rompe MCP → A11 paridad + smoke MCP post-merge de PR1 (API key intacta).
4. pypdf OOM en Render 512MB → B4 streaming + fallback + hard cap 10MB.
5. Webhooks duplicados → E5 dedupe por `event.id` (UNIQUE).
6. Ventana de consent PR1→PR4 (recruiters sin fila de consent) → mismo tratamiento que cuentas pre-sprint: 403 CONSENT_REQUIRED + re-consent en primer acceso (D3).
7. Cron de retención falla en silencio → log del job + monitor de `audit_uploads` expiradas >48h (post-apply).
8. Reintroducción accidental de API key en frontend → guard G10 en CI.

## Notas para apply

- El piso de 117 tests de Sprint 1 es sagrado: ningún PR puede dejar tests rojos; piso final del sprint ≥199 backend + 8 frontend.
- Los snapshot de prompts de Sprint 1 quedan congelados; si el pipeline match cambia de prompt, actualizar snapshot explícitamente en el mismo PR.
- Migraciones 003–007 son aditivas; 008 (RLS) usa FORCE y exige validar up/down en Neon branch antes de cada merge.
- Micro-delta detectado para verify (no se editan specs en esta fase): el endpoint de envío de consent (`POST /v1/recruiter/consent`, D3) y las columnas `owner_user_id` en `profiles`/`analyses` (A2) se derivan de §6.1 y §3.2 del design; confirmar cobertura en specs al sincronizar.
