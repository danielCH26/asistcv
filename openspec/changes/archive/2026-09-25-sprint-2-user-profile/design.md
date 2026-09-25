# Design: Sprint 2 — Cuentas de usuario, CV y Billing (Slice 2)

## Resumen del enfoque técnico

Sprint 1 dejó en producción el flujo match con persistencia transaccional, auth por API key, retrieval por umbral y frontend estático en SvelteKit (`adapter-static` + `svelte-i18n` ES/EN), más MCP adapter operativo contra Render. Este sprint cierra el delta hacia producto multi-usuario: introduce cuentas con roles (`job_seeker` / `recruiter`), JWT coexistiendo con la API key del MCP (precedencia JWT primero), gestión de CV (PDF ≤10MB con `pypdf` y fallback `pdfminer.six`), auditoría anónima gratuita como funnel, roster de candidatos externos para reclutadores con ToS, y billing Stripe (tarjeta + PSE CO) con webhooks firmados e idempotentes.

Decisiones cerradas que el diseño incorpora como hechos (no se re-debaten):

| # | Decisión cerrada |
|---|---|
| 1 | Auth dual: `BACKEND_API_KEY` permanece como credencial de servicio/MCP; JWT (HS256, 15 min access + 30 d refresh opaco) se suma para usuarios. Precedencia: JWT primero, API key como fallback. |
| 2 | Aislamiento: PostgreSQL RLS sobre tablas user-owned (`users_cvs`, `recruiter_candidates`, `subscriptions`, `analyses`). El servicio aplica además checks defensivos — defense in depth. |
| 3 | Parser PDF streaming (pypdf chunk 64KB) con fallback pdfminer.six ante `MemoryError`. Hard cap 10MB en el endpoint antes de tocar `pypdf`. |
| 4 | Stripe Checkout (card + PSE vía Local Payment Methods) + webhook con firma + dedupe por `event.id` + idempotencia de checkout por `Idempotency-Key`. |
| 5 | Free audit rate-limit 3/IP/día; retención 30 d con limpieza vía GitHub Actions schedule (Render free tier no soporta cron nativo). |

Mapa de archivos objetivo:

| Archivo | Acción | PR |
|---|---|---|
| `backend/alembic/versions/003_users_and_refresh_tokens.py` | Create | PR1 |
| `backend/alembic/versions/004_users_cvs.py` | Create | PR2 |
| `backend/alembic/versions/005_recruiter_candidates.py` | Create | PR4 |
| `backend/alembic/versions/006_audit_uploads_and_funnel.py` | Create | PR3 |
| `backend/alembic/versions/007_subscriptions_payments.py` | Create | PR5 |
| `backend/alembic/versions/008_rls_policies.py` | Create | PR6 (último) |
| `backend/app/db/models.py` | Modify — 5 modelos nuevos | varios |
| `backend/app/api/deps.py` | Modify — `get_current_user` JWT-first, `require_role` | PR1 |
| `backend/app/core/config.py` | Modify — `JWT_SECRET`, `JWT_ALGORITHM`, `STRIPE_*` | PR1, PR5 |
| `backend/app/api/v1/auth.py` | Create — register, login, refresh, logout, verify-email | PR1 |
| `backend/app/api/v1/users.py` | Create — `/users/me`, password change | PR1 |
| `backend/app/api/v1/cvs.py` | Create — POST/GET/PATCH/DELETE `/v1/cvs` | PR2 |
| `backend/app/api/v1/audit.py` | Create — POST `/v1/audit`, capture-email | PR3 |
| `backend/app/api/v1/recruiter.py` | Create — candidates CRUD + match + ranked | PR4 |
| `backend/app/api/v1/billing.py` | Create — plans, checkout, portal, subscription | PR5 |
| `backend/app/api/v1/webhooks/stripe.py` | Create — webhook firmado con raw body | PR5 |
| `backend/app/services/pdf_parser.py` | Create — streaming pypdf + pdfminer fallback | PR2, PR3 |
| `backend/app/services/billing.py` | Create — Stripe SDK wrapper, idempotencia | PR5 |
| `backend/app/services/audit_retention.py` | Create — endpoint interno para cron externo | PR3 |
| `backend/app/services/rls_context.py` | Create — `SET LOCAL app.current_user` | PR1, PR6 |
| `frontend/src/routes/login/`, `register/`, `verify-email/` | Create | PR7 |
| `frontend/src/routes/cvs/`, `cvs/[id]/` | Create | PR7 |
| `frontend/src/routes/audit/` | Create | PR7 |
| `frontend/src/routes/recruiter/` | Create | PR7 |
| `frontend/src/routes/billing/` | Create | PR7 |
| `frontend/src/lib/stores/session.ts` | Create — JWT + refresh + auto-renew | PR7 |
| `frontend/src/lib/api/client.ts` | Modify — Bearer JWT, no más API key build-time | PR7 |
| `.github/workflows/audit-retention.yml` | Create — schedule diario | PR3 |

---

## 1. Arquitectura general

### 1.1 Capas y módulos backend

```
backend/app/
├── api/v1/
│   ├── auth.py             ← register / login / refresh / logout / verify-email
│   ├── users.py            ← /users/me, password change
│   ├── cvs.py              ← /cvs (user-bound, RLS)
│   ├── audit.py            ← /audit (anónimo, rate-limited)
│   ├── recruiter.py        ← /recruiter/candidates/*
│   ├── billing.py          ← /billing/plans, checkout, portal, subscription
│   └── webhooks/
│       └── stripe.py       ← /webhooks/stripe (raw body, sin auth)
├── services/
│   ├── pdf_parser.py       ← streaming pypdf + pdfminer fallback
│   ├── billing.py          ← Stripe wrapper (idempotency, checkout, portal)
│   ├── audit_retention.py  ← deleteExpired() + telemetría funnel
│   ├── audit_funnel.py     ← emit events a audit_funnel_events
│   └── rls_context.py      ← context manager Postgres GUC SET LOCAL
├── db/
│   └── models.py           ← + User, RefreshToken, UserCV, RecruiterCandidate,
│                              AuditUpload, Subscription, RecruiterConsent,
│                              RecruiterAuditLog, StripeWebhookEvent
└── core/
    └── config.py           ← JWT_*, STRIPE_*, AUDIT_*, RATE_LIMIT_*
```

### 1.2 Frontend (SvelteKit estático)

```
frontend/src/routes/
├── +layout.svelte          ← nav con sesión, LanguageToggle, banner global
├── +page.svelte            ← / (JdForm → resultado; requiere JWT)
├── login/+page.svelte
├── register/+page.svelte   ← wizard registro por rol (incluye ToS recruiter)
├── verify-email/+page.svelte
├── cvs/
│   ├── +page.svelte        ← listado
│   ├── upload/+page.svelte
│   └── [id]/+page.svelte   ← editor estructurado
├── audit/+page.svelte      ← funnel anónimo
├── recruiter/
│   ├── candidates/+page.svelte
│   └── candidates/[id]/+page.svelte
├── billing/
│   ├── plans/+page.svelte
│   └── subscription/+page.svelte
├── history/                ← existente (modificado: JWT + filtro user-bound)
└── analyses/[id]/+page.svelte  ← existente (modificado)
```

### 1.3 Principios arquitectónicos

- **Hexagonal / Clean**: `services/` no depende de FastAPI; `api/` traduce HTTP ↔ servicios. Esto facilita test unit sin cliente HTTP.
- **Defense in depth**: RLS en BD (primera línea) + checks de servicio (segunda). Si una policy RLS se rompe por error de migración, los `WHERE owner_user_id = current_user.id()` en queries siguen protegiendo.
- **Idempotencia por diseño**: webhooks Stripe (event.id dedupe), checkout (Idempotency-Key header), refresh tokens (rotación con consumed_at).
- **Fail-open selectivo**: free-audit funciona con `BACKEND_API_KEY` no definida; endpoints autenticados nunca.
- **Streaming defensivo**: PDFs se procesan en chunks 64KB para evitar OOM en Render 512MB.

---

## 2. Modelo de datos (5 tablas nuevas + RLS)

### 2.1 Tablas y columnas clave

