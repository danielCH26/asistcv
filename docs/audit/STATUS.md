# Estado de remediación — 2026-10-04

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

## ⚠️ Todo esto está en `main`; deploy reportado por el maintainer

Render no auto-deploya. Los tres pasos manuales, en orden:

> Reportados como ejecutados el 2026-10-04. **Sin verificación propia** — la
> confirmación pendiente es que un usuario real pueda subir un CV y hacer un
> audit anónimo sin 500. Ese es el mismo bug que acabamos de corregir localmente,
> así que si el deploy ocurrió *antes* de esos commits, sigue desplegado.

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

## Red de seguridad (#50) — cerrada

CI corre `npm run test` (48 tests) y `npm run check` en el job
`frontend-i18n-parity`, y los cuatro workflows declaran `permissions:`
(`contents: read` en `ci.yml`, `{}` en los tres sweepers).

El path RLS per-user ya no queda enmascarado. `tests/conftest_rls.py` abre
un **lane** que quita el listener de servicio y fuerza el rol no-superuser
sobre el engine real de la app, con un guard que **falla cerrado** si no
puede probar que el lane es fiel.

**Hallazgo de esta sesión:** el rol por defecto del entorno de test
(`asistcv`) es **superuser con `BYPASSRLS`**, así que RLS no se aplicaba
nunca — el GUC era irrelevante. Sin corregir eso, ningún test podía detectar
un bug de RLS aunque el listener de servicio estuviera quieto. Esta era la
segunda máscara, más profunda que la que el issue reportaba.

## `refresh()` post-commit mataba 10 endpoints (500 en producción)

`SET LOCAL` muere en el `COMMIT`. `get_db` bindea el GUC una vez por
request; los handlers que commitean y después releen la misma tabla
protegida abrían una transacción **sin contexto**, RLS denegaba, el SELECT
devolvía 0 filas y `Session.refresh()` lanzaba `InvalidRequestError` → **500**.

**10 sitios eliminados** en `cvs.py`, `adaptations.py`,
`recruiter_candidates.py`, `recruiter_consent.py` y `audit.py`. Eran
redundantes con `expire_on_commit=False`, y ninguna de esas tablas tiene
trigger (el único del repo es `trg_audit_log_immutable` sobre
`recruiter_audit_log`).

Entre los afectados estaba **`POST /v1/audit/anonymous`**, la entrada
pública del producto.

**Las escrituras persistían antes del 500**, así que un cliente que
reintentaba duplicaba el registro.

Cubierto por 17 tests en `tests/test_rls_commit_boundary.py`, más un guard
que escanea el código fuente y falla si alguien reintroduce un `refresh()`
post-commit sobre tabla RLS.

**El fix estructural sigue diferido**: re-bindeo del GUC tras cada commit
vía `ContextVar` + listener `after_begin` en código de producción. El guard
bloquea la variante `refresh()`, no la clase general.

---

## Seguridad

Revocar la API key de Neon que se pegó en texto plano en una conversación
de trabajo: **Console → ícono de cuenta → Account Settings → API Keys**.
Fue la credencial de administración del proyecto entero.

---

## Flujo de recruiter roto end-to-end (3 familias, abierto)

Ninguno de los tres es RLS. Salieron al poder finalmente ejercitar el flujo.

| Endpoint | Qué pasa | Estado |
|---|---|---|
| `POST /v1/recruiter/candidates` | **422 en las 8 formas de request.** Declara `body: CandidateCreate` junto a `file: UploadFile = File(None)`, y FastAPI 0.141.1 exige un campo multipart llamado literalmente `body`. El cliente real (`client.ts:302-310`) manda campos planos: **el frontend no puede crear un candidato** | Abierto |
| `POST /v1/recruiter/candidates/{id}/match` | Era 500. **Corregido:** `MatchAnalysis` emite `list[str]` y `CandidateMatchResponse` declaraba `dict`; las anotaciones mentían | **Cerrado** |
| `POST /v1/recruiter/consent` | 422 para un cliente real. `recruiter_consent.py:42` declara `current_user: CurrentUser` **sin `Depends(get_current_user)`**, así que FastAPI lo toma como campo de body — y el handler saca la identidad de un **campo controlado por el cliente** mientras `get_db` bindea el GUC desde el JWT | Abierto, **seguridad** |

Como el alta de candidato no funciona, un recruiter no puede adjuntar un CV
ni llegar al match. El flujo completo está verificado solo en su tramo 404.

Bug hermano del que sí arreglamos, sin corregir a propósito:
`Analysis.strengths`/`gaps` (`models.py:130-135`) también dicen `dict | None`
guardando listas. No da 500 porque `analyses.py:149-150` aplica un shim
`_as_str_list()` — un parche que además **se traga silenciosamente** cualquier
valor malformado devolviendo `[]`.

## Otros pendientes

| | |
|---|---|
| Base `asistcv_test` en el branch de Neon | Los tests siguen usando el contenedor de Docker |
| 3 strings en "usted" mezclados con voseo | Decisión de producto, 3 líneas |
| Atajo de variables | Migrar las líneas exportadas de los `.env.example` a un gestor de secretos |
| Resend sin dependencia nueva | `email_service.py` usa `httpx` directo; funciona, pero sin reintentos ni tests contra la API real |
| `test_cv_storage.py::test_store_creates_user_directory` | Assert de separadores POSIX, falla en Windows. Preexistente, ajeno a este trabajo |

Detalle de hallazgos: `docs/audit/00-hallazgos.md`
Catálogo completo: `docs/audit/90-catalogo-completo.md`
Plan original: `docs/audit/PLAN.md`
