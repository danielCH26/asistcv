/**
 * Color tokens — the typed registry of the sober palette in `app.css`.
 *
 * `app.css` is canonical: these values MUST stay byte-identical to the
 * `:root` declarations there (`tokens.test.ts` enforces it). Edit both in the
 * same commit, and re-run the contrast suite — `contrast.test.ts` recomputes
 * every documented WCAG pair from these hex values.
 *
 * Naming follows the shipped system (Layer 0 mode-invariant primitives +
 * Layer 3 sober palette), NOT the `--color-bg`/`--color-fg` sketch from the
 * original issue — see `odd/tasks/feat-design-tokens-v1.md` S1.
 */

/**
 * Mode-invariant score fills (Layer 0). They sit behind a white label, so
 * white is tuned against them — in BOTH colour schemes, because these fills
 * never move per mode.
 *
 * MEASURED (WCAG 2.1 relative luminance), #ffffff against each fill:
 *   --score-low  #dc2626   4.83:1  (AA normal text)
 *   --score-mid  #92400e   7.09:1  (AA normal text)
 *   --score-high #047857   5.48:1  (AA normal text)
 */
export const scoreFills = {
	'--score-low': '#dc2626',
	'--score-mid': '#92400e',
	'--score-high': '#047857',
} as const;

/** The label ink for the score fills. Mode-invariant by the same argument. */
export const onScoreFill = { '--color-on-score-fill': '#ffffff' } as const;

/**
 * Text counterparts of the fills (mode-scoped in app.css dark block; the
 * values below are the light-scheme values).
 */
export const scoreInks = {
	'--score-low-ink': '#b91c1c',
	'--score-mid-ink': '#92400e',
	'--score-high-ink': '#065f46',
} as const;

/**
 * eptus palette (Layer 3, light scheme). Every text-on-surface pair is
 * asserted >= 4.5:1 by `contrast.test.ts` — the check app.css's comment used
 * to promise and never had.
 *
 * Identity: deep indigo + cold neutrals with a violet cast. The action hue is
 * separated from the semantic greens (success / score-high) so a primary
 * button never reads as "state: good".
 *
 * Boundary tokens:
 *   --color-line-strong #6b6b83 measures 4.89:1 on canvas and 5.18:1 on
 *   surface — it is the opt-in 3:1 boundary for WCAG 1.4.11 (form fields,
 *   focusable controls), not a text colour.
 */
export const palette = {
	// canvas + surfaces
	'--color-canvas': '#f8f8fc',
	'--color-surface': '#ffffff',
	'--color-surface-alt': '#f1f1f9',
	'--color-line': '#e3e4ef',
	'--color-line-strong': '#6b6b83',

	// ink
	'--color-ink': '#1c1c2b',
	'--color-ink-strong': '#111120',
	'--color-ink-muted': '#4c4c63',

	// action / primary
	'--color-action': '#4f46e5',
	'--color-on-action': '#ffffff',
	'--color-action-muted': '#e0e7ff',
	// Hover/pressed steps. White label on either holds AAA (7.90:1 hover,
	// 9.93:1 pressed). Dark-theme counterparts live in app.css dark block
	// (#c7d2fe / #a5b4fc with a dark label).
	'--color-accent-hover': '#4338ca',
	'--color-accent-pressed': '#3730a3',

	// success
	'--color-success': '#047857',
	'--color-on-success': '#ffffff',
	'--color-success-muted': '#ecfdf5',

	// warning — used as TEXT (JdForm, StrengthsGapsList), so held to 4.5:1
	'--color-warning': '#92400e',
	'--color-on-warning': '#ffffff',
	'--color-warning-muted': '#fffbeb',

	// danger
	'--color-danger': '#b91c1c',
	'--color-on-danger': '#ffffff',
	'--color-danger-muted': '#fef2f2',

	// info — shares the brand hue; on its muted tint it measures 5.10:1
	'--color-info': '#4f46e5',
	'--color-on-info': '#ffffff',
	'--color-info-muted': '#e0e7ff',
} as const;

/** Flat registry: every color token name -> its `app.css :root` value. */
export const colorTokens: Record<string, string> = {
	...scoreFills,
	...onScoreFill,
	...scoreInks,
	...palette,
};

export type ColorToken = keyof typeof colorTokens;