```sql
-- users
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  email CITEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,                    -- bcrypt cost 12
  role TEXT NOT NULL CHECK (role IN ('job_seeker','recruiter')),
  full_name TEXT NOT NULL,
  locale TEXT NOT NULL DEFAULT 'es',
  avatar_url TEXT,
  email_verified_at TIMESTAMPTZ,
  email_verification_token_hash TEXT,
  email_verification_expires_at TIMESTAMPTZ,
  last_login_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_users_role ON users(role);

-- users_refresh_tokens
CREATE TABLE users_refresh_tokens (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,                -- sha256(token)
  consumed_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  user_agent TEXT,
  ip INET
);
CREATE INDEX idx_refresh_user_active
  ON users_refresh_tokens(user_id) WHERE consumed_at IS NULL AND revoked_at IS NULL;

-- users_cvs (RLS-protected)
CREATE TABLE users_cvs (
  id BIGSERIAL PRIMARY KEY,
  owner_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  original_filename TEXT NOT NULL,
  detected_locale TEXT,
  raw_blob BYTEA,                                 -- PDF binario
  raw_text TEXT,                                  -- extraído por pypdf
  structured JSONB NOT NULL,                      -- schema: full_name, email, experience[], ...
  embedding vector(1024),
  embedding_model TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_edited_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_cvs_owner ON users_cvs(owner_user_id);
CREATE INDEX idx_cvs_embedding_hnsw ON users_cvs USING hnsw (embedding vector_cosine_ops);

-- recruiter_candidates (RLS-protected)
CREATE TABLE recruiter_candidates (
  id BIGSERIAL PRIMARY KEY,
  recruiter_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  email CITEXT,
  phone TEXT,
  notes TEXT,
  cv_id BIGINT REFERENCES recruiter_candidates_cvs(id) ON DELETE SET NULL,
  last_analysed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_candidate_unique_per_recruiter
  ON recruiter_candidates(recruiter_id, COALESCE(email, ''));
CREATE INDEX idx_candidate_recruiter ON recruiter_candidates(recruiter_id);

-- audit_uploads (sin RLS — datos anónimos; limpieza por job)
CREATE TABLE audit_uploads (
  id BIGSERIAL PRIMARY KEY,
  audit_funnel_id UUID NOT NULL UNIQUE,
  ip_hash TEXT NOT NULL,                          -- sha256(ip + salt), truncado
  jd_text TEXT NOT NULL,
  pdf_blob BYTEA,
  pdf_text TEXT,
  result JSONB,                                   -- MatchAnalysis
  email_captured TEXT,
  linked_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_expires ON audit_uploads(expires_at) WHERE linked_user_id IS NULL;
CREATE INDEX idx_audit_linked ON audit_uploads(linked_user_id) WHERE linked_user_id IS NOT NULL;

-- subscriptions (RLS-protected)
CREATE TABLE subscriptions (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan_id TEXT NOT NULL,                          -- 'free' | 'job_seeker_monthly' | 'recruiter_starter' | ...
  status TEXT NOT NULL CHECK (status IN ('active','past_due','canceled','incomplete')),
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT UNIQUE,
  current_period_start TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  usage_matches_this_month INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_sub_user_active ON subscriptions(user_id) WHERE status = 'active';

-- Tablas adicionales de soporte (no son las 5 principales pero necesarias):
-- recruiter_candidates_cvs (binarios + texto, FK desde recruiter_candidates)
-- recruiter_consent (FK a users, accepted_at, tos_version, ip, user_agent)
-- recruiter_analyses (FK a recruiter_candidates, persistencia de matches)
-- recruiter_audit_log (append-only, trigger BEFORE UPDATE/DELETE que rechaza)
-- stripe_webhook_events (event_id PK, type, payload, processed_at)
-- audit_funnel_events (telemetría: step, ip_hash, audit_id, user_id opcional)
-- token_revocation (jti del access_token revocado, TTL = exp)
-- auth_login_attempts (rate-limit fuerza bruta: email, ip, success, attempted_at)
-- auth_security_events (cross-user attempts, token reuse, etc.)
```

### 2.2 RLS policies (aplicadas en migración 008, después de todas las tablas)

Patrón uniforme (defense in depth):

```sql
-- Habilitar RLS
ALTER TABLE users_cvs ENABLE ROW LEVEL SECURITY;
ALTER TABLE users_cvs FORCE ROW LEVEL SECURITY;   -- incluso owners respetan policy

-- Política lectura
CREATE POLICY users_cvs_select ON users_cvs
  FOR SELECT
  USING (
    owner_user_id = current_setting('app.current_user_id', true)::BIGINT
    AND current_setting('app.current_role', true) = 'job_seeker'
  );

-- Política inserción (sólo con su propio owner_user_id)
CREATE POLICY users_cvs_insert ON users_cvs
  FOR INSERT
  WITH CHECK (owner_user_id = current_setting('app.current_user_id', true)::BIGINT);

-- Política update / delete (mismo filtro)
CREATE POLICY users_cvs_modify ON users_cvs
  FOR UPDATE USING (owner_user_id = current_setting('app.current_user_id', true)::BIGINT)
  WITH CHECK (owner_user_id = current_setting('app.current_user_id', true)::BIGINT);

CREATE POLICY users_cvs_delete ON users_cvs
  FOR DELETE USING (owner_user_id = current_setting('app.current_user_id', true)::BIGINT);
```

`recruiter_candidates` aplica la misma forma con `recruiter_id` y `role = 'recruiter'`. `subscriptions` aplica con `user_id`. Las tablas sin owner (`audit_uploads`, `audit_funnel_events`, `stripe_webhook_events`, `recruiter_audit_log`) **no** tienen RLS — la primera porque es anónima, las demás porque son append-only o internas.

`recruiter_audit_log` se protege con trigger:

```sql
CREATE OR REPLACE FUNCTION reject_modification() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit log is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_audit_log_immutable
  BEFORE UPDATE OR DELETE ON recruiter_audit_log
  FOR EACH ROW EXECUTE FUNCTION reject_modification();
```

### 2.3 SET LOCAL desde el servicio

```python
# app/services/rls_context.py
from contextlib import contextmanager
from sqlalchemy import text

@contextmanager
def rls_context(session, user_id: int | None, role: str | None):
    """Establece el contexto RLS en la sesión actual (Postgres GUC)."""
    if user_id is None:
        # Modo servicio / API key / free-audit
        session.execute(text("SET LOCAL app.current_user_id = '0'"))
        session.execute(text("SET LOCAL app.current_role = 'service'"))
    else:
        session.execute(text("SET LOCAL app.current_user_id = :uid"), {"uid": user_id})
        session.execute(text("SET LOCAL app.current_role = :role"), {"role": role})
    yield session
```

`SET LOCAL` vive lo que dura la transacción; el servicio garantiza que toda query que toca tablas con RLS esté envuelta en transacción explícita. Conexión sin contexto → query falla con `AUTH_CONTEXT_MISSING` (500), que el servicio traduce antes de propagar (ver scenario del spec `cv-management`).

---

## 3. API surface (new + modified)

### 3.1 Endpoints nuevos

| Método | Ruta | Auth | Capability |
|---|---|---|---|
| POST | `/v1/auth/register` | público | user-accounts |
| POST | `/v1/auth/login` | público | user-accounts |
| POST | `/v1/auth/refresh` | refresh token | authentication |
| POST | `/v1/auth/logout` | JWT | user-accounts |
| POST | `/v1/auth/verify-email/request` | JWT | user-accounts |
| POST | `/v1/auth/verify-email/confirm` | token en body | user-accounts |
| GET | `/v1/users/me` | JWT | user-accounts |
| PATCH | `/v1/users/me` | JWT | user-accounts |
| POST | `/v1/users/me/password` | JWT | user-accounts |
| POST | `/v1/cvs` | JWT | cv-management |
| GET | `/v1/cvs` | JWT | cv-management |
| GET | `/v1/cvs/{id}` | JWT | cv-management |
| PATCH | `/v1/cvs/{id}` | JWT | cv-management |
| DELETE | `/v1/cvs/{id}` | JWT | cv-management |
| POST | `/v1/audit` | público (rate-limited) | free-audit |
| POST | `/v1/audit/{audit_id}/capture-email` | público | free-audit |
| POST | `/v1/recruiter/candidates` | JWT recruiter + consent | recruiter-roster |
| GET | `/v1/recruiter/candidates` | JWT recruiter + consent | recruiter-roster |
| POST | `/v1/recruiter/candidates/{id}/match` | JWT recruiter + consent | recruiter-roster |
| GET | `/v1/recruiter/candidates/ranked` | JWT recruiter + consent | recruiter-roster |
| DELETE | `/v1/recruiter/candidates/{id}` | JWT recruiter + consent | recruiter-roster |
| GET | `/v1/billing/plans` | público | billing |
| POST | `/v1/billing/checkout` | JWT | billing |
| POST | `/v1/billing/portal` | JWT | billing |
| GET | `/v1/billing/subscription` | JWT | billing |
| POST | `/v1/webhooks/stripe` | firma Stripe (sin JWT ni API key) | billing |

