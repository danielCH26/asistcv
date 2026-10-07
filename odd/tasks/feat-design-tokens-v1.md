# Feature: design-tokens-v1

> **Issue**: #54 (milestone v1.0)
> **Branch**: `feat/design-tokens-v1` (off main @ 7ae2d81)
> **Scope**: Complete the token system: TS layer (6 files) + automated WCAG AA check + migrate the remaining 85 hardcoded literals in routes. NOT a redesign.

---

## Specs

### S1 — Six TS token files exist (issue verbatim)

*"Existe `frontend/src/lib/tokens/` con los 6 archivos"* — `colors.ts`, `typography.ts`, `spacing.ts`, `radius.ts`, `shadow.ts`, `motion.ts`.

**Naming decision (spec deviation, documented):** the issue's proposed names were written before the CSS-first implementation shipped (PRs #66–#68). The TS layer mirrors the **existing** vocabulary instead of introducing a third one:

| Issue proposed | Ships as | Why |
|---|---|---|
| `--color-bg` / `--color-fg` | `--color-canvas` / `--color-ink` (+ `--color-surface`, `--color-ink-strong/muted`) | semantic system already shipped and used by 10 components |
| `--shadow-*` sm/md/lg/xl | `--clay-raised/lifted/floating` + `--clay-focus-ring` | clay elevation is measured, shipped, mode-scoped |
| `--motion-*` (100/200/400ms) | `--duration-instant/fast/base/slow` (80/140/220/340ms) + `--ease-standard/out/in/spring` | shipped values; issue numbers were pre-implementation guesses |
| radius 0/4/8/12/999 | `--radius-control/card/card-lg/panel/pill/circle` (6/8/10/12/999px/50%) | shipped scale, documented as byte-identical renames of 78 literals |

Acceptance: files exist, export typed constants, and every exported value matches the corresponding CSS custom property.

### S2 — TS ↔ app.css consistency is machine-checked

One source of truth per value: `app.css` stays canonical for the CSS cascade; the TS files are the typed registry. A test parses `:root` from `app.css` and asserts **every** TS-exported token resolves to the identical CSS value (and that every TS token name exists in CSS). Drift in either direction fails the suite.

### S3 — WCAG AA is an automated test, not a comment

`app.css:85-91` admits: *"There is no automated check for it yet … A previous revision of this comment cited a `contrast-audit.mjs` that was never committed."* This feature commits that missing check:

- `contrast.test.ts` computes WCAG 2.1 relative-luminance ratios from the TS hex values.
- Asserted pairs (light): `#ffffff` on `--score-low/mid/high` ≥ 4.5 (documented 4.83/7.09/5.48); `--color-ink` on `--color-canvas` and `--color-surface` ≥ 4.5; `--color-on-action` on `--color-action` ≥ 4.5; `--color-warning` (used as text) on `--color-warning-muted` and `--color-canvas` ≥ 4.5; `--color-ink-muted` on `--color-surface` ≥ 4.5.
- The stale comment in `app.css` is updated to point at the test.

### S4 — WCAG ratios documented in colors.ts (issue verbatim)

*"Validación WCAG AA documentada en `colors.ts` (comentarios con el ratio)"* — each documented pair carries its measured ratio in a comment next to the export.

### S5 — Zero hardcoded radius/spacing/font-size in routes and components

Current debt (measured): **37** `border-radius` + **44** spacing (`padding/margin/gap`) + **4** `font-size` literals across 20 `.svelte` files, concentrated in: `history/[id]` (19), `billing` (14), `signup` (13), `login` (7), `history` (6). Exclusions (not literals-to-fix): `1px` border longhands/shorthands, width/height/max-width dimensions, `@media` preludes (see app.css `--breakpoint-sm` warning — var() in media conditions silently no-ops), `var()` fallbacks.

Acceptance: re-running the audit grep yields 0 hits in the counted categories. Partially-tokenized declarations (`padding: var(--space-2) 0.75rem`) count as hits until fully tokenized.

### S6 — No visual regression

Every substitution is a pure rename to a byte-identical value (the token system was built that way — app.css:233-235 documents the 78-literal radius swap as zero-visual-change). Proofs: `svelte-check` 0 errors, `vitest run` green (8 existing files + new token tests), `npm run build` succeeds, and no substitution changes the computed value.

---

## Tasks

