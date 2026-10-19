# Feature: Pasarela de pagos (#56) — v2.0 slice 1

> **Issue #56**: pasarela Colombia (PSE / Nequi / Daviplata vía Wompi/Bold/PayU o Stripe+PSE).
> **Alcance ampliado**: USD/global (Job Seekers no-CO + Recruiters internacionales) → segunda pasarela necesaria. Decisión arquitectónica: **abstraer BillingProvider** para no acoplarse a un único vendor.

## Decisión de diseño principal

**Patrón Adapter (`BillingProvider`)** detrás de un factory: cada pasarela implementa un contrato común (create_checkout, handle_webhook, get_subscription_status). Esto convierte el "Issue #56 Colombia-only" en una decisión de **catálogo de proveedores disponibles por geografía/moneda**, no en una reescritura de billing cada vez que sume un vendor.

Proveedores planeados (en este orden):

1. **Lemon Squeezy** (MoR) — USD, Job Seekers + Recruiters globales. Persona natural ✅. Maneja EU VAT / US sales tax. Deposita a Bancolombia/BBVA en COP/USD. **Este slice**.
2. **Mercado Pago** (directo) — COP, CO early adopters (PSE/Nequi/Bancolombia). Persona natural con Cédula ✅.
3. **Wompi / Bold** — descartado por ahora (requieren SAS en CO). Reconsiderar cuando se abra empresa.
4. **Stripe** — código actual de `billing.py` queda como `StripeProvider` por compatibilidad, pero **se deja no-instanciable por default** (sin `STRIPE_SECRET_KEY` en prod) para forzar uso de las nuevas pasarelas. Borrar el switch a Stripe en un slice futuro si se confirma.

Razón de orden: **LS primero** porque cubre el 90% del público objetivo (Job Seeker Latam-no-CO + Recruiter globales) con persona natural + sin tarjeta. MP es un slice separado para mantener cada PR acotado.

## Contexto (del issue, del repo, del PRD)

- Mercado objetivo: devs Latam aplicando a US/EU (Job Seeker $9/mes) + equipos de recruiting chicos (Recruiter $29–$299/mes). Precios en **USD**, planes en `PLANS_CATALOG` (5 tiers: free, job_seeker_monthly, recruiter_starter, recruiter_business, recruiter_agency).
- Restricción dura del proyecto: stack 100% free tier sin tarjeta de crédito (STACK.md). Lo mismo aplica al autor como vendedor: **no quiere abrir SAS ni LLC para cobrar**.
- Issue #56 está marcado como **"KYC-gated"** en ROADMAP.md (sección v2.0 dic 2026). KYC real (Cédula + selfie o similar) precede a cualquier cobro en producción pública.
- `backend/app/api/v1/billing.py` actual usa exclusivamente Stripe (rotas: `/plans`, `/checkout`, `/portal`, `/webhooks/stripe`). Auditoría inicial reportó 500s (`current_user` mal tipado), `email_verified_at` nunca seteado, `verify-email` stub. El refactor a Adapter no debe empeorar esto.
- `backend/app/services/stripe_client.py` ya existe y se mantiene como un provider más (no se borra todavía, se traspasa a `providers/stripe.py`).
- Sub-cosas que sobreviven intactas: `tier_limits.PLAN_LIMITS`, `Subscription` model, `UsageCounter`, `webhooks/stripe.py`.
- El usuario (autor del repo) está físicamente en Colombia, persona natural, sin empresa, sin tarjeta. Él es el primer cliente y tester.

## Specs

> **S1** (slice 1 — este): `BillingProvider` ABC en `backend/app/services/billing_provider.py` define el contrato mínimo: `create_checkout(plan, user) -> CheckoutSession`, `handle_webhook(payload, signature) -> WebhookEvent`, `get_subscription_status(user_id) -> SubStatus`, `cancel_subscription(user_id) -> None`. Cada provider expone además un `provider_id` y un `supports_country(country) -> bool`. Factory `get_billing_provider(provider_id) -> BillingProvider` resuelve por config (`BILLING_PROVIDER_ACTIVE` en Settings, default `lemon_squeezy` para prod / `mock` para tests).