### 3.2 Endpoints modificados

| Método | Ruta | Cambio |
|---|---|---|
| `POST /v1/match` | Auth dual (JWT o API key); persiste `user_id` del JWT | match-analysis |
| `GET /v1/analyses` | Filtro automático por `user_id` del JWT (RLS) | match-analysis |
| `GET /v1/analyses/{id}` | 404 si pertenece a otro user | match-analysis |
| `GET /health` | Sigue público (sin cambios) | universal |
| `GET /ping` | Sigue protegido por API key (modo actual preservado) | authentication |

### 3.3 Códigos de error estandarizados

| Código | HTTP | Uso |
|---|---|---|
| `TOKEN_INVALID` | 401 | refresh revocado/expirado |
| `TOKEN_REUSED` | 401 | reuso de refresh → cadena revocada |
| `ROLE_FORBIDDEN` | 403 | rol del JWT no califica |
| `CONSENT_REQUIRED` | 403 | reclutador sin ToS |
| `ROLE_IMMUTABLE` | 422 | intento de cambiar role vía PATCH |
| `EMAIL_TAKEN` | 409 | registro duplicado |
| `INVALID_CREDENTIALS` | 401 | login fallido (genérico) |
| `PLAN_LIMIT_REACHED` | 402 | tope mensual excedido |
| `RATE_LIMITED` | 429 | audit por IP o login fuerza bruta |
| `JD_TOO_SHORT` | 422 | jd_text < 50 chars |
| `PDF_NO_TEXT` | 422 | PDF sin texto extraíble |
| `PDF_INVALID` | 422 | free-audit con PDF inválido |
| `PDF_PARSE_FAILED` | 503 | pypdf + pdfminer ambos fallan |
| `FILE_TOO_LARGE` | 413 | PDF > 10MB |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Content-Type ≠ application/pdf |
| `CANDIDATE_DUPLICATED` | 409 | email duplicado en roster |
| `AUDIT_EXPIRED` | 410 | capture-email > 1h |
| `AUTH_CONTEXT_MISSING` | 500 | sin GUC app.current_user_id |
| `EMAIL_INVALID` | 422 | email malformado |
| `NO_CUSTOMER` | 400 | billing portal sin stripe_customer_id |

---

## 4. Flujo de auth (dual JWT + API key, lifecycle de tokens)

### 4.1 Precedencia y unified dependency

```
HTTP request
    │
    ▼
Authorization: Bearer <credential>
    │
    ├─ JWT válido (firma HS256, no expirado, jti no revocado)
    │     → current_user = User(id=sub, role=role), auth_method="jwt"
    │
    ├─ Match con BACKEND_API_KEY (secrets.compare_digest)
    │     → current_user = SyntheticUser(name="system", role="service"), auth_method="api_key"
    │
    └─ Ninguno
          → 401 sin invocar handlers
```

`get_current_user` en `app/api/deps.py` se reescribe como una sola dependencia:

```python
async def get_current_user(
    request: Request,
    api_key_header: str | None = Depends(_security),
) -> CurrentUser:
    """Intenta JWT primero; si falla, intenta API key; si ninguna, 401."""
    token = _extract_bearer(api_key_header)
    if token and token.startswith("ey"):                   # heurística JWT (3 segmentos base64)
        user = await _try_jwt(token)
        if user: return user
    settings = get_settings()
    if settings.backend_api_key and token and secrets.compare_digest(token, settings.backend_api_key):
        return CurrentUser(id=0, name="system", role="service", auth_method="api_key")
    raise HTTPException(401, "Invalid credentials")
```

Nota: la heurística `token.startswith("ey")` evita el costo de verificar firma cuando claramente no es JWT. Verificación completa con `jwt.decode(..., algorithms=["HS256"], options={"require": ["exp","sub"]})` y check de `jti` contra `token_revocation`.

`require_role("recruiter")` es una dependencia que envuelve `get_current_user` y compara `role`:

```python
def require_role(*allowed: str):
    def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(403, "ROLE_FORBIDDEN")
        return user
    return _dep
```

### 4.2 Lifecycle del refresh token (rotación)

```
POST /v1/auth/login
  └─► bcrypt.verify(password) → genera access_token (jti, 15 min) + refresh_token (opaco 32 bytes)
      └─► guarda sha256(token), expires_at=now+30d, user_agent, ip

POST /v1/auth/refresh
  ├─► sha256(refresh_token) → lookup users_refresh_tokens
  ├─► si expires_at < now o revoked_at != NULL → 401 TOKEN_INVALID
  ├─► si consumed_at != NULL → 401 TOKEN_REUSED + revoca TODOS los tokens del user
  ├─► si vigente:
  │     UPDATE users_refresh_tokens SET consumed_at = NOW() WHERE id=...
  │     genera nuevo access + nuevo refresh (mismo user)
  │     INSERT nuevo users_refresh_tokens
  │     retorna 200 { access_token, refresh_token }
  └─► en error: registra en auth_security_events

POST /v1/auth/logout
  ├─► UPDATE users_refresh_tokens SET revoked_at = NOW() WHERE token_hash = sha256(refresh_token)
  └─► INSERT token_revocation (jti, ttl = exp del access_token)

POST /v1/users/me/password
  └─► UPDATE users_refresh_tokens SET revoked_at = NOW() WHERE user_id = X AND revoked_at IS NULL
      (cambio de password invalida cadena; nueva cadena tras re-login)
```

### 4.3 Escenario de reuso (token theft)

El scenario "Reuso de refresh token" del spec exige respuesta firme:

```
POST /v1/auth/refresh  (con token consumido_at != NULL)
  ├─► 401 TOKEN_REUSED
  ├─► UPDATE users_refresh_tokens SET revoked_at = NOW()
  │   WHERE user_id = X AND revoked_at IS NULL AND consumed_at IS NULL
  └─► INSERT auth_security_events (event='token_reuse', user_id, ip, user_agent)
```

UI: al recibir 401 con código `TOKEN_REUSED`, limpia tokens y muestra "Tu sesión fue invalidada por seguridad. Por favor inicia sesión de nuevo."

---

## 5. Free audit funnel (anónimo → email opcional → signup linking)

### 5.1 Pipeline del endpoint `/v1/audit`

```
POST /v1/audit (multipart: file + jd_text)
  │
  ├─1─ validar jd_text ≥ 50 chars → 422 JD_TOO_SHORT
  ├─2─ validar Content-Type=application/pdf → 415
  ├─3─ validar Content-Length ≤ 10MB → 413 FILE_TOO_LARGE
  ├─4─ rate limit: 3/IP/día (counter en audit_uploads exitosos)
  │      └─► si excedido: 429 con Retry-After
  ├─5─ abrir transacción:
  │      INSERT audit_uploads (audit_funnel_id=uuid, ip_hash, jd_text,
  │                             pdf_blob, expires_at = now + 30d)
  │      SET LOCAL app.current_user_id = '0'   -- modo servicio
  ├─6─ streaming PDF: pdf_parser.parse(pdf_blob)
  │      ├─► pypdf chunk 64KB → texto
  │      ├─► si MemoryError: pdfminer.six fallback
  │      └─► si ambos fallan: 503 PDF_PARSE_FAILED, ROLLBACK (sin audit_upload)
  ├─7─ pipeline match: embedding(BGE-M3) → LLM Groq → MatchAnalysis
  ├─8─ UPDATE audit_uploads SET result = jsonb, raw_text = ...
  ├─9─ emit audit_funnel_events (step='audit_success', audit_id, ip_hash)
  └─10─ responde 200 con Cache-Control: no-store, X-Robots-Tag: noindex
```

### 5.2 Captura de email

