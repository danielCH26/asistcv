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
 * Sober palette (Layer 3, light scheme). Every text-on-surface pair is
 * asserted >= 4.5:1 by `contrast.test.ts` — the check app.css's comment used
 * to promise and never had.
 *
 * Boundary tokens:
 *   --color-line-strong #64748b measures 4.55:1 on canvas and 4.76:1 on
 *   surface — it is the opt-in 3:1 boundary for WCAG 1.4.11 (form fields,
 *   focusable controls), not a text colour.
 */
export const palette = {
	// canvas + surfaces
	'--color-canvas': '#f8fafc',
	'--color-surface': '#ffffff',
	'--color-surface-alt': '#f1f5f9',
	'--color-line': '#e2e8f0',
	'--color-line-strong': '#64748b',

	// ink
	'--color-ink': '#1f2937',
	'--color-ink-strong': '#0f172a',
	'--color-ink-muted': '#475569',

	// action / primary
	'--color-action': '#0f766e',
	'--color-on-action': '#ffffff',
	'--color-action-muted': '#ccfbf1',
	// Hover/pressed steps (issue #57). White label on either holds >= AA
	// (5.47:1 hover — AA, 7.58:1 pressed — AAA). Dark-theme counterparts
	// live in app.css dark block (#99f6e4 / #2dd4bf with a dark label).
	'--color-accent-hover': '#115e59',
	'--color-accent-pressed': '#134e4a',

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

	// info
	'--color-info': '#0f766e',
	'--color-on-info': '#ffffff',
	'--color-info-muted': '#ccfbf1',
} as const;

/** Flat registry: every color token name -> its `app.css :root` value. */
export const colorTokens: Record<string, string> = {
	...scoreFills,
	...onScoreFill,
	...scoreInks,
	...palette,
};

export type ColorToken = keyof typeof colorTokens;
