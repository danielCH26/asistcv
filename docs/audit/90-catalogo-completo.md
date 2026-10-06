# Catálogo completo de hallazgos (apéndice)

> Referencia compacta del resto de la auditoría. Los 9 hallazgos del plan de ataque están desarrollados en [`00-hallazgos.md`](./00-hallazgos.md) y **no** se repiten aquí. Los IDs `A1`, `A2`, … son estables y citables.
>
> Misma regla de evidencia: análisis estático por lectura de código, referencias `file:line` verificadas, **sin ejecución contra un sistema corriendo**.

## Leyenda de severidad

| Nivel | Significado |
|---|---|
| P0 | Seguridad o feature core rota |
| P1 | Correctness / integridad |
| P2 | Mantenibilidad / deuda |
| P3 | Cosmético |

---

## Seguridad / auth (adicional)

| ID | Descripción | Ubicación | Sev. |
|---|---|---|---|
| A1 | Logout revoca el refresh token de **cualquier** usuario: el `UPDATE` filtra solo por `token_hash`, sin chequeo de ownership, así que cualquier principal con service key puede revocar la sesión de otro | `backend/app/api/v1/auth.py:321-344` | P0 |
| A2 | `token_revocation` es tabla muerta: la blacklist de access tokens existe en el schema pero nunca se consulta al validar un token | `backend/app/models.py:238-252`; `backend/app/api/v1/auth.py:341-342` | P1 |
| A3 | `auth_login_attempts` no tiene índice sobre `(email, attempted_at)`, que es exactamente la clave del rate limit de login | `003:90-99` vs `backend/app/api/v1/auth.py:41-46` | P1 |
| A4 | Rate limit de login indexa solo por email, sin dimensión de IP; además un login exitoso no limpia la ventana | `backend/app/api/v1/auth.py:36-54` | P1 |
| A5 | Consent gate no compara `tos_version` contra `CURRENT_TOS_VERSION`; el endpoint de aceptación confía en el `body.tos_version` declarado por el cliente | `backend/app/services/consent_gate.py:50`; `backend/app/api/v1/recruiter_consent.py:20,69` | P1 |
| A6 | Las rutas de candidates del recruiter no exigen `require_role("recruiter")` (a diferencia de las de consent) y `check_recruiter_consent` deja pasar a no-recruiters | `backend/app/main.py:204-208` vs `:197-201`; `backend/app/services/consent_gate.py:39-40` | P1 |
| A7 | La tabla `profiles` **no** tiene RLS y los GET/PATCH de perfil no validan ownership del registro | `backend/app/models.py`; `backend/app/api/v1/profiles.py:165,175` | P0 |
| A8 | CORS con `allow_credentials=True` combinado con un `cors_origins` que `.env.example` sugiere configurar como `["*"]` → CORS abierto con credenciales | `backend/app/main.py:74-80`; `backend/.env.example:31-38` | P0 |
| A8b | **La guía de troubleshooting de `DEPLOY.md` indica `CORS_ORIGINS` en formato CSV (comma-separated)**, pero `config.py` lo exige como **array JSON** y lo advierte explícitamente en el docstring del módulo. Seguir `DEPLOY.md:111-113` en producción rompe el parseo de CORS (el origen del frontend Cloudflare Pages no se aplica o el arranque falla). La guía correcta está en `backend/.env.example`. | `docs/DEPLOY.md:111-113` vs `backend/app/core/config.py:4-9,22-24`; `backend/.env.example` | P1 |
| A9 | El rate limit del audit anónimo se indexa por `X-Forwarded-For`, header controlado por el cliente, y sin allowlist de proxies de confianza; si `ip is None` el límite no se aplica | `backend/app/api/v1/audit.py:50-55`; `backend/app/services/audit_rate_limit.py:57-59` | P1 |
| A10 | `hash_ip` es SHA-256 sin salt: el espacio de IPv4 es enumerable por fuerza bruta, así que el "anonimato" del funnel es reversible | `backend/app/services/audit_token.py:62-74` | P1 |
| A11 | `Retry-After` siempre devuelve ~0 por aritmética de ventana incorrecta | `backend/app/services/audit_rate_limit.py:66-68` | P2 |
| A12 | El rate limit del audit es check-then-insert sin serialización: requests concurrentes exceden el tope de 3/día | `backend/app/api/v1/audit.py:149` vs `:223` | P1 |
| A13 | `POST /v1/auth/verify-email/request` y `/confirm` son ambos stubs: no se envía email y `/confirm` responde 200 incondicionalmente | `backend/app/api/v1/auth.py:347-368` | P0 |

---

## Correctness / confiabilidad