| ID | Title | Route | Linked S# | Commit |
|---|---|---|---|---|
| T1 | RED: consistency + contrast tests → GREEN: 6 TS token files | direct | S1-S4 | `feat(tokens): typed token layer with machine-checked CSS parity and WCAG AA` |
| T2 | Migrate `routes/history/[id]` (19 literals) | direct | S5 | `refactor(ui): tokenize history detail route` |
| T3 | Migrate `routes/billing` (14 literals) | direct | S5 | `refactor(ui): tokenize billing route` |
| T4 | Migrate `routes/signup` + `routes/login` (20 literals) | direct | S5 | `refactor(ui): tokenize auth routes` |
| T5 | Migrate `routes/history` + remaining stragglers (~15 literals) | direct | S5 | `refactor(ui): tokenize remaining routes, zero literal audit` |
| T6 | Final QA (vitest + svelte-check + build + audit grep) | direct | S6 | `test(tokens): full QA pass, closes #54` |

---

## Log

### L1 — User's verbatim request (2026-10-07)

> "Continua"

(Within the standing directive: *"Sigue la ruta que consideres mas optima, pusheas, haces testeo qa cuando sea pertinente…"* — #54 is the next v1.0 issue after #51 per the agreed route.)

### L2 — Pre-work mapping (2026-10-07, delegated explorer)

- `frontend/src/lib/tokens/` does not exist (greenfield).
- `app.css`: 109 unique custom properties, 5 documented layers, dark + reduced-motion blocks.
- Components: **0 hardcoded colors** (already clean); debt is radius/spacing/font-size only.
- WCAG ratios live in comments only; the cited `contrast-audit.mjs` was never committed.
- Vitest is configured in `vite.config.ts` (jsdom, setup at `src/tests/setup.ts`); 8 test files already exist; co-location convention `src/lib/**/*.test.ts`.

### L3 — Rationale for value divergence from the issue text

The issue's numbers (radius 4/8/12, motion 100/200/400, shadows sm/md/lg/xl) predate the shipped system. Adopting them now would mean changing ~200 computed values across 10 components + 5 routes for zero user-visible gain, and re-measuring every contrast pair. The shipped values are measured and documented; the acceptance criteria of the issue (6 files, CSS vars, 3+ usages, WCAG docs, no regression) are all satisfiable on top of them. The divergence is recorded in S1's table.

### L4 — Evidence / commits (appended as work progresses)

**T1 (S1-S4 — TS token layer + machine checks) — DONE**
- RED: `tokens.test.ts` (14 parity/coverage tests) + `contrast.test.ts` (13 WCAG tests) failed on missing modules.
- GREEN: 6 files in `frontend/src/lib/tokens/` (colors/typography/spacing/radius/shadow/motion), values verbatim from `app.css :root`. The contrast suite recomputes WCAG 2.1 ratios and its pinned score-fill ratios (4.83/7.09/5.48 ±0.05) matched the documented measurements on first run — the formula agrees with the year-old manual audit.
- Stale `app.css` comment ("no automated check for it yet", cited an uncommitted `contrast-audit.mjs`) replaced with a pointer at the test.
- Fix during GREEN: `import.meta.url` is not a `file:` URL under the esm-env alias — CSS resolved from `process.cwd()` instead.
- Verified: vitest 78/78 (10 files), svelte-check 0 errors.

**T2–T5 (S5 — literal migration) — DONE (delegated writer)**
- 85 substitutions, all byte-identical renames: radius 37, spacing 44, font-size 4. Zero UNMAPPED — every literal had an exact token.
- T2 `20a1e66` history/[id] (19) · T3 `e2d07eb` billing (14) · T4 `2dedf17` signup+login (20) · T5 `a828347` layout+audit+recruiter+profile+history + 9 components (32).
- Excluded as legitimate (documented): 29× `1px` borders, 16× width/height-family dims, 5× `@media` preludes (silent-no-op trap), ~20× bare `0` (repo convention, `--space-0` not substituted).
- Verified after every group: vitest 78/78, svelte-check 0 errors, final audit grep **0 / 0 / 0** across routes+components.

**T6 (S6 — final QA) — DONE**
- `npm run build` green (check-env guard + vite build + static adapter, 5.6s).
- Full verification matrix: vitest 10 files / 78 tests ✅ · svelte-check 0 errors ✅ · build ✅ · audit 0 literals ✅.