```
POST /v1/audit/{audit_id}/capture-email  { "email": "..." }
  ├─► valida RFC 5322 → 422 EMAIL_INVALID
  ├─► lookup audit_uploads WHERE id = X AND created_at > now - 1h
  │   └─► si no: 410 AUDIT_EXPIRED
  ├─► UPDATE audit_uploads SET email_captured = X
  ├─► email con HTML del MatchAnalysis + CTA /register?ref=audit_<id>
  └─► responde 202
```

### 5.3 Linking audit → signup (hash cookie)

Cuando se captura email, el backend setea cookie httpOnly:

```
Set-Cookie: audit_link=<base64(sha256(audit_id + SECRET_SALT))>;
            Max-Age=2592000; HttpOnly; SameSite=Lax; Secure
```

En el registro, la UI envía `audit_link` en el body. El backend:

1. Si la cookie existe al momento del login/registro, matchea contra `audit_uploads.email_captured`.
2. Si coincide: `UPDATE audit_uploads SET linked_user_id = X WHERE email_captured = ?`.
3. Registra `audit_funnel_events` con `step='audit_to_signup'`.

Si el usuario NO se registra, el CV anónimo permanece en `audit_uploads` hasta la limpieza de 30 d (CRON externo).

### 5.4 Limpieza 30 d vía GitHub Actions

`.github/workflows/audit-retention.yml`:

```yaml
name: audit-retention
on:
  schedule:
    - cron: '17 3 * * *'    # 03:17 UTC diario
  workflow_dispatch:
jobs:
  cleanup:
    runs-on: ubuntu-latest
    steps:
      - name: DELETE expired audit_uploads
        run: |
          curl -fsS -X POST \
            -H "Authorization: Bearer ${{ secrets.AUDIT_CLEANUP_TOKEN }}" \
            https://asistcv-api.onrender.com/internal/audit/cleanup
```

Endpoint interno protegido por `AUDIT_CLEANUP_TOKEN` (no JWT, no API key pública):

```python
@router.post("/internal/audit/cleanup")
async def cleanup(authorization: str = Header(...)):
    if not secrets.compare_digest(authorization.removeprefix("Bearer "), settings.audit_cleanup_token):
        raise HTTPException(401)
    deleted = await audit_retention.delete_expired()
    return {"deleted": deleted}
```

El job ejecuta:
```sql
DELETE FROM audit_uploads
WHERE linked_user_id IS NULL
  AND expires_at < NOW()
RETURNING id;
```

Cada delete emite `audit_funnel_events` con `step='audit_purged'` para observabilidad.

---

## 6. Recruiter roster (CRUD, CVs externos, ToS gate)

### 6.1 ToS gate en flujo de registro

```
POST /v1/auth/register { role: "recruiter", accept_tos: false, ... }
  └─► 422 CONSENT_REQUIRED, NO crea cuenta
POST /v1/auth/register { role: "recruiter", accept_tos: true, good_faith_declaration: true, tos_version: "v1.2" }
  └─► INSERT users (role='recruiter')
      INSERT recruiter_consent (user_id, accepted_at, tos_version, ip, user_agent)
      retorna 201 + tokens
```

Migración de cuentas previas: cualquier recruiter creado antes del sprint que intente un endpoint de roster recibe 403 `CONSENT_REQUIRED` y la UI fuerza la pantalla de consentimiento (route guard en `frontend/src/routes/recruiter/+layout.svelte`).

### 6.2 CRUD de candidatos

```
POST /v1/recruiter/candidates (multipart)
  ├─► require_role("recruiter") + recruiter_consent.accepted_at IS NOT NULL
  ├─► valida PDF (≤10MB, application/pdf)
  ├─► parse + estructura (mismo pdf_parser)
  ├─► INSERT recruiter_candidates_cvs (blob, texto, structured)
  ├─► INSERT recruiter_candidates (recruiter_id, ..., cv_id)
  ├─► INSERT recruiter_audit_log (action='candidate_added', sha256(pdf_bytes))
  └─► 201 { candidate_id, cv_id, full_name, added_at }
```

`GET /v1/recruiter/candidates?page=1&page_size=10` paginado; `recruiter_analyses` y `recruiter_candidates` se unen para devolver `last_analysed_at`.

`DELETE /v1/recruiter/candidates/{id}` → CASCADE borra `recruiter_analyses`, `recruiter_candidates_cvs`.

### 6.3 Match y ranking híbrido

`POST /v1/recruiter/candidates/{id}/match { jd_text }`:

- Reusa el pipeline match (`POST /v1/match`) pero con `cv_id = recruiter_candidates_cvs.id` y persistiendo en `recruiter_analyses` (no en `analyses` global).
- Incrementa `usage.matches_this_month` en `subscriptions` del recruiter.
- Si `usage >= limits.matches_per_month` (50 Starter, 200 Business, ∞ Agency): 402 `PLAN_LIMIT_REACHED`.

`GET /v1/recruiter/candidates/ranked?jd_text=...`:

1. Pre-filtrar top-K=10 por similitud embedding del CV contra el JD (operación barata, pgvector HNSW).
2. Para cada uno de los K candidatos, calcular `match_score = LLM(jd, cv)` (N=10 ejecuciones paralelas con semáforo asyncio).
3. Si ya existen análisis previos del JD contra estos candidatos (`recruiter_analyses` cacheable por hash del JD), reusar el score cacheado.
4. Aplicar `effective_score = match_score * exp(-dias_desde_ultimo_analisis / 30)`.
5. Floor: si `effective_score < 0.5 * match_score` y `match_score >= 0.7`, fijar `effective_score = 0.5 * match_score` (evita hundir candidatos válidos por recencia baja).
6. Ordenar descendente, devolver top 10.

Si el roster tiene > 10 candidatos, los restantes quedan fuera del ranking. La UI debe mostrar el mensaje "Mostrando top 10 de N candidatos; refina el JD para mejorar la cobertura".

---

## 7. Billing (Stripe products/prices, webhook, tier enforcement, PSE CO)

### 7.1 Productos y precios (USD/mes)

| Plan | Tier | Price USD | matches/mes | Stripe Product ID |
|---|---|---|---|---|
| Free job_seeker | `free` | $0 | 3 | n/a |
| Job Seeker Monthly | `job_seeker_monthly` | $9 | 50 | prod_job_monthly |
| Recruiter Starter | `recruiter_starter` | $29 | 50 | prod_rec_starter |
| Recruiter Business | `recruiter_business` | $99 | 200 | prod_rec_business |
| Recruiter Agency | `recruiter_agency` | $299 | ∞ | prod_rec_agency |

El catálogo se sincroniza desde Stripe con `stripe.Price.list(active=True)` en cada `GET /v1/billing/plans` (caché 5 min en memoria por proceso, invalidable por webhook `price.updated`).

### 7.2 Checkout

```python
# app/services/billing.py
async def create_checkout(user_id, plan_id, payment_method, idempotency_key):
    settings = get_settings()
    price_id = PLAN_TO_PRICE_ID[plan_id]

    if payment_method == "pse":
        session = stripe.checkout.Session.create(
            payment_method_types=["pse"],
            payment_method_options={"pse": {"country": "CO"}},
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            customer_email=user.email,
            metadata={"user_id": str(user_id), "plan_id": plan_id},
            idempotency_key=idempotency_key,
            success_url=f"{settings.frontend_url}/billing/subscription?status=success",
            cancel_url=f"{settings.frontend_url}/billing/plans",
        )
    else:  # card
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            customer_email=user.email,
            metadata={"user_id": str(user_id), "plan_id": plan_id},
            idempotency_key=idempotency_key,
            success_url=f"{settings.frontend_url}/billing/subscription?status=success",
            cancel_url=f"{settings.frontend_url}/billing/plans",
        )
    return session.url
```

### 7.3 Webhook firmado e idempotente

```
POST /v1/webhooks/stripe   (sin auth, sin API key; firma en Stripe-Signature)
  │
  ├─► validar firma con STRIPE_WEBHOOK_SECRET → 400 si falla
  ├─► INSERT stripe_webhook_events (event_id, type, payload) ON CONFLICT DO NOTHING
  │      └─► si ya existe: 200 webhook_dedup, retorna sin procesar
  ├─► procesar evento:
  │      ├─ checkout.session.completed → upsert subscriptions (status=active)
  │      ├─ customer.subscription.deleted → subscriptions.status='canceled'
  │      ├─ invoice.payment_failed → subscriptions.status='past_due'
  │      └─ customer.subscription.updated → actualizar current_period_*
  └─► UPDATE stripe_webhook_events SET processed_at = NOW()
```

