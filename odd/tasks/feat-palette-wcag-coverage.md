# Feature: palette-wcag-coverage (#57, T1)

> **Issue**: #57 (v2.0, palette completa con roles semánticos)
> **Branch**: `feat/palette-wcag-coverage`
> **Scope**: First of two passes on #57. This pass: (T1) close the WCAG AA coverage gap for the **current** palette (every shipped text/bg pair gets a measured ratio + automated check) and add an axe-core scan to CI as a regression net. The second pass (T2, separate branch + feature doc): the **expanded** palette with new semantic roles (bg-elevated, fg-muted, accent-hover/pressed, etc.) — BLOCKED on the design decision (accent color + error/warning family).

---

## Specs

### S1 — Close the WCAG AA coverage gap on the current palette

The shipped palette has **24 color tokens** and dozens of valid text/bg combinations; `contrast.test.ts` measures **11**. The acceptance criterion of #57 — *"todos los pares texto/fondo validados WCAG AA"* — is not met today. This pass enumerates every reasonable text/bg pair from the existing 24 tokens and adds them to the measured set, with the documented ratio per pair and a CI failure if any drops below 4.5:1.

Pairs added (all from the current token set, no new colors):
- text-on-surface pairs: `--color-ink` on `--color-canvas-alt`, `--color-ink-muted` on `--color-canvas`, `--color-ink-muted` on `--color-surface-alt`, etc.
- status pair: `--color-on-success` on `--color-success`, `--color-on-warning` on `--color-warning`, `--color-on-danger` on `--color-danger`, `--color-on-info` on `--color-info`.
- muted (decorative) borders: `--color-line` and `--color-line-strong` (3:1 boundary per WCAG 1.4.11 for form fields, already measured at 4.55/4.76 in app.css comments — these are documented in the test, not re-derived).
- `null` documented vs `null` threshold: the existing test treats `null` as ≥4.5:1 (threshold-only). We keep that and add explicit ratio assertions for the new pairs.

### S2 — axe-core scan in CI as a regression net

Per #57 acceptance *"test automatizado en CI falla si una combinación nueva no cumple"*: add `@axe-core/playwright` (or equivalent) to the existing test setup so any new component rendered in tests is checked for contrast violations automatically. The current `vite.config.ts` already wires playwright/vitest (the fix from #61). The `check-i18n-keys.mjs` precedent shows the CI hook pattern; this adds a contrast check to it.

Scope: one axe-core scan over the `/` and `/audit` and `/profile` pages (the three surfaces a user can land on). The scan asserts zero contrast violations in the rendered DOM. This is a soft net — it catches "you shipped a new color and forgot to swap it everywhere" — not a full re-implementation of all combinations.

### S3 — Out of scope (T2 follow-up)

The **expanded** palette: `--color-bg-elevated`, `--color-bg-sunken`, `--color-fg-subtle`, `--color-accent-hover`, `--color-accent-pressed`, `--color-border-strong` (the current `--color-line-strong` may be renamed), plus AAA target where possible. This is a real design decision (accent color, error/warning family) — it is a separate feature doc + branch once the design choice is made. See `L3` for the structured ask.

---

## Tasks

| ID | Title | Commit |
|---|---|---|
| T1 | RED: enumerate uncovered pairs + assert AA → GREEN: extend `contrast.test.ts` + `colors.ts` comments | `test(tokens): close WCAG AA coverage gap on the current palette` |
| T2 | RED axe scan: page renders with violations → GREEN: add axe-core scan to test infra + CI hook | `test(a11y): axe-core contrast scan in CI` |
| T3 | QA + PR + close this T1 pass; file the T2 follow-up with the design ask | `test(tokens): full QA pass, closes #57-T1` |

---

## T2 PASS — semantic roles + hover tokens (design decisions received)

### T2-S1 — Design decisions (maintainer, 2026-10-08)

