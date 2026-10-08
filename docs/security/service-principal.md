# Service-Principal Contract (Issue #87)

This document describes the **service-principal** — a special account (id `0`)
that the backend fabricates whenever a request is authenticated by the
shared `BACKEND_API_KEY`, **or** when the deployment runs in *open mode*
(no key configured) and the request is unauthenticated.

The contract is **deliberate**, not an accident. It exists because three
consumers in the product rely on the service principal to read across
all rows of certain tables: the MCP adapter (single-user, runtime local),
the `analyses` flow (audit the anonymous funnel), and the matching
plumbing in `match.py`. The audit's P0 IDOR fix (#85) tightened
**per-user** ownership on `profiles`; this carve-out is the documented
exception.

The **read surface** that the service principal can see, today:

| Table | Endpoint(s) | Field set | Includes |
|---|---|---|---|
| `profiles` | `GET /v1/profiles/{id}` | All columns of `Profile` (incl. `preferences`) | **Salary range** via `Profile.preferences.location` and the surrounding profile record |
| `analyses` | `GET /v1/me/analyses`, `GET /v1/me/analyses/{id}` | Score, strengths, gaps, energy_level, reasoning | – |
| `job_descriptions` | `GET /v1/job-descriptions/{id}` | raw_text, title, structured fields | – |
| `users_cvs` | `GET /v1/cvs/{id}` | raw_text, structured | – |

> The same carve-out (`if user.id != 0: query = query.where(...)`) appears in
> every endpoint that lists above. The `profiles` filter is the only one
> that exposes the salary range; the others are narrower fields.

## Who can become the service principal

Two ways:

1. **Protected mode** (production): anyone holding the shared
   `BACKEND_API_KEY` in the env. On the wire, they send
   `Authorization: Bearer <key>`; `deps._try_api_key` returns
   `CurrentUser(id=0, role="service", auth_method="api_key")`.
2. **Open mode** (dev only, no `BACKEND_API_KEY` set): every
   unauthenticated request is **auto-fabricated** as the service
   principal. The `auth_method` is the literal string `"open"` (not
   `"api_key"`) so the audit log can tell the two apart.

## Audit log

Every read of a profile under the service principal emits a structured
log line at `INFO` level via structlog:

```json
{
  "event": "service_principal_profile_read",
  "profile_id": 42,
  "auth_method": "api_key"
}
```

`auth_method` is either `"api_key"` (real key) or `"open"`
(open-mode auto-fabrication). The log is emitted from
`backend/app/api/v1/profiles.py::_get_profile_or_404` after the profile
has been fetched. In Render, the structlog JSON renderer emits this to
stdout, picked up by the platform's log drain.

The log is **per read**, not per service. It is the minimum honest
improvement over the unmonitored bypass: anyone with access to the
audit log stream can reconstruct who read what, even though the read
itself is not gated.

## What this document is NOT

Closing the service-principal bypass requires one of:

- **Per-client service principal** (replaces the global `BACKEND_API_KEY`).
- ~~**Row-level security on `profiles`**~~ **DONE** (migration `023_enable_rls_profiles`, issue #95): FORCE RLS + `profiles_service_all` (GUC '0') + owner CRUD policies. The exception now lives in the database; the app-level filter remains as defense in depth.
- **Secret rotation** moved out of plain-text env into a managed secret store.

The first and third items remain open. This
document exists so that, when those changes happen, the existing
behaviour is described here as the reference point.

## Source of truth

- `backend/app/api/v1/profiles.py:108-141` — the `if user.id != 0` carve-out and the log emission.
- `backend/app/api/deps.py:179-225` — `optional_auth` building the service user (protected + open paths).
- `backend/tests/test_profile_ownership.py` — the existing carve-out pinner and the new audit-log tests for #87.
- The MCP adapter at `mcp-adapter/src/asistcv_mcp/server.py` is the production user of this principal (single-user design).