**Critical**: el router del webhook debe leer el **raw body** antes de que FastAPI lo parsee. Se monta con `include_router(webhooks.router, prefix="/api/v1")` y dentro del handler:

```python
@router.post("/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")
    ...
```

`include_router` con `include_in_schema=False` para no exponerlo en OpenAPI.

### 7.4 Enforcement de tier en match

Antes de `POST /v1/match` (job_seeker) o `POST /v1/recruiter/candidates/{id}/match` (recruiter):

```python
async def enforce_plan_limit(user_id: int, role: str):
    sub = await subscriptions.get_active(user_id)
    if sub is None:
        # free defaults
        if role == "job_seeker":
            return PlanLimit(matches_per_month=3, used=await usage.get_count(user_id))
        return PlanLimit(matches_per_month=0, used=0)  # recruiter sin plan = 0 matches
    return PlanLimit(
        matches_per_month=sub.limits.matches_per_month,
        used=sub.usage_matches_this_month,
    )

async def check_can_match(limit: PlanLimit) -> None:
    if limit.matches_per_month is not None and limit.used >= limit.matches_per_month:
        raise HTTPException(402, "PLAN_LIMIT_REACHED")
```

El contador se incrementa **dentro de la transacción** del match (mismo path que persistencia), antes del COMMIT.

---

## 8. Frontend (rutas nuevas, stores, guards)

### 8.1 Stores

`src/lib/stores/session.ts`:

```typescript
interface Session {
  accessToken: string;
  refreshToken: string;
  user: { id: number; email: string; role: 'job_seeker' | 'recruiter'; full_name: string; locale: string };
  expiresAt: number;            // ms epoch del access
}

export const session = writable<Session | null>(null);
export const isAuthenticated = derived(session, ($s) => $s !== null);
export const isRecruiter = derived(session, ($s) => $s?.user.role === 'recruiter');

// Auto-refresh: si expiresAt - Date.now() < 60_000, llamar /auth/refresh
export function startSessionRefresh() { ... }
```

Persistencia: `localStorage` con clave `asistcv.session` (single-device Svelte estático). El spec menciona "cookie httpOnly si BFF" pero Sprint 2 mantiene estático, así que `localStorage` con SameSite=Lax está bien para el MVP. El refresh proactivo evita que tokens expiren mid-session.

### 8.2 Cliente API

`src/lib/api/client.ts` se rehace: recibe un getter `() => session` para tomar el access token vigente, maneja refresh automático, expone `fetch`:

```typescript
async function api(path: string, init?: RequestInit) {
  const s = get(session);
  let headers = { ...init?.headers };
  if (s) headers.Authorization = `Bearer ${s.accessToken}`;
  let r = await fetch(`${PUBLIC_BACKEND_URL}${path}`, { ...init, headers });
  if (r.status === 401 && s) {
    // intentar refresh silencioso
    const refreshed = await tryRefresh(s.refreshToken);
    if (refreshed) {
      session.set(refreshed);
      headers.Authorization = `Bearer ${refreshed.accessToken}`;
      r = await fetch(`${PUBLIC_BACKEND_URL}${path}`, { ...init, headers });
    }
  }
  if (r.status === 401) {
    session.set(null);
    goto('/login?reason=expired');
  }
  return r;
}
```

### 8.3 Guards de ruta

`+layout.svelte` revisa `isAuthenticated` y `isRecruiter` antes de renderizar children:

```
/cvs/*                  → require isAuthenticated
/recruiter/*            → require isRecruiter && hasAcceptedConsent
/billing/*              → require isAuthenticated
/audit                  → público
/login, /register       → require !isAuthenticated (redirect /cvs si ya autenticado)
```

`hasAcceptedConsent` se hidrata de `GET /v1/users/me` (campo `recruiter_consent.accepted_at` si role=recruiter).

### 8.4 Onboarding wizard

Tres pasos con persistencia del paso actual en `localStorage` (`asistcv.onboarding_step`):

1. `/onboarding/role` — confirma rol + edita `full_name` y `locale`.
2. `/onboarding/cv` — upload PDF o editor estructurado.
3. `/onboarding/match` — ejecuta primer match contra un JD de muestra.

Al completar paso 3: `localStorage.removeItem('asistcv.onboarding_step')` y redirect `/cvs`.

---

## 9. Plan de migración (orden aditivo, rollback strategy)

### 9.1 Orden de las migraciones Alembic

```
003_users_and_refresh_tokens.py        PR1 — auth foundation
004_users_cvs.py                       PR2 — CV management
005_recruiter_candidates.py            PR4 — recruiter roster
006_audit_uploads_and_funnel.py        PR3 — free audit
007_subscriptions_payments.py          PR5 — billing
008_rls_policies.py                    PR6 — RLS (ÚLTIMO)
```

**Por qué RLS al final**: las policies RLS asumen que las tablas existen y tienen las columnas que referencian (`owner_user_id`, `recruiter_id`, `user_id`). Si una migración posterior agrega una columna nueva, hay que actualizar la policy. Aplicar RLS en la última migración del sprint reduce este riesgo.

### 9.2 Aditividad

Todas las migraciones son 100% aditivas en producción:

- Nuevas tablas, nuevas columnas (todas NULLable por default).
- Nuevos índices HNSW (CREATE INDEX CONCURRENTLY cuando sea posible).
- Sin `ALTER TABLE ... DROP COLUMN` ni `DROP TABLE` durante el sprint.
- RLS se habilita con `FORCE ROW LEVEL SECURITY` (incluso owners respetan) — esto puede romper migraciones de datos que el owner hace. **Solución**: ejecutar migraciones de datos con rol `postgres` o `service_role` (BYPASSRLS).

### 9.3 Rollback

Cada migración tiene `downgrade()` que revierte en orden inverso. Para rollback completo del sprint:

```bash
alembic downgrade 002_add_vector_columns
```

Esto ejecuta:
- Drop RLS policies (`008` downgrade).
- Drop tables de subscriptions, audit_uploads, recruiter_candidates, users_cvs, users_refresh_tokens, users (`003`–`007` downgrades).

Después del rollback, dual auth puede seguir funcionando en modo API-key-only (porque `BACKEND_API_KEY` se mantiene). El frontend puede re-deployarse con `PUBLIC_BACKEND_API_KEY` si se necesitara volver al modo pre-Sprint-2.

Stripe: ningún downgrade (datos en Stripe persisten). En el peor caso, deshabilitamos Checkout devolviendo 503 desde `/v1/billing/checkout` y los webhooks siguen llegando pero la lógica de upsert en `subscriptions` se ignora (defensive: si la tabla no existe, el handler captura el error y responde 200 a Stripe para evitar retries infinitos).

---

## 10. Decisiones resueltas (las 10 preguntas abiertas)

### 10.1 RLS mechanism: `SET app.current_user` GUC + policies ✓

**Decisión**: PostgreSQL Row-Level Security con GUC `app.current_user_id` y `app.current_role`, seteadas vía `SET LOCAL` dentro de cada transacción. Policies en cada tabla user-owned (`users_cvs`, `recruiter_candidates`, `subscriptions`).

**Por qué**: GUC + policies es el patrón estándar de Postgres para RLS por usuario. `SET LOCAL` (no `SET`) garantiza que el contexto vive solo la transacción — no contamina la pool. Las policies `FORCE ROW LEVEL SECURITY` (no solo `ENABLE`) hacen que incluso el owner de la tabla respete las policies, blindando contra errores de bypass por el rol `postgres`.

**Alternativas descartadas**:
- Multi-tenant con schema-per-user: complejidad operacional enorme (migraciones por schema, conexiones por schema), overkill para 2 roles.
- Row-level security via columna `tenant_id` sin GUC: requiere WHERE en cada query — error-prone.
- App-layer filtering only (sin RLS): defense-in-depth débil, una query nueva sin WHERE filtra datos.

### 10.2 Cron retention: GitHub Actions schedule llamando endpoint protegido ✓

