# Proposal: Sprint 2 — Cuentas de usuario, CV y Billing (Slice 2)

## Intent

Convertir AsistCV en producto multi-usuario: cuentas (`job_seeker` + `recruiter`), JWT coexistiendo con la API key del MCP, gestión de CV (PDF + editor estructurado), auditoría anónima gratuita como funnel y billing Stripe (PSE CO + tarjetas). Base: Sprint 1 archivado (117 tests, i18n es/en, MCP en producción).

## Scope

### In Scope

- Auth: tabla `users` con `role`; bcrypt + JWT (access 15 min, refresh 30 d); dual auth con API key preservada (MCP sin regresión)
- CV: `user_cvs`; upload PDF ≤10MB (pypdf) + editor estructurado; aislamiento STRICT vía RLS
- Recruiter: `recruiter_candidates` (candidatos externos); declaración buena fe + ToS; ranking híbrido score×recency
- Free audit: anónima → auditoría → email opcional; rate limit 3/IP/día
- Billing Stripe: job_seeker freemium + mensual; reclutador por volumen; webhooks firmados + idempotentes; PSE CO
- Frontend: 6+ rutas nuevas + onboarding 3 pasos; historial user-bound
- Deps: `pypdf`, `passlib[bcrypt]`, `PyJWT`, `stripe`, `python-multipart`

### Out of Scope

Adaptar CV/outreach/research y tracking (Sprint 3+); OAuth social; multi-seat; retiro de API key; revisión legal formal del ToS.

## Capabilities

**New:** `user-auth` (roles, JWT, dual auth) · `cv-management` (PDF, editor, aislamiento) · `recruiter-roster` (externos, ToS, ranking) · `free-audit` (funnel, rate limit) · `billing` (planes, checkout, webhooks) · `account-ui` (rutas, onboarding).

**Modified:** `match-analysis` — auth API key → dual; historial user-bound. `match-ui` — sesión JWT reemplaza API key build-time.

## Approach

1. Migración aditiva (`users`, `user_cvs`, `recruiter_candidates`, `subscriptions`); validar en Neon branch.
2. Dependencia FastAPI dual: JWT usuarios, API key servicio/MCP.
3. Aislamiento: RLS capa primaria + checks en servicio.
4. Stripe Checkout + webhooks (firma, idempotencia); PSE vía Local Payment Methods.
5. Frontend sobre patrones existentes (i18n, adapter-static).

## Affected Areas

| Área | Impacto |
|---|---|
| `backend/app/core/config.py`, `app/api/deps.py` | Mod — dual auth, settings |
| `backend/app/db/models.py`, `backend/alembic/` | New — 4 tablas |
| `backend/app/api/v1/`, `app/services/` | New — 5 módulos |
| `backend/pyproject.toml` | Mod — 5 deps |
| `frontend/src/routes/` | New — 6+ rutas |
| `mcp-adapter/` | Sin cambios |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| ~2150 l / ~7 PRs vs single-pr/600 | Alta | Ver Rollout |
| Dual auth rompa MCP | Media | Tests paridad; API key queda |
| pypdf OOM (Render 512MB) | Media | Streaming; fallback pdfminer.six |
| Webhooks duplicados | Media | Firma + idempotencia |
| RLS filtra CVs (STRICT) | Alta | Tests cross-user/role |
| ToS sin texto final | Media | Draft; legal diferida |

## Rollout — tensión de tamaño

Forecast exploración: **~2150 líneas / ~7 PRs** (auth ~300, CV ~350, roster ~200, Stripe ~300, audit ~250, UI ~400, UI recruiter/billing ~350). **Incompatible con single-pr/600**: `sdd-tasks` debe resolver `size:exception` o recomendar Feature Branch Chain. Auth bloquea todo; audit es independiente.

## Rollback Plan

Revert por PR; migraciones aditivas con `downgrade` en Neon; dual auth permite volver a API-key-only; Stripe en modo test hasta validar webhooks.

## Dependencies

Deps Python (In Scope); cuenta Stripe con PSE CO; draft ToS reclutador.

## Success Criteria

- [ ] Registro/login ambos roles (15 min / 30 d)
- [ ] MCP operativo con API key (tests paridad)
- [ ] PDF ≤10MB → perfil editable
- [ ] Aislamiento cross-user/role → 403/404
- [ ] Auditoría anónima e2e (3/IP/día)
- [ ] Checkout tarjeta + PSE sandbox por plan; webhooks idempotentes
- [ ] Onboarding 3 pasos + historial user-bound; CI verde

## Open Questions (validar en design)

1. RLS: `SET app.current_user` vs. policies + dependencia.
2. Retención free 30 días: ¿cron?
3. ¿Vincular email de audit a cuenta posterior?
4. Tiers/precios reclutador; verificación de email: ¿cuándo?
