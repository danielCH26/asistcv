# Feature: api-key-shared-read-audit (#87)

> **Issue**: #87 (P2 security finding, board cleanup residual)
> **Branch**: `fix/api-key-shared-read-audit`
> **Scope**: Document the service-principal contract, add structured audit log on every service-principal read of `/profiles`, add the "open mode" test the issue requests. The deeper fixes (per-client service principal, RLS for service) stay as documented follow-ups.

---

## Specs

### S1 — Document the service-principal contract

A new file `docs/security/service-principal.md` that names:
- The principal id (0), the auth_method (`api_key` and the `optional_auth` open-mode auto-fabrication).
- The exact surface that the principal can read across `profiles`, `analyses`, `job_descriptions`, `users_cvs` (the issue names them).
- The data fields exposed per profile (incl. **rango salarial** via `Profile.preferences`).
- A pointer to the docstring at `profiles.py:113-115` that already documents the per-endpoint exception.
- A "what we are NOT doing yet" section listing the deeper fixes (per-client principal, RLS, secret rotation) with a link to the follow-up issue.

Also update the `profiles.py:113-115` docstring to link to the new file.

### S2 — Structured log on every service-principal profile read

In `backend/app/api/v1/profiles.py::_get_profile_or_404`, when `user.id == 0` (the bypass path) and the profile IS found, log a `service_principal_profile_read` event with:
- `profile_id` (read)
- `auth_method` (should be `api_key`; if `optional_auth` fabricated 0 in open mode, log `auth_method=open` so it's distinguishable in the audit stream)
- `request_id` (if available from `request.state`)

This makes the API-key read **auditable** without changing the read surface — the deepest single change that addresses the issue's *"sin auditoría de qué leyó"* line directly.

The same pattern exists in `analyses`, `job_descriptions`, `users_cvs` endpoints per the issue; replicating the log in each of those endpoints is out of scope here (out-of-scope is documented as a follow-up).

### S3 — Test the open-mode auto-fabrication behavior

The issue notes: *"El filtro de ownership no protege nada en modo abierto (sin BACKEND_API_KEY): `optional_auth` fabrica el usuario de servicio 0 y el filtro queda inerte por construcción. Ese modo es de desarrollo, pero conviene que quede un test que documente la diferencia."*

A new test in `backend/tests/test_profile_ownership.py`:
- With `BACKEND_API_KEY` unset (or stubbed), an unauthenticated request to `GET /v1/profiles/<random_id>` returns 200 with the profile (the inerte filter documents the dev-mode behavior).
- Verifies the log line fired with `auth_method=open`.

### S4 — Out-of-scope follow-ups (issue #)

The feature doc records a new issue (or updates an existing one if Daniel prefers) that lists the three "dirección de arranque" the body names but we are NOT doing in v1.0:
- Per-client service principal (replaces the global key).
- RLS policy for service principal on `profiles` (moves the exception from app code into DB).
- Secret rotation moved to a managed secret (the audit already has this follow-up for BACKEND_API_KEY generally).

---

## Tasks

| ID | Title | Commit |
|---|---|---|
| T1 | RED test (service-principal read emits structured log) → GREEN: log in `_get_profile_or_404` | `fix(profile): log service-principal profile reads (S2 of #87)` |
| T2 | RED open-mode test → GREEN | `test(profile): document open-mode service-principal auto-fabrication` |
| T3 | docs/security/service-principal.md + profiles.py docstring link | `docs(security): service-principal contract for API-key reads` |
| T4 | Follow-up issue + QA + close #87 | `docs(audit): #87 follow-ups + close` |

---

## Log

### L1 — User's verbatim request (2026-10-07)

> "si, ataca la 87 y tambien sigamos con la 57"

The "ataca" = attack / tackle with a fix, not just a closure-by-documentation. (1) doc + (2) audit log is the meaningful v1.0-scoped deliverable.

### L2 — Pre-fix mapping (2026-10-07)

- `backend/app/api/v1/profiles.py:108-128` `_get_profile_or_404`: the bypass at L117-119 (`if user.id != 0`).
- `backend/app/api/deps.py:113`: API key user has `auth_method="api_key"`.
- `backend/app/api/deps.py:179-225` `optional_auth`: in open mode (no `BACKEND_API_KEY`) fabricates the service user.
- `backend/tests/test_profile_ownership.py::test_service_principal_can_still_read_profiles` pins the bypass — we MUST keep it green.
- `mcp-adapter/src/asistcv_mcp/server.py` (per issue) hardcodes `profile_id=1` and uses the shared key — the mcp-adapter use is single-user but the credential is not.

### L3 — Evidence / commits (appended as work progresses)

- TBD per task.