| ID | Descripción | Ubicación | Sev. |
|---|---|---|---|
| A14 | El contexto RLS con `SET LOCAL` se pierde en cada `commit()`, y varios handlers hacen commit y luego releen tablas protegidas por RLS (cvs, adaptations, recruiter_consent, recruiter_candidates) — enmascarado en tests por el hook global de service | varios handlers; ver T1 | P1 |
| A15 | El índice único parcial de adaptaciones deja filas atascadas en `pending` en repeticiones y concurrencia | `015:111-121`; `adaptation_runner.py:318` (detalle en F3) | P1 |
| A16 | Cache de adaptaciones inválida: `cv_adaptations` no tiene `content_version` y la clave de cache hashea solo `jd_text[:500]`, así que dos JDs con prefijo compartido colisionan | `backend/app/services/adaptation_cache.py:4-16,51,64` | P1 |
| A17 | `candidate_ranking` ignora su argumento `jd_text` y hace N+1 queries; el docstring promete un pre-filtro por embedding que no existe | `backend/app/services/candidate_ranking.py:60-117`; `backend/app/api/v1/recruiter_candidates.py:256` | P1 |
| A18 | `profile.embedding` se calcula pero nunca se usa para ranking, y hay 4 índices vectoriales HNSW creados que **nunca se consultan** (no hay `<=>` ni `ORDER BY embedding` en ningún lado): la retrieval es numpy en proceso | `backend/app/models.py`; migraciones `002`/`004`; `backend/app/services/retrieval.py` | P1 |
| A19 | Groq duerme en el último retry antes de lanzar la excepción, y no reintenta 5xx; HuggingFace reintenta 4 veces con sleeps un mismatch de dimensión | `backend/app/services/groq_provider.py:291,300`; `backend/app/services/huggingface_provider.py:89-93,109` | P2 |
| A20 | El SDK sync de Stripe se llama dentro de `async def`, bloqueando el event loop | `backend/app/services/stripe_client.py:26,87,106` | P1 |
| A21 | El webhook de Stripe no es atómico entre 3 sesiones: un crash puede reproducir el side effect; además el prefijo `/api/v1` está hardcodeado sin relación con `API_PREFIX` | `backend/app/api/webhooks/stripe.py:45-86`; `backend/app/main.py:225` | P1 |
| A22 | Datetimes naive/aware mezclados: defaults de modelo con `datetime.utcnow` vs escrituras de servicio con `datetime.now(UTC)` — ya requirió un parche defensivo | `backend/app/models.py` (múltiples); `backend/app/api/v1/audit.py:289,457` | P1 |
| A23 | `NullPool` en todas partes: nuevo handshake TCP+TLS por request, sin pooling | `backend/app/db/session.py:55` | P2 |
| A24 | `get_llm_provider` con `@lru_cache` lanza excepción por keys faltantes en el **primer uso**, produciendo 500 en request en lugar de fallar en el arranque | `backend/app/services/factory.py:14,34-43` | P2 |
| A25 | Parseo de PDF y audit: los parámetros `session` / `pdf_bytes` de `run_audit` no se usan, y el docstring promete streaming de 64KB mientras el archivo entero se lee en memoria | `backend/app/services/audit_runner.py:46-51`; `backend/app/services/pdf_parser.py:3-5` | P2 |

---

## Datos / privacidad

| ID | Descripción | Ubicación | Sev. |
|---|---|---|---|
| A26 | Texto completo del CV + JD + perfil se envían a Groq y HuggingFace sin redacción de PII | `backend/app/services/groq_provider.py:250-259`; `backend/app/services/huggingface_provider.py`; `backend/app/api/v1/cvs.py:211-222` | P1 |
| A27 | Tokens de sesión (access y refresh) guardados en `localStorage` en texto plano, sin `httpOnly` | `frontend/src/lib/stores/session.ts:15,64-71` | P1 |
| A28 | El funnel público de audit queda expuesto también en la raíz por el montaje duplicado del router (detalle en S4) | `backend/app/main.py:186-194` | P0 |
| A29 | `audit_uploads` almacena el PDF crudo como BYTEA (10MB) más el texto del CV durante 30 días; `cv_adaptations` guarda el texto de la JD sin cifrar pese al nombre de columna `jd_text_encrypted` | `backend/app/api/v1/audit.py`; `backend/app/api/v1/adaptations.py:271` | P1 |

---

## Frontend UX / estado

