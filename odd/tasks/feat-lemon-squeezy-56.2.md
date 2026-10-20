# Feature: Lemon Squeezy provider (#56 slice 2)

> **Issue #56** slice 2. Predecesor: slice 1 (`88b4ef7`, BillingProvider adapter en main).
> **Objetivo**: `LemonSqueezyProvider` funcional (MoR, USD/global, persona natural OK) + migración 028 + endpoints de billing de usuario.

## Decisión de diseño principal

**Cliente LS con httpx (patrón Tavily de `offer_search_client.py`)**: errores tipados (`LemonSqueezyError` / `AuthError` / `RateLimitError` / `TimeoutError` / `ConnectionError`), `httpx.AsyncClient` por-request, timeout 12s. El provider (`providers/lemon_squeezy.py`) consume el client y traduce al contrato `BillingProvider` del slice 1.

**Idempotencia de webhooks multi-provider**: tabla nueva `payment_webhook_events` (provider + event_id UNIQUE juntos) en vez de una tabla por pasarela. La de Stripe (`stripe_webhook_events`) NO se toca — migrarla es deuda separada.

**Custom data passthrough**: el checkout de LS lleva `checkout_data.custom = {"user_id": ..., "plan_id": ...}` que LS reenvía en `meta.custom_data` de cada webhook. Es el mecanismo para ligar eventos a usuarios SIN guardar customer_id nuestro.

## Specs

> **S1**: `backend/app/services/lemon_squeezy_client.py` (NUEVO). `LemonSqueezyClient(api_key, timeout=12.0)`. Base URL `https://api.lemonsqueezy.com/v1`. Header `Authorization: Bearer <key>`. Métodos: `create_checkout(store_id, variant_id, custom: dict, test_mode: bool, expires_at: datetime | None = None) -> dict` (devuelve `{"checkout_url": ..., "checkout_id": ...}` leyendo `data.attributes.url` / `data.id`), `get_subscription(subscription_id: str) -> dict` (attributes normalizados), `cancel_subscription(subscription_id: str) -> dict` (PATCH con `attributes.cancelled: true`). Errores tipados: 401→AuthError, 429→RateLimitError (con retry_after del header), timeout→TimeoutError, connect→ConnectionError, resto→LemonSqueezyError(status_code).

> **S2**: `backend/app/services/providers/lemon_squeezy.py` (REEMPLAZA el stub). `LemonSqueezyProvider(BillingProvider)`:
> - `__init__`: exige `lemon_squeezy_api_key` + `lemon_squeezy_store_id` → si faltan, `ProviderNotConfiguredError` (mismo contrato que Stripe en slice 1).
> - `create_checkout(plan, user, return_urls, *, idempotency_key=None)`: resuelve `variant_id` por `plan_id` desde Settings (4 variantes stubbed); arma `custom={"user_id": str(user["id"]), "plan_id": plan["plan_id"]}`; `test_mode` desde `Settings.lemon_squeezy_test_mode` (NUEVA setting, default `true`); devuelve `CheckoutSession(checkout_url, session_id=checkout_id, provider_id="lemon_squeezy")`. La `return_urls` va en `checkout_options.redirect_url` (LS redirige solo al success; el cancel lo maneja el frontend con history.back — documentar).
> - `handle_webhook(payload, signature, headers)`: verifica `X-Signature` (header configurable) = hex HMAC-SHA256 del payload con `lemon_squeezy_webhook_secret`, con `hmac.compare_digest`. Si no coincide → `ValueError("Invalid signature")` (el endpoint lo mapea a 400, mismo patrón que Stripe en slice 1). Si secret falta → `ProviderNotConfiguredError`. Devuelve `WebhookEvent(event_type=meta.event_name, user_id=int(meta.custom_data.user_id) si existe, plan_id=meta.custom_data.plan_id, raw=payload_dict)`.
> - `get_subscription_status(user_id)`: lee la fila `Subscription` del user (RLS service context), toma el `payment_methods.provider_subscription_id` más reciente para LS, llama `client.get_subscription`, mapea `status` LS→nuestro (`active`→`active`, `cancelled`→`canceled`, `expired`→`canceled`, `on_trial`→`trialing`, `paused`→`past_due`), `renews_at`/`ends_at`→`current_period_end`.
> - `cancel_subscription(user_id)`: igual lookup, llama `client.cancel_subscription`. Idempotente: si no hay sub LS registrada → no-op (mismo contrato que Stripe).
> - `supports_country("CO")` → True (LS es global/MoR).