**Decisión**: Workflow `.github/workflows/audit-retention.yml` con `cron: '17 3 * * *'` que llama `POST /internal/audit/cleanup` con bearer token (`AUDIT_CLEANUP_TOKEN` en secrets de GitHub + Render). El endpoint valida con `secrets.compare_digest`.

**Por qué**: Render free tier no soporta cron jobs nativos. GitHub Actions es gratis para repos públicos y hasta 2000 min/mes en privados. El schedule diario a las 03:17 UTC es off-peak. El endpoint interno está exento de API key pública (atajo de riesgo: en modo protegido, este endpoint aceptaría API key, pero el path `/internal/*` queda excluido del router `verify_api_key` y usa su propio token).

**Alternativas descartadas**:
- pg_cron extension: requiere rol superuser en Neon (no disponible).
- Worker process en Render con asyncio sleep loop: consume dyno hours 24/7.
- APScheduler in-process: igual al anterior, además pierde el schedule si el dyno duerme.

### 10.3 Audit → signup linking: hash token en cookie al capturar email, exchange on signup ✓

**Decisión**: Al capturar email en `/v1/audit/{id}/capture-email`, el backend setea cookie httpOnly `audit_link = base64(sha256(audit_id + SECRET_SALT))` con Max-Age=30 d. El frontend envía el valor de la cookie en el body del registro. El backend matchea contra `audit_uploads.email_captured` (encriptado) y setea `linked_user_id`.

**Por qué**: hash + secret server-side evita que el cliente manipule el valor y se vincule a un audit ajeno. Cookie httpOnly previene XSS. Max-Age=30 d matchea la ventana de retención.

**Alternativas descartadas**:
- Token en localStorage: vulnerable a XSS.
- Pass audit_id en URL (?ref=audit_<id>): visible en logs, enlaces referidos.
- Email magic link que auto-vincula al primer signup con ese email: no requiere cookie pero race condition si dos audits con mismo email + ventana corta.

### 10.4 Verificación de email: soft gate (allow login, banner, hard gate solo para features pagas) ✓

**Decisión**: El usuario puede hacer login sin verificar email; la UI muestra banner amarillo persistente "Verifica tu email para acceder a funciones pagas". El endpoint `/v1/billing/checkout` exige `email_verified_at IS NOT NULL` (hard gate). Free audit, gestión de CV, y match autenticado funcionan sin verificar.

**Por qué**: el funil de conversión no debe bloquear el valor principal (audit/match). Bloquear checkout evita fraude con tarjetas y disputas. El balance es maximizar activación temprana sin sacrificar calidad de suscripción.

**Alternativas descartadas**:
- Hard gate universal (no login sin verificar): fricción severa en el MVP, especialmente para recruiters que llegan por invitación.
- Sin verificación: abre la puerta a abuso con tarjetas y a emails no entregables para notificaciones de billing.

### 10.5 Recruiter tier pricing USD/mes: Starter $29 (50 matches), Business $99 (200), Agency $299 (unlimited) ✓

**Decisión**: Tres tiers como en la tabla §7.1. Job_seeker_free mantiene 3 matches/mes (límite actual sin auth). Job_seeker_monthly $9/mes con 50 matches.

**Por qué**: $29/$99/$299 es el rango "SMB recruiter" estándar (LinkedIn Recruiter Lite ≈ $170/mo, HireEZ ≈ $249/mo; nuestros precios undercut con IA local). 50/200/∞ covers los tres perfiles (consultora boutique, agencia mediana, RPO grande). $9 para job_seeker_monthly es accesible y comparable a Resume Worded / Teal ($5-12).

**Alternativas descartadas**:
- Un solo tier recruiter ($99 con 100 matches): castiga a recruiters chicos con poca actividad.
- Tier por seats: complica enforcement, difiere para Sprint 3+.
- Costo por match (pay-as-you-go): modelo distinto, requiere tracking de créditos y suscripciones múltiples — difiere.

### 10.6 Free-audit retention: borra `audit_uploads` con `linked_user_id IS NULL` después de 30 d ✓

**Decisión**: índice `idx_audit_expires` sobre `audit_uploads(expires_at) WHERE linked_user_id IS NULL`. El job de limpieza (§5.4) ejecuta `DELETE FROM audit_uploads WHERE linked_user_id IS NULL AND expires_at < NOW()`.

**Por qué**: auditoría que se convirtió en signup queda (linked), se mantiene para historial del usuario. La que no se convirtió se va a los 30 d (GDPR-friendly, evita acumular PDFs huérfanos).

**Alternativas descartadas**:
- Retención 7 días: muy agresivo para funil lento (signup puede llegar día 20).
- Retención 90 días: innecesario, riesgo legal mayor (más tiempo reteniendo datos no vinculados).
- Soft-delete con `deleted_at`: complica queries, no aporta valor.

### 10.7 JWT + API key precedence: JWT primero, API key fallback retorna user sintético `system` ✓

**Decisión**: `get_current_user` intenta JWT primero; si falla o no hay, intenta API key con `secrets.compare_digest`; si ninguna, 401. Cuando matchea API key, retorna `CurrentUser(id=0, name="system", role="service", auth_method="api_key")`. `require_role` rechaza `service` salvo en endpoints explícitamente permitidos (ej. cron interno, webhooks).

**Por qué**: API key se mantiene para MCP adapter y para reusar la lógica de auth sin duplicar rutas. `id=0` y `role="service"` es convencional y testeable. Endpoints sensibles (billing portal, password change) usan `require_role("job_seeker", "recruiter")` que rechaza `service` con 403 ROLE_FORBIDDEN.

**Alternativas descartadas**:
- API key primero, JWT fallback: rompe flujo de la UI (frontend ya envía JWT antes que nada) y obliga al MCP a no enviar JWT.
- Header separado (`X-Auth-Method: jwt` / `X-Auth-Method: api_key`): más explícito pero requiere coordinación cliente-servidor innecesaria.

### 10.8 Migration order: 003 → 004 → 005 → 006 → 007 → 008 (RLS último) ✓

**Decisión**: Ver §9.1.

**Por qué**: RLS al final evita que policies referencien columnas que aún no existen (ej. `users_cvs.owner_user_id` no existe hasta la migración 004). Aplicar RLS incremental es propenso a errores donde una tabla queda sin policy por accidente.

**Alternativas descartadas**:
- RLS por capability (PR3 con audit_uploads, PR4 con recruiter_candidates, etc.): 4 migrations de RLS, riesgo de inconsistencia entre policies.
- Aplicar RLS en PR1 (todo junto desde el inicio): bloquea el resto del sprint porque todo depende de tablas con RLS.

### 10.9 Stripe webhook: dedicated router `/api/v1/webhooks/stripe` con raw body + signature verification ✓

**Decisión**: Router separado `app/api/v1/webhooks/stripe.py`, montado sin `verify_api_key` ni JWT, lee raw body con `await request.body()`, verifica firma con `stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)`.

**Por qué**: FastAPI por default parsea JSON, lo que modifica el payload y rompe la verificación de firma de Stripe (que requiere bytes exactos). El endpoint NO se monta con auth dependency — Stripe no puede autenticarse vía JWT ni API key. La firma es el único autenticador.

**Alternativas descartadas**:
- Validar firma en middleware: complica routing, el middleware no ve raw body fácilmente.
- API key para webhook: requiere configurar secret adicional en Stripe; menos seguro que la firma criptográfica nativa.

### 10.10 PDF memory: 10MB hard cap, stream 64KB chunks a pypdf, fallback pdfminer.six si exception ✓

**Decisión**: `Content-Length` check en el endpoint (413 si >10MB); `pdf_parser.parse(blob)` lee el blob en chunks de 64KB y pasa a `pypdf.PdfReader(io.BytesIO(blob), strict=False)`. Si `MemoryError` u otra excepción de pypdf, retry con `pdfminer.six.high_level.extract_text`. Si ambos fallan, 503 `PDF_PARSE_FAILED` con stack trace y `cv_id` tentativo.

**Por qué**: Render free tier tiene 512MB RAM. pypdf es memory-friendly con streaming pero un PDF malformado con objetos comprimidos puede explotar. pdfminer.six es más robusto pero ~3x más lento. Hard cap 10MB evita que un cliente envíe un PDF de 500MB que tumbe el worker.