| ID | Descripción | Ubicación | Sev. |
|---|---|---|---|
| A30 | Las rutas `/history` y `/history/[id]` no tienen session guard (solo `/profile`, `/recruiter`, `/billing` lo tienen) | `frontend/src/routes/history/+page.svelte`; `frontend/src/routes/history/[id]/+page.svelte` | P1 |
| A31 | `CvStructuredForm` recibe un prop `initial` que nunca se le pasa → editar el CV abre un formulario vacío y enviarlo sobrescribe con blancos | `frontend/src/lib/components/CvStructuredForm.svelte:11`; `frontend/src/routes/profile/+page.svelte:305,328` | P0 |
| A32 | `editorOpen` en la página de perfil se escribe pero nunca se lee | `frontend/src/routes/profile/+page.svelte:29` | P3 |
| A33 | `apiClient.linkAudit` es código muerto; `session.ts:claimPendingAudit` lo reimplementa inline y **no** manda header `Authorization` | `frontend/src/lib/api/client.ts:284-290`; `frontend/src/lib/stores/session.ts:227-245` | P1 |
| A34 | `POST /v1/audit/anonymous` pasa por el path de cliente **autenticado** (sin `{auth:false}`), así que una sesión stale puede provocar un 401 que limpia un audit anónimo válido | `frontend/src/lib/api/client.ts:260-274,102` | P1 |
| A35 | 4 copias duplicadas del mapa error-code → i18n en 4 archivos distintos; `POLL_TIMEOUT` existe solo en el frontend | `frontend/src/routes/audit/+page.svelte:52-65`; `frontend/src/routes/profile/+page.svelte:108-123,221-238`; `frontend/src/routes/recruiter/+page.svelte:48-61`; `frontend/src/lib/stores/adaptation.ts:53` | P2 |
| A36 | `TOS_VERSION` hardcodeada en dos lugares | `frontend/src/lib/auth/rules.ts:8`; `frontend/src/routes/recruiter/+page.svelte:14` | P2 |
| A37 | Las URLs de success/cancel/portal de billing apuntan a `/billing/subscription` y `/billing/plans`, que no existen (la ruta real es `/billing`) → Stripe redirige a un soft 404 bajo el fallback adapter-static | `backend/app/api/v1/billing.py:181-182,227` | P1 |
| A38 | Las filas de `HistoryList` no son navegables y `onSelect` no se usa → `/history/[id]` solo es alcanzable vía el redirect post-signup | `frontend/src/lib/components/HistoryList.svelte:6`; `frontend/src/routes/signup/+page.svelte:51` | P2 |
| A39 | `startSessionRefresh` instala un intervalo de 30s imparable, sin `clearInterval` exportado | `frontend/src/lib/stores/session.ts:306-311` | P2 |
| A40 | El adapter MCP loguea los argumentos completos de las tools (incluida la JD entera) en DEBUG, y `_sanitize_headers` no se usa en el logging de producción | `mcp-adapter/src/asistcv_mcp/server.py:74`; `mcp-adapter/src/asistcv_mcp/http_client.py:15-28,174-182` | P1 |
| A41 | El adapter MCP duplica el prefijo en errores de auth y reenvía al cliente los bodies de error crudos del backend | `mcp-adapter/src/asistcv_mcp/tools.py:46-48`; `mcp-adapter/src/asistcv_mcp/http_client.py:124` | P2 |
| A42 | Para CVs en PDF, la fuente de verdad de `CVAudit` carece de las claves `title` / `company` / `dates` que el schema de salida exige → el path de PDF solo puede "pasar" con metadata vacía | `backend/app/services/pdf_parser.py:260-320`; `backend/app/schemas.py:51-53`; `backend/app/services/adaptation_validator.py:222-231` | P1 |

---

## DevOps / CI

| ID | Descripción | Ubicación | Sev. |
|---|---|---|---|
| A43 | Los tests de frontend nunca se ejecutan en CI (detalle en T1) | `.github/workflows/ci.yml:141-166` | P1 |
| A44 | Ningún workflow declara `permissions:`; todos los jobs heredan el scope por defecto del `GITHUB_TOKEN` | `.github/workflows/*.yml` | P1 |
| A45 | Las third-party actions están clavadas a tags mutables en lugar de SHAs | `.github/workflows/*.yml` | P2 |
| A46 | Dos crons leen la URL del backend de repo vars distintas (`RENDER_BACKEND_URL` vs `BACKEND_URL`) con el mismo fallback hardcodeado a prod Render → un misconfig pega a producción en silencio | workflows de cron | P1 |
| A47 | El docstring del sweeper de adaptaciones contradice su código (describe fail-open cuando es fail-closed) | `backend/app/api/internal/adaptations.py:60-70` | P3 |
| A48 | `adaptation_enabled` (el kill switch) no figura en `.env.example` | `backend/.env.example` | P2 |
| A49 | `get_engine` reescribe / descarta query params de la DB URL salvo allowlist (compat Neon): frágil ante cualquier param nuevo | `backend/app/db/session.py:44-46` | P2 |