> **S2** (slice 1): `providers/stripe.py` envuelve el código actual de `stripe_client.py` (no reescribe, solo adapta). Al instanciar verifica `STRIPE_SECRET_KEY` set; si no, el provider se reporta como "no configurado" y el factory devuelve 503 PAYMENT_PROVIDER_UNCONFIGURED. Webhook handler existente (`app/api/v1/webhooks/stripe.py`) sigue funcionando, solo cambia que la verificación de firma pasa por la interface.

> **S3** (slice 1): `billing.py` refactoriza para usar el factory. Mantiene los endpoints existentes (`/plans`, `/checkout`, `/portal`, `/webhooks/stripe`). Agrega un nuevo endpoint `POST /v1/billing/checkout/{provider}` que delega al provider correspondiente. La verificación de email sigue siendo gate previo a cualquier checkout. **Tests existentes deben seguir pasando** — refactor sin cambio de comportamiento.

> **S4** (slice 1): Settings agrega `billing_provider_active: Literal["lemon_squeezy", "mercadopago", "stripe", "mock"] = "mock"` (default `mock` en dev para no depender de credenciales). `lemon_squeezy_api_key`, `lemon_squeezy_store_id`, `lemon_squeezy_webhook_secret`, `lemonsqueezy_signature_header_name` (LS usa `X-Signature`). Los 4 viejos `stripe_price_*` siguen existiendo para Stripe provider pero se documentan como legacy.

> **S5** (slice 2 — Lemon Squeezy): Implementar `LemonSqueezyProvider` (test-first con `httpx.MockTransport` o `respx`). Crear variant por plan (LS usa "variants" en lugar de "prices"). Checkout devuelve URL de LS al frontend (no redirect nuestro). Webhook maneja `subscription_created`, `subscription_updated`, `subscription_cancelled`, `subscription_resumed`, `subscription_expired`. Status sync: leer `/v1/subscriptions` y mapear a `tier_limits.PLAN_LIMITS`. Tabla `payment_methods` (migración 028) guarda `provider`, `provider_customer_id`, `provider_subscription_id`, `status`, con RLS day-one como el patrón de 023. Endpoints: `GET /v1/me/billing` (devuelve subscription_status real), `DELETE /v1/me/billing` (cancel).

> **S6** (slice 3 — Mercado Pago): Implementar `MercadoPagoProvider`. Checkout devuelve `init_point` de MP. Payment methods: card, PSE, Nequi (vía preference `payment_methods.excluded_payment_types` y `payment_methods.installments`). Webhook maneja `payment.created`, `payment.updated`, `subscription.created/updated/cancelled`. Tokenización del customer (MP usa `customer_id` por user, distinto de Stripe). Tabla `payment_methods` se popula para los users CO.

> **S7** (slice 4 — KYC gate): Endpoint `POST /v1/kyc/submit` recibe Cédula + selfie + datos básicos. Para v0 usar verificación manual (admin marca `kyc_status = "approved"`). Para v1 integrar Onfido o Sumsub (ambos tienen programa Latam gratis hasta cierto volumen). Tabla `kyc_records` con RLS day-one. El checkout queda bloqueado si `user.kyc_status != approved`. Email verification pre-existente sigue siendo el primer gate (no se cambia).

> **S8** (slice 5 — UX final): Frontend `/billing` muestra: (a) plan actual + usage, (b) selector "Pagar en USD" → Lemon Squeezy button, "Pagar en COP" → Mercado Pago button (solo si user.country == CO), (c) historial de pagos desde `payment_methods`. i18n en ES/EN (LS checkout URLs tienen parámetro `?embed=1` para abrir en modal). Tests vitest del componente.

