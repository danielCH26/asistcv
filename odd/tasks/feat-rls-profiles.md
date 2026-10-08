# Feature: rls-profiles (#95, follow-up de #87)

> **Issue**: #95 (el item 2 de los tres follow-ups), cierra la deuda "profiles sin RLS" del audit (A7/comentario de 011).
> **Branch**: `feat/rls-profiles`
> **Scope**: Migración que habilita ROW LEVEL SECURITY sobre `profiles` con el patrón exacto de la migración 011 (service_all + owner CRUD via `app_current_user_id()`), seed fijado a contexto de servicio, comentarios/documentación actualizados. El filtro app-level queda como defense-in-depth.

---

## Specs

### S1 — RLS sobre `profiles` con el patrón de la 011

Migración `023_enable_rls_profiles`:
- `ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY` + `FORCE` (downgrade: inverso).
- Policies (mismo naming que 011):
  - `profiles_service_all FOR ALL USING (current_setting('app.current_user_id', true) = '0')` — el carve-out documentado del service principal (MCP adapter, open mode) se conserva a nivel DB.
  - `profiles_owner_select/insert/update/delete` vía `owner_user_id = public.app_current_user_id()` (la función de la 011 sigue en la DB).
- Precondición cumplida: la 011 difirió profiles porque el create path no estampaba owner — #85 ya estampa `owner_user_id` + FK en create (profiles.py:194) y exige JWT real.

### S2 — El app-level filter queda como defense-in-depth

Los filtros `owner_user_id == user.id` en `profiles.py` y `match.py` NO se tocan (con RLS + FORCE son redundantes pero documentan intención a nivel lectura y protegen el caso superuser). Los comentarios que dicen "profiles no tiene RLS" se actualizan (match.py:118-125, profiles.py:113-117, `docs/security/service-principal.md`).

### S3 — Seed fijado a contexto de servicio

`app/db/seed.py` no bindea GUC — con FORCE RLS el insert sería denegado. Agregar `set_rls_service(session)` antes de insertar (mismo patrón que `internal/adaptations.py:97`).

### S4 — Tests RLS para profiles (RED primero)

En `tests/test_rls.py`, espejando `test_user_cannot_select_other_users_analyses`:
- user A no puede SELECT del profile de user B (0 filas)
- service (GUC '0') lee across users
- sin GUC: 0 filas + INSERT denegado (default deny con FORCE)
- owner puede update/delete sus propias filas
Además: `"profiles"` se agrega a `_PROTECTED_TABLES` (test no-GUC).

---

## Tasks

| ID | Title | Commit |
|---|---|---|
| T1 | RED: tests RLS de profiles (cross-user leak hoy) → GREEN: migración `023_enable_rls_profiles` | `fix(db): enable RLS on profiles with service carve-out (S1+S4 of #95)` |
| T2 | Seed a servicio + comentarios actualizados (match, profiles, docs) | `fix(db): seed under service context; update stale no-RLS comments` |
| T3 | QA (suite completa) + PR + cierre | `test(db): full QA pass, closes #95 item RLS` |

---

## Log

### L1 — User's verbatim request (2026-10-07)

> "sigamos"

(Ruta declarada: QA hover visual ✅ → #95 RLS profiles — el único follow-up de #87 100% desbloqueado y autocontenido.)

### L2 — Mapping previo

- 011 difirió profiles explícitamente: *"Deferred until profile CRUD becomes user-bound"* — #85 cumplió la precondición (owner stamp + FK + JWT requerido en create).
- `get_db`/`get_db_optional` ya bindean el GUC por principal (deps.py:305-331) → RLS funciona out-of-the-box para todos los endpoints de profiles.
- match.py:127-131 ya bindea + filtra (el comentario del gap se actualiza en T2).
- Lectores de `Profile`: profiles.py (owner/service), match.py (owner/service), seed.py (dev — sin GUC, se arregla en T2). Recruiter NO lee `profiles` (usa recruiter_candidates/análisis propios).
- Head de migraciones: `022_cv_adaptations_cv_ver` → nueva revisión `023_enable_rls_profiles`.
- conftest corre `alembic upgrade head` en la DB de test + listener global bindea servicio '0' → fixtures siguen funcionando.
- Legacy rows con `owner_user_id` NULL: quedan visibles solo para el servicio (deny por defecto para owners) — mismo comportamiento que el filtro app-level post-#85.

### L3 — Evidence / commits (appended as work progresses)

<<<<<<< HEAD
- TBD per task.
=======
**T1 (S1, S4 — migración + tests RLS) — DONE**
- RED: 4 tests fallaron contra el estado sin RLS (leak cross-user SELECT, INSERT/UPDATE sin bloqueo, no-GUC sin deny).
- GREEN: `023_enable_rls_profiles` (ENABLE+FORCE + service_all + owner CRUD — patrón exacto de 011, reutiliza `app_current_user_id()`). Downgrade limpio.
- Aprendizaje del test: cross-user UPDATE bajo RLS **no lanza** — afecta 0 filas (stealth semantics de Postgres); la aserción correcta es rowcount==0 + read-back vía servicio. El test positive-control existente no lee cross-conexión porque `conn_as` hace rollback al salir.
- 24/24 en test_rls.py.

**T2 (S2, S3 — seed + comentarios) — DONE**
- `seed.py` bindea `set_rls_service` (sin GUC, FORCE RLS denegaría el insert; mismo patrón que internal/adaptations).
- Comentarios stale actualizados: match.py (RLS ahora protege; app filter = defense-in-depth), profiles.py docstring (doble capa), `docs/security/service-principal.md` (item RLS marcado DONE).
- QA: **160/160** (rls + ownership + persistence + analyses + recruiter + security + adaptation + billing + migrations) · ruff ✅ · mypy ✅.
>>>>>>> 1c378b2446f29f2111399b08c227611244fa215f
