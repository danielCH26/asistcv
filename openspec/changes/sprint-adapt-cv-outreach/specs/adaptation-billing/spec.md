# Spec: adaptation-billing

## Purpose

Enforcement de los límites mensuales de adaptaciones por plan. El
recurso `adaptations_per_month` se suma al catálogo existente de
`PLAN_LIMITS` (junto a `matches_per_month`). El contador se persiste
en `usage_counters` (tabla introducida en Sprint 2 para `matches`)
y se reinicia al renovarse la suscripción. La capa de billing NO
duplica la lógica de enforcement: consume el helper `check_limit` /
`increment_usage` ya validado por el flujo de `match`.

## ADDED Requirements

### Requirement: Recurso `adaptations_per_month` por tier

`PLAN_LIMITS` expone `adaptations_per_month` para cada plan vigente.
La tabla de valores es:

| Tier | `adaptations_per_month` |
|---|---|
| `free` | `0` |
| `seeker_monthly` (job_seeker_monthly) | `5` |
| `recruiter_starter` | `10` |
| `recruiter_business` | `20` |
| `recruiter_agency` | `null` (ilimitado) |

#### Scenario: Plan free sin adaptaciones

- GIVEN un usuario `job_seeker` con plan `free` y
  `usage.adaptations_this_month = 0`
- WHEN el cliente envía `GET /v1/billing/subscription`
- THEN el sistema responde 200 con
  `limits.adaptations_per_month = 0`
- AND `usage.adaptations_this_month = 0`

#### Scenario: Plan seeker_monthly

- GIVEN un usuario `job_seeker` con plan `seeker_monthly` activo
- WHEN el cliente envía `GET /v1/billing/subscription`
- THEN el sistema responde 200 con
  `limits.adaptations_per_month = 5`

#### Scenario: Plan recruiter_business

- GIVEN un usuario `recruiter` con plan `recruiter_business`
- WHEN el cliente envía `GET /v1/billing/subscription`
- THEN el sistema responde 200 con
  `limits.adaptations_per_month = 20`

#### Scenario: Plan recruiter_agency ilimitado

- GIVEN un usuario `recruiter` con plan `recruiter_agency`
- WHEN el cliente envía `GET /v1/billing/subscription`
- THEN el sistema responde 200 con
  `limits.adaptations_per_month = null`

### Requirement: Enforcement 402 PLAN_LIMIT_REACHED

Cuando el contador `usage.adaptations_this_month` alcanza el límite
del plan activo, `POST /v1/adaptations` responde 402 con código
`PLAN_LIMIT_REACHED`. El cuerpo incluye contexto útil para el upsell
(sin filtrar datos privados).

#### Scenario: sexta adaptación en plan seeker_monthly

- GIVEN un `job_seeker` con plan `seeker_monthly`
  (`limit = 5`) y `usage.adaptations_this_month = 5`
- WHEN envía `POST /v1/adaptations` con un JD válido
- THEN el sistema responde 402 con
  `{code: "PLAN_LIMIT_REACHED", current_tier: "seeker_monthly", limit: 5, upgrade_url: "..."}`
- AND no persiste fila en `cv_adaptations` (no consume el slot)
- AND no incrementa el contador

#### Scenario: recruiter_agency no topa límite

- GIVEN un `recruiter` con plan `recruiter_agency`
  (`limit = null`)
- AND `usage.adaptations_this_month = 1000`
- WHEN envía `POST /v1/adaptations`
- THEN el sistema responde 202 (sin tope) y crea la fila normalmente

#### Scenario: free no puede adaptar

- GIVEN un usuario `job_seeker` con plan `free`
- WHEN envía `POST /v1/adaptations`
- THEN el sistema responde 402 con
  `{code: "PLAN_LIMIT_REACHED", current_tier: "free", limit: 0, upgrade_url: "..."}`

### Requirement: Conteo vía usage_counters (Sprint 2)

El contador `adaptations_this_month` se persiste en `usage_counters`
(la misma tabla que ya cuenta `matches_this_month`). El helper
`check_limit`/`increment_usage` de Sprint 2 se reutiliza sin duplicar
la lógica de enforcement.

#### Scenario: Incremento tras adaptación completada

- GIVEN un `job_seeker` con plan `seeker_monthly`
  (`limit = 5`) y `usage.adaptations_this_month = 2`
- WHEN completa una adaptación (job llega a `status = "completed"`)
- THEN `usage.adaptations_this_month = 3`

#### Scenario: Adaptación fallida NO incrementa

- GIVEN un usuario con `usage.adaptations_this_month = 3`
- WHEN una adaptación termina en `status = "failed"`
  (cualquier `error_code`)
- THEN el contador permanece en `3` (no se cobra el slot)

#### Scenario: Adaptación cacheada NO incrementa

- GIVEN un usuario con `usage.adaptations_this_month = 4`
- WHEN un `POST /v1/adaptations` produce cache hit y reutiliza una
  fila existente
- THEN el contador permanece en `4` (cache hit no cobra slot)

### Requirement: Reset mensual al renovar suscripción

El contador `adaptations_this_month` se reinicia junto con
`matches_this_month` cuando la suscripción se renueva
(`current_period_start` nuevo). La mecánica es la misma que Sprint 2
definió para matches.

#### Scenario: Reset al renovar plan seeker_monthly

- GIVEN un `job_seeker` con `usage.adaptations_this_month = 5`
  en el período que vence
- WHEN la suscripción se renueva (nuevo `current_period_start`)
- AND se ejecuta la primera adaptación del nuevo período
- THEN el contador se reinicia a `1`

#### Scenario: Reset al renovar plan recruiter_business

- GIVEN un `recruiter` con `usage.adaptations_this_month = 20`
  al cierre del período
- WHEN la suscripción se renueva
- THEN el siguiente job de adaptación parte el contador en `0`

### Requirement: Coexistencia con `matches_per_month`

`matches_per_month` y `adaptations_per_month` son contadores
independientes en `usage_counters`. Consumir uno no descuenta el
otro. Esto refleja la separación de producto: un match analiza un JD;
una adaptación genera un CV adaptado.

#### Scenario: Contadores independientes

- GIVEN un `job_seeker` con plan `seeker_monthly`
  (`matches_per_month = 30`, `adaptations_per_month = 5`)
- AND `usage.matches_this_month = 10`,
  `usage.adaptations_this_month = 5`
- WHEN envía `POST /v1/match`
- THEN el sistema responde 200 y
  `usage.matches_this_month = 11`,
  `usage.adaptations_this_month = 5` (sin cambio)

#### Scenario: Adaptación no permitida pero match sí

- GIVEN un `job_seeker` con plan `seeker_monthly`
  y `usage.adaptations_this_month = 5`,
  `usage.matches_this_month = 2`
- WHEN envía `POST /v1/adaptations`
- THEN el sistema responde 402 (`adaptations_per_month` agotado)
- AND si luego envía `POST /v1/match`, responde 200 (otro recurso)