> **S9** (slice 5 — tax compliance): Configurar LS para que LS remita EU VAT a clientes EU (en su dashboard, no código). Idem US sales tax. MP ya retiene locally según país. Documentar en `docs/PAYMENTS.md`.

> **S10** (cada slice): Tests — unitarios del provider (test-first con mocks), integración del endpoint, e2e con provider mock (no contra APIs reales en CI), guard de "no real API calls in CI" en pytest marker. Suite verde en CI.

## Fuera de alcance de este slice

- Wompi / Bold (sumar cuando se abra SAS)
- dLocal
- Crypto
- Monedas distintas a USD/COP en el catálogo (LS soporta más, pero no las exponemos todavía)
- One-time payments (descarga del CV adaptado, etc.) — suscripciones mensuales únicamente
- Proration, upgrades/downgrades entre planes (LS lo soporta; lo sumamos en slice 6 si hay demanda)

## Criterio de aceptación (Issue #56 — adaptación)

- [ ] Adapter `BillingProvider` con 4 vendors como mínimo (mock, stripe, lemonsqueezy, mercadopago) y tests de conmutación por config (S1)
- [ ] `billing.py` refactorizado sin cambio de comportamiento observable para clientes actuales (S3)
- [ ] Lemon Squeezy provider funcional contra LS sandbox (USD, tarjeta, Apple/Google Pay) (slice 2)
- [ ] Mercado Pago provider funcional contra sandbox de CO (PSE, Nequi, tarjeta) (slice 3)
- [ ] KYC gate bloquea checkout para usuarios no verificados (slice 4)
- [ ] UI selector país/método en `/billing` con i18n (slice 5)
- [ ] Suite verde en CI, ruff + mypy clean, 7/7 checks
- [ ] Author puede pagar su propio plan `job_seeker_monthly` con Cédula + PSE desde CO sin tarjeta personal (e2e manual)

## Tasks

> **T1**: `BillingProvider` interface + factory + tipos (`CheckoutSession`, `WebhookEvent`, `SubStatus`). Tests del factory (mock provider para tests).

> **T2**: Mover `stripe_client.py` a `services/providers/stripe.py` adaptando al contrato. `STRIPE_SECRET_KEY` ausente → `ProviderNotConfigured`. Mantener comportamiento para tests existentes.

> **T3**: Refactor `billing.py`: rutas usan el factory. Agregar `POST /v1/billing/checkout/{provider}`. El path `/v1/billing/checkout` viejo sigue funcionando con `BILLING_PROVIDER_ACTIVE`.

> **T4**: Settings + env vars + `.env.example` + `docs/DEPLOY.md` (nuevos secretos LS + MP).

> **T5**: Tests del slice 1: provider selection por config, 503 cuando provider no configurado, webhooks del mock provider, idempotencia en checkout. Suite verde.

> **T6**: ✅ PR #56.1 — commit `da16d78` en `feat/pasarela-pagos-56`. Slice 1 cerrado.

> **T7** (siguiente PR): Lemon Squeezy provider + migración 028 `payment_methods`.

> **T8** (siguiente PR): Mercado Pago provider.

> **T9** (siguiente PR): KYC gate.

> **T10** (siguiente PR): Frontend UX + tax docs.

## Log