**Alternativas descartadas**:
- Limitar a 5MB: demasiado conservador para CVs con portafolio embebido.
- Sin fallback (pypdf only): falla mucho más seguido en PDFs escaneados parcialmente.
- Workers externos (Celery/RQ): introduce cola y Redis, overkill para Sprint 2.

---

## 11. Estrategia de tests

### 11.1 Cobertura por capa

| Capa | Qué se prueba | Cómo |
|---|---|---|
| **Unit** | bcrypt verify, JWT encode/decode, refresh rotation logic, RLS context setter, pdf_parser chunker, billing plan resolver | pytest con fixtures (sin DB) |
| **Integration DB** | Cada migración up/down, RLS isolation cross-user, FK constraints | pytest + Neon branch, db fixture por test |
| **Integration API** | Dual auth (JWT válido, JWT inválido, API key válida, sin credencial → 401), RBAC, dual-auth parity MCP | `httpx.AsyncClient` + `app.dependency_overrides` |
| **Contract** | Stripe webhook dedupe, idempotency-key checkout, rate limit (con `freezegun`) | mocks de `stripe.Webhook.construct_event` |
| **E2E (manual)** | Onboarding 3 pasos, free audit funnel end-to-end, recruiter match + ranking | scripts de smoke contra staging |

### 11.2 Tests específicos críticos

**RLS isolation** (`tests/test_rls_isolation.py`):

```python
async def test_cross_user_cv_blocked(db_session):
    # Setup: u1, u2 con sendos CVs
    await db_session.execute(text("SET LOCAL app.current_user_id = '1'"))
    cvs_u1 = (await db_session.execute(text("SELECT id FROM users_cvs"))).scalars().all()
    assert {c.id for c in cvs_u1} == {cv_u1.id}        # sólo ve el suyo

    await db_session.execute(text("SET LOCAL app.current_user_id = '2'"))
    cvs_u2 = (await db_session.execute(text("SELECT id FROM users_cvs"))).scalars().all()
    assert {c.id for c in cvs_u2} == {cv_u2.id}

async def test_cross_role_recruiter_blocks_job_seeker_cvs(db_session):
    await db_session.execute(text("SET LOCAL app.current_user_id = '99'"))
    await db_session.execute(text("SET LOCAL app.current_role = 'recruiter'"))
    cvs = (await db_session.execute(text("SELECT id FROM users_cvs"))).scalars().all()
    assert cvs == []
```

**Dual-auth parity** (`tests/test_dual_auth.py`):

```python
async def test_jwt_path_for_job_seeker(client, jwt_token_job_seeker):
    r = await client.get("/v1/users/me", headers={"Authorization": f"Bearer {jwt_token_job_seeker}"})
    assert r.status_code == 200
    assert r.json()["role"] == "job_seeker"

async def test_api_key_path_returns_service_user(client):
    r = await client.get("/v1/users/me", headers={"Authorization": f"Bearer {BACKEND_API_KEY}"})
    assert r.status_code == 403      # /v1/users/me is user-only, service rejected
    assert r.json()["detail"] == "ROLE_FORBIDDEN"

async def test_match_endpoint_accepts_both(client, jwt_token, jd_text):
    r1 = await client.post("/v1/match", json={"jd_text": jd_text, "profile_id": 1},
                          headers={"Authorization": f"Bearer {jwt_token}"})
    r2 = await client.post("/v1/match", json={"jd_text": jd_text, "profile_id": 1},
                          headers={"Authorization": f"Bearer {BACKEND_API_KEY}"})
    assert r1.status_code == r2.status_code == 200
```

**Stripe idempotency** (`tests/test_stripe_idempotency.py`):

```python
async def test_checkout_idempotency_key_returns_same_url(client, jwt_token):
    payload = {"plan_id": "recruiter_starter", "payment_method": "card"}
    headers = {"Authorization": f"Bearer {jwt_token}",
               "Idempotency-Key": "abc-123"}
    r1 = await client.post("/v1/billing/checkout", json=payload, headers=headers)
    r2 = await client.post("/v1/billing/checkout", json=payload, headers=headers)
    assert r1.json()["checkout_url"] == r2.json()["checkout_url"]

async def test_webhook_dedup(client):
    payload = {"id": "evt_test_1", "type": "checkout.session.completed", "data": {...}}
    sig = stripe_sign(payload, STRIPE_WEBHOOK_SECRET)
    r1 = await client.post("/v1/webhooks/stripe", content=payload, headers={"Stripe-Signature": sig})
    r2 = await client.post("/v1/webhooks/stripe", content=payload, headers={"Stripe-Signature": sig})
    assert r1.status_code == 200
    assert r2.status_code == 200
    # sólo 1 fila en subscriptions
```

**Rate limit** (`tests/test_audit_rate_limit.py`):

```python
async def test_audit_rate_limit_3_per_ip(client, freeze_time):
    for _ in range(3):
        r = await client.post("/v1/audit", multipart={"jd_text": "...", "file": pdf_fixture})
        assert r.status_code == 200
    r4 = await client.post("/v1/audit", multipart={"jd_text": "...", "file": pdf_fixture})
    assert r4.status_code == 429
    assert "Retry-After" in r4.headers
```

### 11.3 Piso de tests

Sprint 1 cerró con 117 tests verdes. Sprint 2 agrega ~80 tests nuevos:

- 15 auth (JWT, refresh rotation, RBAC, login brute force, dual auth)
- 10 user-accounts (registro, login, profile, verify-email)
- 12 cv-management (upload, parse, editor, RLS cross-user)
- 8 free-audit (rate limit, capture-email, retention logic)
- 12 recruiter-roster (CRUD, ranking, consent gate, audit log immutability)
- 15 billing (checkout idempotency, webhook dedupe, plan enforcement)
- 8 frontend smoke tests (build, i18n parity, navigation)

---

## 12. Riesgos (con mitigación)

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| 1 | **Chained PRs (5–6) acumulan drift entre merges**: PR3 depende de auth de PR1 ya mergeado | Alta | Media | PR1 se mergea primero; PR2–PR5 mantienen rama fresca con `main` antes de review |
| 2 | RLS filtra datos en producción (un policy mal escrita expone CVs cross-user) | Alta | Crítica | Tests RLS exhaustivos (§11.2); validación manual con `SET app.current_user_id` en Neon branch antes de prod; canary release |
| 3 | Dual auth rompe MCP en producción (race entre JWT y API key) | Baja | Alta | Tests de paridad en cada PR de auth; MCP smoke test post-deploy; rollback a single-API-key sigue disponible |
| 4 | pypdf OOM en Render 512MB con PDF patológico | Media | Media | Streaming chunks 64KB; fallback pdfminer.six; hard cap 10MB; alert en Sentry si `MemoryError` |
| 5 | Webhooks duplicados de Stripe (red retry) crean suscripciones dobles | Baja | Alta | Dedupe por `event.id` en `stripe_webhook_events` con UNIQUE constraint; respuesta 200 al duplicado |
| 6 | ToS legal sin revisión final expone a réclamo | Media | Media | Draft vigente en MVP; revisión legal diferida (out of scope Sprint 2); `tos_version` permite versionar y forzar re-consent |
| 7 | Cron GitHub Actions falla silenciosamente y `audit_uploads` se acumula | Baja | Media | Logging del job + alerta si `cleanup` no corre por 48h; monitor `SELECT count(*) FROM audit_uploads WHERE expires_at < now() - interval '2 days'` |
| 8 | Stripe API rate limit (100 req/s shared) durante pricing sync | Baja | Baja | Caché en memoria 5 min; webhook `price.updated` invalida caché |
| 9 | Token theft (refresh reuse) no detectado en MVP | Baja | Alta | Scenario del spec implementado + log a `auth_security_events`; revoca cadena completa; dashboard de seguridad en Sprint 3 |
| 10 | Paginación offset del roster es lenta con 1000+ candidatos | Baja | Baja | Límite práctico de Agency plan es ~200 candidatos activos; si crece, migrar a keyset pagination |
| 11 | Embedding recalculation en PATCH /cvs/{id} añade latencia | Media | Baja | Async task en background (no bloquea 200); cliente recibe `last_edited_at` inmediato; embedding se actualiza con next match |
| 12 | Frontend pierde `PUBLIC_BACKEND_API_KEY` accidentalmente reintroducida | Baja | Media | grep test en CI: `rg "PUBLIC_BACKEND_API_KEY|BACKEND_API_KEY" frontend/src/` falla si encuentra literal en código de runtime |

