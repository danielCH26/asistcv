# Feature: profile-cv-jd-tabs

> **Issue**: #61 (milestone v1.0)
> **Branch**: `feat/profile-cv-jd-tabs` (off main @ a083b43)
> **Scope**: Two clearly differentiated tabs in `/profile` — "CV vs JD" (existing match flow, unchanged) and "Solo CV" (cv-only audit, new UI). Mode hints, i18n es/en, auth preserved, zero regression.

---

## Specs

### S1 — Two accessible tabs in /profile

*"En /profile se ven dos tabs claramente diferenciadas."* A `role="tablist"` with two `role="tab"` buttons (`aria-selected`), following the existing pattern in `routes/audit/+page.svelte:110-129` (the in-repo reference). Default tab: **CV vs JD**. Labels + hints in both locales; `check-i18n-keys.mjs` parity stays green (keys added to BOTH `es.json` and `en.json`).

### S2 — "CV vs JD" tab: existing flow, non-regression (interpretation decision documented)

The issue text says *"reutilizar `JdForm` + flujo actual (`audit_jd_directed`)"* — but mapping showed the current `/profile` analysis section calls **`POST /v1/match`** (the authenticated product match), not the audit funnel. The acceptance criterion *"CV vs JD sigue funcionando end-to-end como antes"* is authoritative: the flow to preserve is `/v1/match`. Switching to `audit_jd_directed` would silently replace the product match — a capability regression, not a refactor.

Therefore: **Tab 1 keeps `runMatch()` / `apiClient.match()` exactly as-is**, re-wrapped in `JdForm` for the shared input UX. `JdForm` gains optional `headingKey` / `introKey` props (defaults = current `home.heading` / `home.intro`) so `/profile` can pass profile-scoped copy without touching the home page (backwards compatible, home renders byte-identical).

### S3 — "Solo CV" tab: cv-only audit with dedicated UI

*"Solo CV produce el análisis del CV sin pedir JD."* Implementation: `auditStore.submit('' /* no JD */, cvText, cvFile)` → `apiClient.auditAnonymous` **without `jd_text`** → backend `cv_only` mode. Result render: score, `problematicas` (severity chips), `recomendaciones`, `fortalezas`, reasoning — reusing the render semantics of the audit funnel's cv_only branch (`routes/audit/+page.svelte:197-227`). Validation/API errors surface in a `role="alert"` block (422 `PDF_NO_TEXT`, 429 rate limit, etc.).

**CV input contract (mapping finding):** `/profile`'s stored CVs expose only `structured` via `getCv` — there is no FE endpoint returning a stored CV's raw text/PDF, and adding one is backend scope this issue does not include. So Solo CV sources its input the same way the funnel does: **PDF upload (≤10 MB) or pasted text (≥50 chars)**, presented with a PDF/text mode switch. Re-uploading is slightly redundant but honest, shippable, and backend-zero.

### S4 — Mode hints before input

*"Cada tab debe mostrar la pista del modo (qué analiza y qué no) antes del input."* Each tab renders a one-line hint above its input: CV vs JD explains it scores the CV against the pasted JD; Solo CV explains it audits the CV alone (no JD required, no match score against a position). Both hints localized es/en.

### S5 — Auth preserved

*"Mantener auth: ambos tabs requieren usuario autenticado (no usar funnel anónimo acá)."* Both tabs live inside the existing `{#if ready}` block that only renders after `requireSession()` resolves (`+page.svelte:53-62`) — no navigation to `/audit`, no anonymous funnel UI. (The backend endpoint remains anonymous-by-design; the gate is the page.)

### S6 — Zero regression

*"Sin regresión en tests existentes de /profile (`audit-page.test.ts` debe seguir verde)."* `audit-page.test.ts` renders only `routes/audit/+page.svelte` and is untouched by construction; verified after every task. Also green: full vitest suite (10 files / 78 tests baseline + new profile tests), `svelte-check` 0 errors, `npm run build` green, existing profile sections (CV upload/list/editor, adaptation) unchanged.

---

## Tasks

| ID | Title | Route | Linked S# | Commit |
|---|---|---|---|---|
| T1 | RED profile-page test (tabs, default tab, tab1 renders match UI) → GREEN: tab scaffold + i18n keys + JdForm props + match section into tab 1 | direct | S1,S2,S4 | `feat(profile): tabbed analysis modes with i18n labels (T1 of #61)` |
| T2 | RED solo-CV tests (hint, file submit omits jd_text, text submit sends cv_text, result render, error alert) → GREEN: solo section via auditStore | direct | S3,S4,S5 | `feat(profile): solo CV tab wired to cv-only audit (T2 of #61)` |
| T3 | QA (vitest full, svelte-check, build, i18n parity, audit-page.test.ts) + feature doc close | direct | S6 | `test(profile): full QA pass, closes #61` |

---

## Log

### L1 — User's verbatim request (2026-10-07)

> "Continua"

(Within the standing directive: *"Sigue la ruta que consideres mas optima, pusheas, haces testeo qa cuando sea pertinente…"* — #61 follows #54 per the agreed v1.0 route.)

### L2 — Mapping findings that shaped the design (2026-10-07)

- The current `/profile` match section uses `/v1/match` (`runMatch`, L193-217), NOT `audit_jd_directed` as the issue text assumed. Decision in S2.
- `JdForm` is generic capture but hardcodes `home.heading`/`home.intro` inside itself — parameterized in T1.
- `auditStore.submit(jdText, cvText, cvFile)` already validates JD ≥50 and omits `jd_text` when empty — Solo CV reuses it verbatim.
- Stored CVs expose only `structured`; no raw-text fetch endpoint → Solo CV re-uses funnel input modes (S3).
- `audit-page.test.ts` mocks `$api/client` and renders only the audit route — structurally unaffected.
- Profile test needs `requireSession` from `$stores/session` mocked (page gates on it) plus the 9 `apiClient.*` methods the page calls.

### L3 — Evidence / commits (appended as work progresses)

- TBD per task.