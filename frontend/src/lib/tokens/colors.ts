/**
 * Color tokens — the typed registry of the eptus palette in `app.css`.
 *
 * `app.css` is canonical: these values MUST stay byte-identical to the
 * declarations there (`tokens.test.ts` enforces it). Edit both in the same
 * commit, and re-run the contrast suite — `contrast.test.ts` recomputes
 * every documented WCAG pair from these hex values.
 *
 * There are TWO surfaces, and each one has its own palette:
 *
 *   · `palette`      — the marketing surface (editorial, light). These are
 *                      the `:root` values in app.css.
 *   · `appPalette`   — the app surface (instrument, dark). These are the
 *                      values in the `[data-surface='app']` block.
 *
 * The brand indigo (#4f46e5) is the same in both: what changes is the
 * environment around it, and how much contrast has to be fought for.
 *
 * Naming follows the shipped system (Layer 0 mode-invariant primitives +
 * Layer 3 sober palette) — see `odd/tasks/feat-design-tokens-v1.md` S1.
 */

/**
 * Score fills (Layer 0). They sit behind a white label, so white is tuned
 * against them — and they are the SAME in both surfaces, because the white
 * label has to clear 4.5:1 wherever the fill appears.
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

/** The label ink for the score fills. Invariant by the same argument. */
export const onScoreFill = { '--color-on-score-fill': '#ffffff' } as const;

/**
 * Text counterparts of the fills — the MARKETING surface values. The app
 * surface has its own (lighter) set in `appPalette`.
 */
export const scoreInks = {
	'--score-low-ink': '#b91c1c',
	'--score-mid-ink': '#92400e',
	'--score-high-ink': '#065f46',
} as const;

/**
 * Marketing palette (Layer 3, light). Every text-on-surface pair is
 * asserted >= 4.5:1 by `contrast.test.ts`.
 *
 * Identity: deep indigo + cold neutrals with a violet cast. The action hue
 * is separated from the semantic greens (success / score-high) so a primary
 * button never reads as "state: good".
 *
 * Boundary tokens:
 *   --color-line-strong #6b6b83 measures 4.73:1 on canvas and 5.06:1 on
 *   surface — it is the opt-in 3:1 boundary for WCAG 1.4.11 (form fields,
 *   focusable controls), not a text colour.
 */
export const palette = {
	// canvas + surfaces
	'--color-canvas': '#fbfbfd',
	'--color-surface': '#ffffff',
	'--color-surface-alt': '#f3f3f9',
	'--color-line': '#e4e4ee',
	'--color-line-strong': '#6b6b83',

	// ink
	'--color-ink': '#16161f',
	'--color-ink-strong': '#0b0b12',
	'--color-ink-muted': '#5b5b70',

	// action / primary
	'--color-action': '#4f46e5',
	'--color-on-action': '#ffffff',
	'--color-action-muted': '#e9e9fe',
	// Hover/pressed steps. White label on either holds AAA (7.90:1 hover,
	// 9.93:1 pressed).
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

	// info — shares the brand hue; on its muted tint it measures 6.47:1
	'--color-info': '#4f46e5',
	'--color-on-info': '#ffffff',
	'--color-info-muted': '#e9e9fe',
} as const;

/**
 * App palette — the dark instrument surface.
 *
 * The action colour is the LIGHT indigo with a dark label: on a dark canvas
 * the contrast comes from being above the surface, not from reusing the
 * marketing indigo. With #4f46e5 the white label measured 7.7:1 and the
 * button read as muted; with #a5b4fc the #0c0c14 label measures 8.02:1 and
 * the button pops. It also fixes the status chips: `--color-action` over
 * `--color-action-muted` was 2.7:1 with the dark indigo and is 8.45:1 with
 * the light one.
 */
export const appPalette = {
	// canvas + surfaces
	'--color-canvas': '#0c0c14',
	'--color-surface': '#10101a',
	'--color-surface-alt': '#171726',
	'--color-line': '#1f1f2e',
	'--color-line-strong': '#75759a',

	// ink
	'--color-ink': '#e8e8f2',
	'--color-ink-strong': '#f7f7fd',
	'--color-ink-muted': '#9a9ab2',

	// action / primary — light indigo, dark label
	'--color-action': '#a5b4fc',
	'--color-on-action': '#0c0c14',
	'--color-action-muted': '#1a1a3a',
	'--color-accent-hover': '#c7d2fe',
	'--color-accent-pressed': '#a5b4fc',

	// success
	'--color-success': '#34d399',
	'--color-on-success': '#042f2e',
	'--color-success-muted': '#0d2a22',

	// warning
	'--color-warning': '#fbbf24',
	'--color-on-warning': '#422006',
	'--color-warning-muted': '#2a1e08',

	// danger
	'--color-danger': '#fb7185',
	'--color-on-danger': '#450a0a',
	'--color-danger-muted': '#2c1218',

	// info — one step lighter than the action, for accent TEXT
	'--color-info': '#c7d2fe',
	'--color-on-info': '#0c0c14',
	'--color-info-muted': '#1a1a3a',

	// score inks, light end
	'--score-low-ink': '#fca5a5',
	'--score-mid-ink': '#fde047',
	'--score-high-ink': '#6ee7b7',
} as const;

/** Flat registry: every color token name -> its `app.css :root` value. */
export const colorTokens: Record<string, string> = {
	...scoreFills,
	...onScoreFill,
	...scoreInks,
	...palette,
};

/**
 * Flat registry: every color token name -> its `[data-surface='app']` value.
 *
 * The score FILLS and the label ink are deliberately NOT here: they are
 * Layer 0, they are the same in both surfaces, and the app block inherits
 * them from `:root`. Redeclaring them here would create a second place
 * where they could drift apart — which is exactly the failure the Layer 0
 * argument exists to prevent.
 */
export const appColorTokens: Record<string, string> = {
	...appPalette,
};

export type ColorToken = keyof typeof colorTokens;
export type AppColorToken = keyof typeof appColorTokens;