> **S3**: `backend/alembic/versions/028_payment_methods.py` (NUEVA, reversible). Dos tablas:
> - `payment_methods`: id PK, user_id FK users NOT NULL, provider VARCHAR(30) NOT NULL (`stripe`|`lemon_squeezy`|`mercadopago`), provider_customer_id VARCHAR(100) NULL, provider_subscription_id VARCHAR(100) NULL UNIQUE, status VARCHAR(20) NOT NULL, plan_id VARCHAR(50) NOT NULL, current_period_end TIMESTAMPTZ NULL, created_at/updated_at TIMESTAMPTZ server_default NOW(). Index `(user_id)`, index `(provider, provider_subscription_id)`. **RLS habilitado + policy owner** (`owner_user_id = current_setting('app.current_user_id')::int`) día uno, patrón 023/027.
> - `payment_webhook_events`: id PK, provider VARCHAR(30) NOT NULL, event_id VARCHAR(100) NOT NULL, type VARCHAR(50) NOT NULL, payload_json JSONB, processed_at TIMESTAMPTZ NULL, created_at. **UNIQUE (provider, event_id)** para idempotencia. Sin RLS (escritura service-only, igual que `stripe_webhook_events` — patrón interno/`set_rls_service`).
> - Downgrade: DROP TABLE payment_webhook_events → payment_methods (orden por dependencia FK).

> **S4**: `backend/app/api/v1/webhooks/lemonsqueezy.py` (NUEVO). `POST /v1/webhooks/lemonsqueezy` — lee raw body + header de firma (desde Settings), `provider.handle_webhook(...)`, mapea: `ValueError("Invalid signature")`→400, `ProviderNotConfiguredError`→503. Idempotencia: INSERT en `payment_webhook_events` con `ON CONFLICT DO NOTHING` (o select-then-insert como Stripe); si ya procesado → `{"status": "already_processed"}`. Dispatch: `subscription_created`/`subscription_updated` → upsert `Subscription` (plan desde custom_data, status mapeado, current_period_end desde renews_at) + upsert `payment_methods`; `subscription_cancelled`/`subscription_expired` → status `canceled` + `ends_at`; `subscription_resumed` → `active`; `subscription_payment_success` → refresh period. Montado en `main.py` junto al router de Stripe.

> **S5**: `backend/app/api/v1/billing.py` (EXTIENDE). `GET /v1/me/billing` → para el usuario autenticado: plan actual (tier_limits), status de subscription, `provider` activo (de payment_methods o Settings), usage del mes. `DELETE /v1/me/billing` → llama `provider.cancel_subscription(user_id)`; 404 si no hay sub de pago. Ambos con el patrón `_load_user` + RLS del slice 1.

> **S6**: Settings: `lemon_squeezy_test_mode: bool = True` (env `LEMON_SQUEEZY_TEST_MODE`). `.env.example` + `docs/DEPLOY.md` completan la sección LS (test_mode + guía de dónde sacar cada valor en el dashboard LS).

> **S7**: Tests:
> - `tests/test_lemon_squeezy_client.py` (DB-free): httpx `MockTransport` para los 3 métodos + taxonomía de errores (401/429/timeout/connect/500) + header Bearer correcto.
> - `tests/test_billing_provider.py` (EXTIENDE, DB-free): firma HMAC válida/inválida (payload sintético + hmac en test), WebhookEvent mapea custom_data, factory LS sin key → ProviderNotConfigured, create_checkout con MockTransport inyectado (patch del client).
> - `tests/test_webhooks_lemonsqueezy.py` (DB, CI): firma válida → 200 + Subscription upsert + idempotencia (segunda llamada → already_processed), firma inválida → 400, evento cancelled → status canceled.
> - `tests/test_billing.py` (EXTIENDE, DB, CI): GET /v1/me/billing shape, DELETE sin sub → 404, DELETE con sub → 200 + status canceled.
> - Fixture pattern del slice 1: `monkeypatch.setattr(settings, "billing_provider_active", "lemon_squeezy")` + patch de api_key/store_id — NUNCA env vars globales (lru_cache de Settings).

## Fuera de alcance de este slice

- Checkout embebido (`embed=true` modal) — slice 5 UX
- Portal de LS para el usuario (manage subscription) — slice 5
- Migración de `stripe_webhook_events` → `payment_webhook_events` (deuda separada, Stripe sigue con su tabla)
- Frontend UI de billing — slice 5
- Proration / upgrade entre planes
- KYC gate — slice 4

## Criterio de aceptación

- [ ] `LemonSqueezyProvider` pasa el contrato `BillingProvider` (5 métodos) y el factory lo resuelve con `BILLING_PROVIDER_ACTIVE=lemon_squeezy`
- [ ] Webhook LS verificado con HMAC real (test genera firma válida con hmac) y rechaza firma inválida con 400
- [ ] `subscription_created` activa la Subscription del user (plan correcto) y persiste `payment_methods`
- [ ] Segunda entrega del mismo event_id → `already_processed` sin doble escritura
- [ ] Migración 028 sube y baja limpia (`alembic upgrade head` + `downgrade -1`) — CI la valida
- [ ] 17 tests del slice 1 siguen verdes; nuevos tests client (DB-free) y webhook (CI) verdes
- [ ] Suite completa en CI 7/7
- [ ] El autor puede setear las 6 env vars de LS y hacer un checkout test-mode real end-to-end (validación manual post-deploy)

