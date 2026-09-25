# Spec: billing

## Purpose

Integración con Stripe para planes de `job_seeker` (freemium + mensual) y `recruiter` (Starter / Business / Agency), incluyendo Checkout, webhooks firmados e idempotentes, y método de pago local PSE (Colombia) vía Local Payment Methods.

## ADDED Requirements

### Requirement: Catálogo de planes

El backend expone `GET /v1/billing/plans` con el catálogo vigente sincronizado desde Stripe. Cada plan incluye `plan_id`, `name`, `tier` (job_seeker_monthly | recruiter_starter | recruiter_business | recruiter_agency), `price_cents`, `currency`, `interval`, `features[]`, `limits[]`.

#### Scenario: Plan job_seeker mensual

- GIVEN el catálogo activo
- WHEN el cliente envía `GET /v1/billing/plans?tier=job_seeker_monthly`
- THEN el sistema responde 200 con un plan cuyo `price_cents`, `currency` (USD/EUR) e `interval = "month"` coinciden con la configuración vigente

#### Scenario: Plan recruiter Starter

- GIVEN el catálogo activo
- WHEN el cliente envía `GET /v1/billing/plans?tier=recruiter_starter`
- THEN el sistema responde 200 con `limits.matches_per_month = 50`

#### Scenario: Plan recruiter Agency

- GIVEN el catálogo activo
- WHEN el cliente envía `GET /v1/billing/plans?tier=recruiter_agency`
- THEN el sistema responde 200 con `limits.matches_per_month = null` (ilimitado)

### Requirement: Creación de Checkout Session

`POST /v1/billing/checkout` crea una Stripe Checkout Session y devuelve la URL de redirección. Soporta métodos de pago globales (tarjeta) y método local PSE (Colombia).

#### Scenario: Checkout con tarjeta (job_seeker)

- GIVEN un usuario `job_seeker` autenticado sin suscripción activa
- WHEN envía `POST /v1/billing/checkout` con `{"plan_id": "job_seeker_monthly", "payment_method": "card"}`
- THEN el sistema crea la Checkout Session con `payment_method_types = ["card"]`, `customer_email = users.email`, `metadata.user_id`, `metadata.plan_id`
- AND responde 200 con `{"checkout_url": "..."}`

#### Scenario: Checkout con PSE (recruiter CO)

- GIVEN un usuario `recruiter` autenticado con `locale = "es-CO"`
- WHEN envía `POST /v1/billing/checkout` con `{"plan_id": "recruiter_business", "payment_method": "pse"}`
- THEN el sistema crea la Checkout Session con `payment_method_types = ["pse"]`, `payment_method_options.pse.country = "CO"`
- AND responde 200 con `{"checkout_url": "..."}`

#### Scenario: Idempotencia de checkout

- GIVEN una `Idempotency-Key` ya usada con el mismo payload
- WHEN el cliente reintenta la petición
- THEN el sistema devuelve la misma `checkout_url` sin crear una nueva sesión en Stripe

### Requirement: Webhooks firmados e idempotentes

**`POST /api/v1/webhooks/stripe`** recibe eventos de Stripe. El backend debe (a) verificar la firma con `STRIPE_WEBHOOK_SECRET`, (b) deduplicar por `event.id` en `stripe_webhook_events` y (c) procesar el evento de forma transaccional.

**Reconciled**: El endpoint implementado es `POST /api/v1/webhooks/stripe` (raw-body signature verification, idempotent por event_id), no `/v1/billing/webhook` como se pensó en diseño.

#### Scenario: Verificación de firma

- GIVEN un payload firmado con un secreto incorrecto
- WHEN llega a `POST /api/v1/webhooks/stripe`
- THEN el sistema responde 400 sin tocar la base de datos

#### Scenario: Evento duplicado

- GIVEN un `event.id` ya procesado y persistido en `stripe_webhook_events`
- WHEN Stripe reenvía el mismo evento
- THEN el sistema responde 200 sin aplicar el cambio dos veces
- Y registra `webhook_dedup` en logs