- L1: Usuario abrió el tema con "Stripe me pide empresa en USA, estoy en Colombia como persona natural". Confirmé audiencia global (USD, Job Seekers Latam-no-CO, Recruiter globales) → el #56 CO-only no alcanza.
- L2: Revisión Engram + repo confirmó: stack free tier sin tarjeta (restricción del autor), Issue #56 marcado "KYC-gated" en ROADMAP, billing.py actual está roto pero el dominio está bien modelado (plan/feature/limit/sub/usage). Decisión: abstraer con Adapter, no rescribir.
- L3: LS como provider primario (USD/MoR, persona natural OK, cubre Job Seekers + Recruiters globales). MP como secundario (COP/CO/PSE/Nequi). Wompi queda descartado por ahora (requiere SAS).
- L4: Plan por slices vs "todo de una": cada PR acotado, suite verde por PR, deploy por PR. Aprende del patrón exitoso del #55 cron y del #101 embeddings.
- L5: Slice 1 implementado (commit `da16d78`) — Adapter + factory + MockProvider + StripeProvider wrap + refactor billing.py + Settings + .env.example + DEPLOY.md + 17 tests DB-free. Ruff clean, mypy clean. Compromiso original `af8bf24` se hizo sobre `main` por confusión de rama y se descartó vía `git reset --soft 7574a17` + `git stash --include-untracked` (cambios preservados como cherry-pick `da16d78` en la feature branch). El feature doc se commiteó por separado (no se bundle con feat). Docker Desktop down en la máquina del usuario → pytest local no corre; CI de GitHub Actions verifica la suite completa en el push.

## Migración necesaria

- **028** (slice 2): `payment_methods` table (id, user_id FK users, provider text, provider_customer_id text, provider_subscription_id text, status text, plan_id text, current_period_end timestamp, created_at, updated_at) + RLS day-one policy `owner_user_id = current_setting('app.current_user_id')::int`. Indexes `(user_id)`, `(provider, provider_subscription_id)`.
- **029** (slice 4): `kyc_records` table (id, user_id FK users, status: pending|approved|rejected, document_type, document_number, document_country, selfie_url, reviewed_by_user_id, reviewed_at, created_at) + RLS day-one.

## Riesgos

- **R1 — LS sandbox no refleja producción**: el sandbox de LS tiene quirks (subscriptions son simuladas; webhooks llegan encolar). Mitigación: test e2e manual con LS en modo test antes de declarar el slice 2 listo.
- **R2 — KYC vendor lock**: Onfido vs Sumsub vs Persona vs un mock-manual. Decidir antes del slice 4. v0 = mock-manual (admin aprueba), v1 = Sumsub si hay volumen.
- **R3 — Webhook delivery**: Render free duerme a los 15 min. Si la pasarela manda un webhook mientras el backend está asleep, LS/MP reintentan, pero los reintentos tienen ventanas cortas (Stripe ~3 días, MP ~4 días, LS ~3 días). Aceptable para suscripciones (no es crítico instantáneo); documentar el catch-up como en el #55 cron si es necesario.
- **R4 — Currency rounding**: plans están en USD cents. COP usa diferentes redondeos. Si LS devuelve cobre en COP a un user CO, el `price_cents` debe matchear el redondeo local. Documentar y, si hace falta, snapshot del tipo de cambio al crear el checkout.

## Variables de entorno nuevas (para el slice 1 + .env.example)

```
# Billing provider switch
BILLING_PROVIDER_ACTIVE=mock           # mock | stripe | lemon_squeezy | mercadopago

# Lemon Squeezy (slice 2)
LEMON_SQUEEZY_API_KEY=
LEMON_SQUEEZY_STORE_ID=
LEMON_SQUEEZY_WEBHOOK_SECRET=
LEMON_SQUEEZY_SIGNATURE_HEADER=X-Signature
# Variant IDs por plan (configurar en dashboard de LS):
LEMON_SQUEEZY_VARIANT_JOB_SEEKER_MONTHLY=
LEMON_SQUEEZY_VARIANT_RECRUITER_STARTER=
LEMON_SQUEEZY_VARIANT_RECRUITER_BUSINESS=
LEMON_SQUEEZY_VARIANT_RECRUITER_AGENCY=

# Mercado Pago (slice 3)
MERCADOPAGO_ACCESS_TOKEN=
MERCADOPAGO_PUBLIC_KEY=
MERCADOPAGO_WEBHOOK_SECRET=
```

---

*Sigue el patrón ODD de los features #55, #101, #108.*