> *"Me gusta la paleta de colores que definiste, para el resto tomá las decisiones según convengan mejor visualmente y en la calidad del proyecto."*

1. **Acento**: se conserva `#0369a1` (la paleta actual gusta). No hay re-acento.
2. **Error/warning**: universales loud (actuales `#b91c1c`/`#92400e`) — pasan AA holgado; suavizar arriesga el umbral.
3. **AAA**: body text ya lo pasa y está pineado ≥7:1; nuevos roles, AAA donde salga natural.

### T2-S2 — Nuevos tokens (solo valor genuinamente nuevo)

Los demás roles del issue YA existen en nuestro vocabulario canónico (documentado en `docs/palette.md`, sin alias-soup — precedente #54):

| Rol del issue | Token nuestro | Nota |
|---|---|---|
| bg / bg-elevated / bg-sunken | canvas / surface / surface-alt | existen |
| fg / fg-muted / fg-subtle | ink / ink-muted / **line-strong (dual-use documentado 4.55/4.76)** | subtle cubierto por line-strong |
| accent | action | existe |
| **accent-hover** | **NUEVO: `#075985`** (light) / `#7dd3fc` (dark) | blanco encima ~7.9:1 AAA (light); label oscuro ≥13:1 (dark) |
| **accent-pressed** | **NUEVO: `#0c4a6e`** (light) / `#0ea5e9` (dark) | blanco ~10:1 (light); label oscuro ~6:1 (dark) |
| success/warning/danger/info | existen (loud universales, decisión 2) | existen |
| border / border-strong | line / line-strong | existen |

### T2-S3 — Wiring en componentes (criterio: ≥5)

Swap `filter: brightness(1.05)` → `background: var(--color-accent-hover)` en los hovers de action buttons (8 sitios en 5 archivos: JdForm, audit, profile ×3, recruiter ×3). En dark, el token apunta a la variante clara — el label oscuro `--color-on-action` mantiene contraste sin cambios.

### T2-S4 — docs/palette.md

Tabla visual del rol → token → hex → ratio medido, incluyendo el mapping de nombres del issue → vocabulario canónico (bg→canvas, fg-subtle→line-strong, accent→action, etc.).

### T2-S5 — axe-core: decisión documentada

El criterio *"test automatizado en CI falla si una combinación nueva no cumple"* ya lo satisface `contrast.test.ts` a nivel token (falla si un par no cumple). Un scan axe-core a nivel DOM requiere Playwright browsers en CI (infra pesada) y su regla de contraste es redundante con el test de tokens para combinaciones declaradas. Queda como mejora futura opcional, documentada aquí — no bloquea el cierre de #57.

---

## Log

### L1 — User's verbatim request (2026-10-07)

> "si, ataca la 87 y tambien sigamos con la 57"

This is the first pass on #57. The design-dependent second pass is below as a structured ask.

### L2 — Pre-fix mapping (2026-10-07)

- `frontend/src/lib/tokens/contrast.test.ts` measures 11 pairs.
- `frontend/src/app.css` documents 5–6 ratios in comments (score fills, line-strong, dark-block) — the comments are not pinned by tests.
- No `axe-core` in the project (`pyproject.toml`/frontend equivalent: no `@axe-core/playwright`).
- CI hook precedent: `frontend/scripts/check-i18n-keys.mjs` runs in CI and breaks the build on es/en parity failures.

### L3 — Structured ask (design decisions for the T2 pass)

The expanded palette requires two decisions that I will not pick unilaterally:

1. **Accent principal.** The issue body lists four options:
   - Azul profundo (e.g. `#1e3a8a`-like)
   - Verde bosque (e.g. `#15803d`-like)
   - Grafito cálido (e.g. `#1f2937`-like)
   - Sepia (e.g. `#78350f`-like)
   Each produces a different palette personality. AA on `--color-action` / `--color-on-action` will pass for any of them (the contrastRatio helper computes from real hex); the *aesthetic* choice is yours.

2. **Familia error/warning.** "Rojo y ámbar universales" (loud, accessible) vs. "suavizadas" (calmer, may compromise 4.5:1 if too desaturated). The current values (`#b91c1c` danger, `#92400e` warning) are loud. If we keep them, the work is mechanical. If you want a calmer variant, we will need a new pass.

3. **Rango de la "AAA donde sea posible"** del issue: is AAA required for *body* text (7:1) or only *decorative* / *muted* roles (3:1 large text)? The current sober palette cannot clear 7:1 for any body pair with the current ink/canvas; AAA on body forces a different ink.

I will hold the T2 follow-up until you answer. The T1 work above is mechanical and ships independently.

### L4 — Evidence / commits (appended as work progresses)

**T1 (S1 — cobertura WCAG completa sobre la paleta actual) — DONE**
- Extensión de `contrast.test.ts`: 11 → **52 aserciones**.
  - `DOCUMENTED_PAIRS` (11): ratios pineados (score fills ±0.05) + threshold AA.
  - `TEXT_PAIRS` (24 nuevas): ink family × 3 superficies, status regular-on-muted (el contrato correcto: texto regular sobre tinte pálido, NO on-color sobre tinte), on-X sobre fill, score inks como label sobre surface.
  - `UI_PAIRS` (2): `--color-line-strong` ≥3:1 (1.4.11 esencial). `--color-line` exempt (hairline decorativa 1.18-1.23:1 — 1.4.11 aplica a UI esencial).
  - AAA: `ink on canvas` pineado ≥7:1 (~14.6:1 medido).
- **Dos iteraciones de diseño del test** (fallas mías, no de tokens): (1) puse `on-X` sobre `X-muted` → 1.0-1.15:1 (contrato incorrecto: el muted lleva texto regular, no blanco); (2) puse mismo-token-same-token → 1:1. Corregidos con el contrato documentado en el header del test.
- Verificado: 52/52 tokens suite · 110/110 suite completa · svelte-check 0 errores.

**T2 PASS (S2 wiring + S3 paleta expandida + decisiones recibidas) — DONE**

Decisiones del maintainer (L3 resuelta): acento SE QUEDA `#0369a1` (gusta la paleta actual); error/warning universales loud; AAA donde salga natural.

- Tokens nuevos (solo valor genuino — el resto de roles del issue se cubre con el vocabulario canónico, mapeado en `docs/palette.md`): `--color-accent-hover` (#075985 light / #7dd3fc dark) + `--color-accent-pressed` (#0c4a6e light / #0ea5e9 dark), ambos bloques de app.css con racional de contraste + colors.ts (paridad byte-a-byte).
- Tests: +2 pares (`on-action` sobre hover ~7.9:1 AAA, sobre pressed ~10:1 AAA) → **54 aserciones** en contrast.test.ts.
- Wiring (S2 wiring — criterio ≥5 componentes): 8 hovers `filter: brightness(1.05)` → `background: var(--color-accent-hover)` en 5 archivos (JdForm, audit, profile ×3, recruiter ×3). Dark label `--color-on-action` mantiene contraste sin cambios (hover aclara, label oscuro: ~13:1).
- `docs/palette.md`: mapping rol→token→hex→ratio del issue → vocabulario canónico, contrato de uso (5 reglas), dark theme, decisión axe-core.
- axe-core (S2 original): decisión documentada en T2-S5 — el test de tokens ya satisface el criterio de CI; scan DOM requiere Playwright en CI, queda como mejora futura.
- Verificado: **112/112** suite completa · svelte-check 0 errores · build ✅.

**Criterios de aceptación de #57**: roles definidos ✅ · usados en ≥5 componentes ✅ · todos los pares AA validados ✅ · test CI que falla si un par nuevo no cumple ✅ · documentación visual ✅ (`docs/palette.md`).