#### Scenario: Evento `checkout.session.completed`

- GIVEN un evento `checkout.session.completed` válido
- WHEN el webhook se procesa
- THEN el sistema crea o actualiza la fila en `subscriptions` con `status = "active"`, `stripe_customer_id`, `stripe_subscription_id`, `plan_id`, `current_period_end`, `user_id` (desde metadata)

#### Scenario: Evento `customer.subscription.deleted`

- GIVEN un evento de cancelación
- WHEN el webhook se procesa
- THEN el sistema marca `subscriptions.status = "canceled"` y libera los límites del plan

#### Scenario: Evento `invoice.payment_failed`

- GIVEN un fallo de pago
- WHEN el webhook se procesa
- THEN el sistema marca la suscripción en estado `past_due`
- Y registra una notificación para el usuario

### Requirement: Suscripción activa y límites

`GET /v1/billing/subscription` devuelve el estado de la suscripción del usuario autenticado y sus límites efectivos.

#### Scenario: Usuario con plan activo

- GIVEN un `job_seeker` con suscripción `active`
- WHEN envía `GET /v1/billing/subscription`
- THEN el sistema responde 200 con `plan_id`, `status = "active"`, `current_period_end`, `limits`, `usage.matches_this_month`

#### Scenario: Usuario free (job_seeker)

- GIVEN un `job_seeker` sin suscripción
- WHEN envía `GET /v1/billing/subscription`
- THEN el sistema responde 200 con `plan_id = "free"`, `status = "active"`, `limits.matches_per_month = 3`

#### Scenario: Reclutador Starter agotado

- GIVEN un `recruiter` con plan `recruiter_starter` y `usage.matches_this_month = 50`
- WHEN envía `GET /v1/billing/subscription`
- THEN el sistema responde 200 con `limits.matches_per_month = 50`, `usage.matches_this_month = 50`, `overage = 0`
- Y cuando intenta un nuevo match, recibe 402 con código `PLAN_LIMIT_REACHED`

### Requirement: Cancelación desde el portal

`POST /v1/billing/portal` crea una sesión del Customer Portal de Stripe y devuelve la URL. El cliente usa el portal para cancelar o cambiar tarjeta.

#### Scenario: Portal session exitoso

- GIVEN un usuario con `stripe_customer_id`
- WHEN envía `POST /v1/billing/portal`
- THEN el sistema responde 200 con `{"portal_url": "..."}`

#### Scenario: Usuario sin customer

- GIVEN un usuario sin `stripe_customer_id` (nunca pagó)
- WHEN envía `POST /v1/billing/portal`
- THEN el sistema responde 400 con código `NO_CUSTOMER`

### Requirement: Conteo de uso mensual

`usage.matches_this_month` se incrementa en cada match exitoso (`POST /v1/match` o equivalente de roster) asociado al usuario. El contador se reinicia cuando `current_period_end` expira y se confirma la renovación.

#### Scenario: Incremento tras match

- GIVEN un `job_seeker` con `usage.matches_this_month = 2` y plan free (`limit = 3`)
- WHEN completa un match exitoso
- THEN `usage.matches_this_month = 3`

#### Scenario: Reset mensual

- GIVEN la suscripción se renovó (nuevo `current_period_start`)
- WHEN el primer match del nuevo período se ejecuta
- THEN el contador se reinicia a `1`

### Requirement: Monedas y payouts soportados

El sistema opera con `USD` y `EUR` como currencies de precio y payout. Los precios en CO se pagan en USD/EUR; PSE es el método local de transferencia bancaria.

#### Scenario: Pago PSE en USD

- GIVEN un `recruiter` CO con checkout PSE
- WHEN completa el pago
- THEN el evento de Stripe reporta `currency = "USD"` y `payment_method = "pse"`
- Y el payout al merchant se programa en USD