---

## 13. Recomendación de PR slicing — **CRÍTICO**

### 13.1 Defensa de Chained PRs sobre single-pr

**Postura**: este sprint DEBE ejecutarse como **chained PRs**. La alternativa single-pr con ~2150 líneas excede el budget por **3.6×** y no debe siquiera intentar `size:exception`.

**Cuantificación**:

- Forecast de exploración: **2150 líneas / ~7 PRs** según `proposal.md` §Rollout (auth ~300, CV ~350, roster ~200, Stripe ~300, audit ~250, UI ~400, UI recruiter/billing ~350).
- Budget por PR según convención del repo: **600 líneas** (Sprint 1 cerró con PRs de 60–550 l).
- Single-pr requeriría `size:exception` por **3.6×** del budget — probabilidad de aprobación: **muy baja**.
- Peor: incluso aprobado, un PR de 2150l imposibilita review efectivo (cambios en auth no pueden mergearse hasta que billing también esté listo; un bug en CV bloquea Stripe; etc.).

**Por qué chained** (no single-pr, no scope-trim):

1. **Auth es un gate universal**: `get_current_user` cambia de signature; todo endpoint que la usa debe migrar en el mismo PR. Pero **billing**, **audit**, **CV management** y **recruiter roster** pueden vivir sin auth nuevos hasta que PR1 esté mergeado.
2. **Stripe depende de users**: necesitas `users.id` y JWT para crear suscripciones. PR1 (auth) es prerequisito de PR5 (billing).
3. **Frontend depende de todo backend**: PR7 (frontend) consume la API completa; entra último.
4. **RLS depende de todas las tablas**: PR6 (RLS) entra después de PR2 (users_cvs), PR4 (recruiter_candidates), PR5 (subscriptions).
5. **Cada PR entregable**: PR1 ya da valor (login funcional); PR2 ya da valor (CV management con API key service); PR3 ya da valor (funnel anonymous → email).

**scope-trim como fallback**: si el equipo decide recortar, las candidatas son:
- Diferir PSE CO (cards-only en Sprint 2, PSE en Sprint 3).
- Diferir ranking híbrido (sólo CRUD roster en Sprint 2, ranking en Sprint 3).
- Diferir editor estructurado (sólo upload PDF en Sprint 2, editor en Sprint 3).

Pero estas NO son necesarias si se acepta chained PRs.

### 13.2 Plan de PRs encadenados

| PR | Contenido | Issues | Líneas ~ | Tests | Migraciones | Depende de |
|---|---|---|---|---|---|---|
| **PR1 — Auth foundation** | Migración 003 (users + refresh_tokens); `get_current_user` JWT-first con API key fallback; `require_role`; `/v1/auth/register\|login\|refresh\|logout\|verify-email/*`; `/v1/users/me` + password change; `core/config.py` JWT_* | #1, #2 | ~480 | 25 (auth, RBAC, dual auth parity) | 003 | — |
| **PR2 — CV management** | Migración 004 (users_cvs); `pdf_parser.py` streaming + fallback; `/v1/cvs` CRUD; embedding recalc en PATCH; CV embedding HNSW index | #3 | ~380 | 12 (upload, parse, edit, RLS cross-user) | 004 | PR1 |
| **PR3 — Free audit** | Migración 006 (audit_uploads + funnel); `/v1/audit` con rate limit; `audit_retention.py` + endpoint `/internal/audit/cleanup`; GitHub Actions workflow; audit_funnel_events | #4 | ~280 | 8 (rate limit, capture-email, retention) | 006 | PR1 |
| **PR4 — Recruiter roster** | Migración 005 (recruiter_candidates, recruiter_consent, recruiter_analyses, recruiter_audit_log); `/v1/recruiter/candidates/*` + match + ranked + append-only trigger; recruitment_audit_log immutability | #5 | ~320 | 12 (CRUD, consent gate, ranking, audit log immutability) | 005 | PR1 |
| **PR5 — Billing** | Migración 007 (subscriptions, stripe_webhook_events); `/v1/billing/plans\|checkout\|portal\|subscription`; `/v1/webhooks/stripe` con raw body; `services/billing.py` con idempotency; plan enforcement en match | #6, #7 | ~380 | 15 (checkout idempotency, webhook dedupe, plan enforcement) | 007 | PR1 |
| **PR6 — RLS** | Migración 008 (RLS policies en users_cvs, recruiter_candidates, subscriptions, recruiter_audit_log append-only); `rls_context.py`; tests RLS exhaustivos; canary checklist | #8 | ~120 | 10 (cross-user SELECT/INSERT/UPDATE/DELETE; cross-role; contexto ausente) | 008 | PR2, PR4, PR5 |
| **PR7 — Frontend** | Sesión store + auto-refresh; nuevo `api/client.ts`; rutas login/register/verify-email/cvs/audit/recruiter/billing/onboarding; i18n parity CI; dep greps para evitar API key reintroducida | #9 | ~450 | 8 (smoke E2E build + i18n parity + dep greps) | — | PR1–PR6 deployados |

**Total**: ~2410 líneas en 7 PRs (incluyendo tests y migraciones). Ningún PR excede 500l.

### 13.3 Orden de merge y dependencias estrictas

```
PR1 ──► PR2 ──┐
   └──► PR3   │
   └──► PR4 ──┤
   └──► PR5 ──┴──► PR6 ──► PR7
```

PR2, PR3, PR4, PR5 son **paralelos** después de PR1 (no se bloquean entre sí porque operan sobre tablas distintas y los endpoints no colisionan). PR6 unifica RLS y entra tras los tres que tocan tablas user-owned. PR7 entra al final con todo el backend en producción.

PR1 es **el gate**: sin auth, ningún otro PR tiene cómo probar end-to-end en staging (los tests sí funcionan, pero la integración con frontend no).

### 13.4 Plan de fallback si PR-D se atrasa (analogía con Sprint 1)

Sprint 1 documentó fallback similar para frontend. Aquí, si PR6 (RLS) se atrasa:

- Los PRs anteriores ya entregan valor con checks de servicio (defense in depth funciona aunque RLS no esté aplicado).
- RLS puede entrar como hotfix post-sprint (es 1 migración + tests).
- Rollout en Neon branch primero; aplicar a producción sólo después de validar que el manual test cross-user no filtra datos.

Si PR5 (billing) se atrasa:

- Planes freemium siguen funcionando (free job_seeker + free recruiter sin matches).
- Stripe queda pendiente; matching con API key + JWT sin enforcement de tier (todo el mundo es "free" hasta Sprint 3).

Si PR3 (free audit) se atrasa:

- No bloquea PR2, PR4, PR5.
- Free audit es independiente del flujo autenticado.

### 13.5 Justificación frente a `size:exception`

`size:exception` para 2150l implica:

- Review de un solo humano leyendo 2150l en una sentada (no efectivo).
- Múltiples concerns mezclados (auth + RLS + billing + frontend): un bug en auth bloquea review de billing.
- Riesgo de merge revert por bugs en producción: rollback de 2150l es caro.

Chained PRs:

- Cada PR < 500l, reviewable en < 30 min.
- Auth, billing, CV, audit son independientes: se mergean por separado.
- Si un PR falla en prod, rollback es 1 commit.
- CI por PR: 7 puertas de calidad vs 1 puerta única.

**Conclusión**: `chained-prs` es la única opción defendible. `single-pr-exception` debe rechazarse. `scope-trim` es opcional y solo si el equipo decide reducir alcance explícitamente.

---

## 14. Preguntas abiertas residuales

- [ ] Confirmar texto final del ToS recruiter con legal (draft v1.2 vigente en MVP; revisión formal en Sprint 3+).
- [ ] Confirmar `tos_version` a registrar en `recruiter_consent` para migraciones futuras (forzar re-consent).
- [ ] Confirmar `AUDIT_CLEANUP_TOKEN` rotation policy (mensual vs trimestral vs on-demand).
- [ ] Confirmar si `recruiter_audit_log` debe ser append-only a nivel Postgres (trigger) o solo a nivel API (no exponer endpoints de update/delete). El diseño actual asume trigger (defense in depth).
- [ ] Confirmar límite práctico de roster antes de migrar de offset a keyset pagination (estimado: >500 candidatos).