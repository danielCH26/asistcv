# Estado de remediación — 2026-10-03

Todos los hallazgos de Fase 0, 1 y 2 están **mergeados en `main`**.
Cero PRs abiertos.

---

## Cerrado y verificado

| ID | Qué era | PR | Verificación |
|---|---|---|---|
| **S1** | `jwt_secret` con default público, explotado en prod | rotado + #53 | 401 con el secret viejo |
| **S3** | IDOR cross-user en `claim_audit` | #52 | 401 sin credencial |
| **S4** | Router duplicado + kill-switch parcial | #52, #62 | 404 en la raíz, 503 en lecturas |
| **Sesiones** | TTL deslizante, nunca expiraban | #69 | 30 días absolutos |
| **#46** | Billing 500, verificación de email stub | #72 | migration chain lineal |
| **#47** | El audit público no mandaba el CV al LLM | #73 | CV real llega al provider |
| **#48** | Cuota de adaptaciones nunca consumida | #74 | 411 tests |
| **#49** | El validador no verificaba números | #75 | sustitución rechazada, reformat permitido |
| **Guard DB** | Tests podían dropear producción | #70 | fail-closed en 4 checks |
| **Copy** | 41 strings con jerga | #71 | 0 siglas en la UI |
| **Diseño** | Tokens, contraste, clay, grilla, header | #64–#68 | 0 overflow a 80 viewports |

**Fases 0, 1 y 2 completas.**

---

## ⚠️ Todo esto está en `main` pero NO en producción

Render no auto-deploya. Los tres pasos manuales, en orden:

### 1. `RESEND_API_KEY` en Render
Sin esto el checkout sigue bloqueado en 403 aunque el código sea correcto.

### 2. Migraciones en Neon
El deploy corre solo `uvicorn`; las migraciones no se aplican solas.
Hay **tres** pendientes, y el orden importa porque cada una depende de la anterior:

```powershell
cd C:\Users\danie\Downloads\asistcv\asistcv\backend
$env:DATABASE_URL = "postgresql+asyncpg://<user>:<pass>@<host>/neondb?sslmode=require"
uv run alembic current
uv run alembic upgrade head
uv run alembic current    # debe mostrar 021_cv_adaptations_pending_uq
```

| Migración | Qué hace | Por qué antes del deploy |
|---|---|---|
| `020_email_verification_tokens` | Tabla de tokens de verificación | Sin ella, `verify-email/confirm` falla |
| `021_cv_adaptations_pending_uq` | Índice único pasa de `completed` a `pending` | Sin ella, las adaptaciones pueden quedar colgadas |

Rollback si la base está vacía:
`uv run alembic downgrade 019_rename_adaptations_jd_text`

### 3. Manual Deploy en Render
Web Service → Deploys → Manual Deploy → esperar `Live`.

Cubre #69 (sesiones), #72 (billing), #73 (audit), #74 (cuota), #75 (validador).

---

## Pendiente conocido, no resuelto

**`content_version` cache invalidation es vacía.** Tras editar un CV, una
repetición dentro de la ventana de caché devuelve una adaptación generada
**del CV previo a la edición**. Probado empíricamente.

`get_cached` compara contra el valor *actual* que le pasa el endpoint, así
que nunca hay desactualización. Necesita una columna snapshot en
`cv_adaptations` más un write en el runner. **Cambio de schema, merece su
propio ticket.**

**Gaps del validador, medidos y diferidos:**
- Migración entre empleos: `source_blob` mezcla bloques.
- Alias de skills: `"R"` admite 11 de 16 skills inventables. El guard de
  una línea cerraría el hole pero rechazaría `Go` → `Golang`.
- `full_name`, `education` y `languages` no se validan.

**Sin la red de seguridad (#50):** CI no corre los tests del frontend, y
el hook global de `conftest` sigue enmascarando el path RLS per-user.

---

## Seguridad

Revocar la API key de Neon que se pegó en texto plano en una conversación
de trabajo: **Console → ícono de cuenta → Account Settings → API Keys**.
Fue la credencial de administración del proyecto entero.

---

## Otros pendientes

| | |
|---|---|
| Base `asistcv_test` en el branch de Neon | Los tests siguen usando el contenedor de Docker |
| 3 strings en "usted" mezclados con voseo | Decisión de producto, 3 líneas |
| Atajo de variables | Migrar las líneas exportadas de los `.env.example` a un gestor de secretos |
| Resend sin dependencia nueva | `email_service.py` usa `httpx` directo; funciona, pero sin reintentos ni tests contra la API real |

Detalle de hallazgos: `docs/audit/00-hallazgos.md`
Catálogo completo: `docs/audit/90-catalogo-completo.md`
Plan original: `docs/audit/PLAN.md`