---

## Docs / deuda

| ID | Descripción | Ubicación | Sev. |
|---|---|---|---|
| A50 | `README.md`, `STACK.md`, `PROJECT.md` y `ROADMAP.md` describen una herramienta personal pre-auth sobre GCP; el código es un SaaS multi-tenant sobre Render | `README.md`; `STACK.md`; `PROJECT.md`; `ROADMAP.md` | P2 |
| A51 | `README.md` dice "Sprint 0 en curso" mientras `ROADMAP.md` dice Sprint 0 cerrado; el badge dice "Apache 2.0" y el cuerpo "License: TBD" | `README.md`; `ROADMAP.md`; `PROJECT.md:178-182` | P2 |
| A52 | `README.md` anuncia **Outreach** y **Tracking Pipeline**, y ninguno de los dos existe: no hay código, ni migraciones, ni rutas. Solo se implementaron Match + Adaptation | `README.md`; `PROJECT.md:30-36` | P1 |
| A53 | Los targets `setup`, `test`, `lint` y `deploy` del `Makefile` son stubs TODO que salen con 0 sin hacer nada, y el README los documenta como funcionales | `Makefile`; `README.md`; `PROJECT.md:152-176` | P2 |
| A54 | `infra/README.md` describe Cloud Run, Cloud SQL, Artifact Registry y Terraform que no existen | `infra/README.md` | P2 |
| A55 | `.env.example` del backend documenta 12 de 26 variables: faltan `JWT_SECRET`, `AUDIT_CLEANUP_TOKEN`, `ADAPTATION_ENABLED`, `FRONTEND_URL`, 4× `STRIPE_PRICE_*` y 3× de retrieval | `backend/.env.example` | P1 |
| A56 | `infra/.env.example` declara el puerto de DB como 5432 cuando docker-compose usa 5433 | `infra/.env.example`; `infra/docker-compose.yml` | P2 |
| A57 | El `.env.example` del frontend documenta `PUBLIC_BACKEND_API_KEY`, que el build prohíbe usar | `frontend/.env.example` | P2 |
| A58 | ~~El cambio SDD activo `sprint-adapt-cv-outreach` muestra 0 de 37 tasks marcadas, aunque sus 4 PRs están mergeadas, y no tiene verify-report~~ **RESUELTO 2026-10-06**: verificado y archivado. La causa era que se implementó sin fase `apply`. La verificación encontró 3 CRITICAL (#81 `content_version` inexistente, #82 `sanitize_jd` nunca implementado, #83 `jd_text` ≥1 y no ≥50) y 11 WARNING (#84) | `openspec/changes/archive/2026-10-06-sprint-adapt-cv-outreach/` | P2 → cerrado |
| A59 | No hay specs de outreach ni de tracking pipeline: la búsqueda en `openspec/specs/` confirma el gap de feature completo | `openspec/specs/` | P2 |

---

## Código muerto

| ID | Descripción | Ubicación | Sev. |
|---|---|---|---|
| A60 | Tabla `TokenRevocation` definida y nunca consultada | `backend/app/models.py:238-252` | P2 |
| A61 | Tabla `Payment` definida y nunca escrita | `backend/app/models.py` | P2 |
| A62 | Servicio `cv_storage` presente pero solo con referencias comentadas | `backend/app/services/cv_storage.py` | P2 |
| A63 | `init_db` / `close_db` definidos y nunca llamados; el bloque `init/close` del lifespan no ejecuta nada | `backend/app/main.py`; `backend/app/db/session.py` | P2 |
| A64 | Helpers `consume_token`, `get_recruiter_consent` y `create_recruiter_consent` sin uso | `backend/app/services/consent_gate.py`; `backend/app/api/v1/recruiter_consent.py` | P3 |
| A65 | Check `ROLE_IMMUTABLE` inalcanzable: el schema no tiene campo `role` | `backend/app/` (schemas) | P3 |
| A66 | `stripe_client.create_customer` definido y nunca invocado | `backend/app/services/stripe_client.py` | P3 |
| A67 | `Embedding.provider` con default sin uso | `backend/app/models.py` | P3 |
| A68 | `pdf_parser.CHUNK_SIZE` y `validate_file_size` sin uso | `backend/app/services/pdf_parser.py` | P3 |
| A69 | `_debug_safe_headers` definido y nunca invocado en el adapter MCP | `mcp-adapter/src/asistcv_mcp/http_client.py` | P3 |
| A70 | Página de detalle `frontend/src/routes/history/[id]/+page.svelte` inalcanzable en la práctica (ver A38) | `frontend/src/routes/history/[id]/+page.svelte` | P3 |
