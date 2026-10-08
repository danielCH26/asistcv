# AsistCV Design System

The visual language of the frontend: a **corporate teal palette** with a
**claymorphism elevation system** on a Swiss-minimalist layout. This document
is the human-facing contract; the machine-facing contract lives in
`src/lib/tokens/*.ts` and `src/app.css` (canonical).

---

## 1. Layers

| Layer | What | Where |
|---|---|---|
| 0 | Mode-invariant primitives (score fills, on-score ink) | `app.css` `:root` |
| 1 | Clay elevation system (shadows, rim highlights, focus ring) | `app.css` + `tokens/shadow.ts` |
| 2 | Layout primitives (spacing, radius, typography, motion) | `app.css` + `tokens/{spacing,radius,typography,motion}.ts` |
| 3 | Semantic palette per colour scheme (light + dark block) | `app.css` + `tokens/colors.ts` |
| 4 | Component classes (`.login__form input`, `.plan-card`, …) | each route/component `<style>` |

**Parity rule:** `app.css` is canonical. Every token value must stay
byte-identical to its entry in `src/lib/tokens/*.ts` — `tokens.test.ts`
enforces it. Edit both in the same commit.

---

## 2. Colour palette (corporate teal)

### Light scheme

| Token | Value | Role |
|---|---|---|
| `--color-action` | `#0f766e` | Primary actions, active nav, brand chip |
| `--color-on-action` | `#ffffff` | Label on action (5.47:1 AA) |
| `--color-accent-hover` | `#115e59` | Hover step (7.58:1 AAA) |
| `--color-accent-pressed` | `#134e4a` | Pressed step (9.48:1 AAA) |
| `--color-action-muted` | `#ccfbf1` | Muted teal surface (chips, banners) |
| `--color-info` / `--color-info-muted` | `#0f766e` / `#ccfbf1` | Informational accents |

### Dark scheme (accent flips to light, label flips to dark)

| Token | Value | Contrast vs `#0f172a` label |
|---|---|---|
| `--color-action` | `#5eead4` | 12.07:1 |
| `--color-accent-hover` | `#99f6e4` | 14.16:1 |
| `--color-accent-pressed` | `#2dd4bf` | 9.59:1 |
| `--color-action-muted` | `#134e4a` | — |

**Rule:** teal-600 `#0d9488` is **forbidden** as a fill under white labels
(3.74:1, fails AA 4.5:1). The action floor is teal-700.

### Score colours (mode-invariant)

`--score-low #dc2626`, `--score-mid #92400e`, `--score-high #047857` behind
white labels; `--score-*-ink` for text on light surfaces. See
`tokens/colors.ts` for measured ratios.

---

## 3. Clay elevation system

Three depths, each composed of a light shadow (top-left), a dark shadow
(bottom-right) and an inner rim highlight:

| Token | Depth | Use |
|---|---|---|
| `--clay-raised` | subtle | resting state of controls, inputs, cards |
| `--clay-lifted` | medium | **hover** of controls; focus of inputs |
| `--clay-floating` | high | overlays/popovers (rare) |
| `--clay-fill` | surface | the matte fill of clay inputs & secondary controls |
| `--clay-focus-ring` | ring | keyboard focus, always stacked **over** raised/lifted |

### Usage rules

1. **Controls get clay.** A real `<button>` (submit, signup, logout,
   LanguageToggle) gets: resting `--clay-raised`, hover `--clay-lifted`,
   focus-visible `--clay-focus-ring, --clay-raised` with `outline: none`,
   and `transition: box-shadow var(--duration-fast) var(--ease-standard)`.
2. **Destinations stay flat.** Nav links never hover-lift. The active page
   may carry `--clay-raised` + `font-weight: 600` as a state marker, but it
   is only ever "arrived at", never pressed.
3. **Cards are surfaces.** Result cards and plan cards carry
   `--clay-raised` over a `1px solid var(--color-line)` border. **No
   hover-lift** — they are not controls.
4. **Disabled controls don't float.** `disabled` → `box-shadow: none`
   (keep the fill), `cursor: not-allowed`.
5. **ScoreCard is exempt.** Its solid score fill is the signal; elevation
   would compete with it (audit decision).

### Canonical patterns

- **Input:** `background: var(--clay-fill)`, `box-shadow: var(--clay-raised)`,
  focus-visible → `box-shadow: var(--clay-focus-ring), var(--clay-raised)`.
  Reference: `CvStructuredForm.svelte`, `login/+page.svelte`.
- **Primary button:** `background: var(--color-action)`,
  `color: var(--color-on-action)`, weight 600, clay control pattern. 
  Reference: `.plan-card button` (billing), auth submit buttons.
- **Secondary button:** `background: var(--clay-fill)`,
  `color: var(--color-ink)`, same clay control pattern.
  Reference: `.billing__current button`.
- **Brand chip (header logo):** action fill + `--clay-raised`.
  Reference: `.app-shell__logo`.

---

## 4. Forbidden: legacy aliases

The old flat-era aliases are removed from shipped pages and must not come
back. Use the modern token instead:

| Legacy (do not use) | Modern token |
|---|---|
| `--surface` | `--color-surface` |
| `--border` | `--color-line` |
| `--accent` | `--color-action` |
| `--accent-contrast` | `--color-on-action` |
| `--text` / `--text-strong` / `--text-muted` | `--color-ink` / `--color-ink-strong` / `--color-ink-muted` |

---

## 5. Testing contract

- `tokens.test.ts` — byte parity `app.css` ↔ `src/lib/tokens/*.ts`, plus
  structural invariants. Breaks if you edit one side only.
- `contrast.test.ts` — recomputes every documented WCAG pair from the hex
  values. If you change a palette value, the suite recalculates: AA 4.5:1
  for text pairs, 3:1 for the 1.4.11 boundary token
  (`--color-line-strong`).
- Run: `npx vitest run src/lib/tokens` (tokens) or `npx vitest run` (all)
  and `npm run check` (svelte-check) after any style change.

## 6. History

- v1: sober sky-blue palette, flat surfaces (PRs #54, #64, #89, #97, #98).
- v2 (issue #60): corporate teal palette, clay elevation rolled out to
  header, auth, billing, result cards; legacy aliases retired from shipped
  pages. Commits `3be1cad`, `402d19d`, `df7246a`, `395638f`, `f8e6a40`.
