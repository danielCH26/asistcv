# Feature: Polish UX (#37)

## Specs

> **S1**: Reescribir todos los mensajes de error de la UI para humanos (no stacktraces)

> **S2**: Mensajes de error del backend sanitizados (no exponer internals al usuario)

> **S3**: Rate limiting en endpoints públicos (ej: 100 requests/minuto por IP)

> **S4**: Manejo elegante de edge cases:
> - JD vacío en match
> - Empresa no encontrada en research
> - Sin perfil cargado

> **S5**: Logging estructurado en producción (ya está, verificar que funcione)

> **S6**: Página de error amigable en el frontend (404, 500)

## Hallazgos del explorer

### Lo que YA está bien
- ~80 mensajes de error en i18n (ES + EN) — bien cubiertos
- Backend: ~60 HTTPExceptions con códigos específicos — bien estructurados
- Logging: structlog + JSON + stdout — ya estructurado ✅ (S5 OK)
- Edge cases: JD vacío, sin perfil — ya manejados ✅ (S4 OK)
- billing: mapeo manual de 403→emailRequired y 400→noCustomer en +page.svelte ✅

### Lo que necesita arreglarse

#### 🔴 CRÍTICO — Rate limiting con bugs de seguridad (S3)
- `A9` (P1): Rate limit de audit usa `X-Forwarded-For` (spoofeable por cliente)
- `A12` (P1): Race condition — requests concurrentes exceden 3 auditorías/día
- `A11` (P2): `Retry-After` siempre ≈ 0 (aritmética incorrecta)
- `A3` (P1): `auth_login_attempts` sin índice en `(email, attempted_at)`
- `A4` (P1): Rate limit de login no tiene dimensión de IP

#### 🟡 MEDIO — Sanitización de errores (S2)
- `billing.py:225`: `str(e)` expone mensajes internos de Stripe
- `billing.py:190,194`: Códigos `"Invalid plan_id"`, `"Invalid payment_method"` son técnicos
- `match.py:108,110,224,226`: `str(exc)` expone excepciones internas

#### 🟡 MEDIO — Páginas de error globales (S6)
- No existe `+error.svelte` dedicado en el frontend
- Solo manejo inline de errores por página

## Tasks

### T1: Bug fixes de rate limiting (S3 — crítico) ✅
- **Commit**: `a930418`
- A9: CF-Connecting-IP > X-Forwarded-For > request.client.host
- A12: SELECT FOR UPDATE SKIP LOCKED serializa concurrentes
- A11: Retry-After calculado desde oldest audit.expires_at
- A3: Migration 024 — índices en (email, attempted_at) y (ip, attempted_at)
- A4: Rate limit login ahora bloquea por email AND IP

### T2: Sanitizar HTTPException.details del backend (S2) ✅
- **Commit**: `e03eda5`
- billing.py: ValueError → "BILLING_ERROR"
- match.py: str(exc) → "EMBEDDING_ERROR" / "LLM_ERROR"
- toApiError: extrae detail.message de respuestas estructuradas

### T3: Página de error global del frontend (S6) ✅
- **Commit**: `6012451`
- `+error.svelte` global: detecta 404/500/otro, muestra mensaje + botón home

### T4: Mejorar mapeo de errores en client.ts (S1) ✅
- **Commit**: `aaea8a9`
- humanizeStatus: 20+ códigos mapeados a mensajes ES
- toApiError: pasa detail.message a humanizeStatus

### T5: Verificar logging estructurado en prod (S5) ✅ DONE
- Ya estaba: structlog + JSON + stdout. Sin cambios necesarios.

## Log

- L1: "Polish UX: mensajes de error, rate limiting, logging" — issue #37