## Tasks

> **T1**: `lemon_squeezy_client.py` (test-first con MockTransport, DB-free)

> **T2**: `providers/lemon_squeezy.py` reemplaza stub (test-first, DB-free con MockTransport)

> **T3**: Migración 028 (`payment_methods` + `payment_webhook_events`, RLS day-one, reversible)

> **T4**: Webhook endpoint + dispatch + idempotencia (test-first, DB para CI)

> **T5**: `GET /v1/me/billing` + `DELETE /v1/me/billing`

> **T6**: Settings `lemon_squeezy_test_mode` + `.env.example` + `DEPLOY.md` guía dashboard LS

> **T7**: ✅ PR #116 — squash commit `b4ea0ad` en `main` (2026-10-20). Incluye 4 commits intermedios: `5e6b4e7` (T1+T2+T6), migración+webhook (T3+T4+T5), `55a59df` (clean_db truncation + cancel status local), `037c0c1`+`eb1808c` (event-id por hash del payload + F821 fix). CI 7/7.

## Log

- L1: Slice 1 mergeado (`88b4ef7`). El stub LS de slice 1 deja el esqueleto: este slice lo reemplaza. Las settings LS ya existen (api_key, store_id, webhook_secret, signature_header, 4 variants) — solo se agrega `test_mode`.
- L2: Usuario no tiene aún credenciales LS → estrategia test-first con httpx MockTransport; credenciales se cargan como env vars en el momento del deploy. Nada del código depende de tener la cuenta hoy.
- L3: Patrón del cliente copiado de `offer_search_client.py` (Tavily): misma taxonomía de errores, mismo estilo async, mismo timeout. Reduce la superficie de review.
- L4: Idempotencia de webhooks: tabla genérica `payment_webhook_events` con UNIQUE(provider, event_id) en vez de clonar `stripe_webhook_events`. La tabla Stripe se queda como está (migrarla rompería el historial ya procesado).

## Variables de entorno (estado tras este slice)

```
BILLING_PROVIDER_ACTIVE=mock            # mock | stripe | lemon_squeezy | mercadopago
LEMON_SQUEEZY_API_KEY=                  # Dashboard LS → Settings → API keys
LEMON_SQUEEZY_STORE_ID=                 # URL del dashboard: /dashboard/stores/<id>
LEMON_SQUEEZY_WEBHOOK_SECRET=           # Dashboard LS → Settings → Webhooks → signing secret
LEMON_SQUEEZY_SIGNATURE_HEADER=X-Signature
LEMON_SQUEEZY_TEST_MODE=true            # false solo con live keys
LEMON_SQUEEZY_VARIANT_JOB_SEEKER_MONTHLY=
LEMON_SQUEEZY_VARIANT_RECRUITER_STARTER=
LEMON_SQUEEZY_VARIANT_RECRUITER_BUSINESS=
LEMON_SQUEEZY_VARIANT_RECRUITER_AGENCY=
```

## Riesgos

- **R1 — Webhooks en Render free dormido**: LS reintenta ~3 días con backoff; el backend despierta con el POST. Igual que Stripe en slice 1 — aceptable para suscripciones.
- **R2 — test_mode true en prod por descuido**: la setting default es `true`; el checklist de deploy debe incluirla. Mitigación: log warn al boot si `BILLING_PROVIDER_ACTIVE=lemon_squeezy` y `LEMON_SQUEEZY_TEST_MODE=true` en producción.
- **R3 — Mapping de status LS**: LS usa `on_trial`/`paused` que nuestro dominio no tiene. Mapeo documentado en S2; tests pinnean cada caso.

## S5 Correction (implemented)

The spec above named `GET /v1/me/billing` and `DELETE /v1/me/billing`. In practice, the existing `GET /v1/billing/subscription` already returns plan/status/limits/usage — creating a parallel `/v1/me/billing` would duplicate it. Instead:
- **Extended** `SubscriptionResponse` with `provider: str | None` and `cancel_at_period_end: bool`.
- **Extended** the `GET /v1/billing/subscription` handler to populate `provider` from the newest `PaymentMethod` row (preferring `status='active'`).
- **New** `DELETE /v1/billing/subscription` — same RLS pattern as the other protected endpoints, calls `provider.cancel_subscription(user_id)`, 404 if no paid `Subscription` row, 503 if provider unconfigured. Best-effort update of the user's newest LS `PaymentMethod` to `canceled`.
- Both new fields are optional (`None` / `False` defaults) so existing API consumers are not broken.
