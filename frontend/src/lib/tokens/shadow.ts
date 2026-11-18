/**
 * Shadow tokens — typed registry of the elevation system in `app.css`
 * (Layer 1). app.css is canonical; `tokens.test.ts` enforces parity.
 *
 * There are two depth systems, one per surface, and the difference is
 * physical rather than cosmetic:
 *
 *   · Marketing (light): an editorial plane. One barely-there shadow to lift
 *     the card off the canvas, and nothing else. Depth comes from the rules
 *     and the air.
 *   · App (dark): on a dark surface the bounce of light has nothing to come
 *     from — the background is already at the bottom of the range, so a
 *     strong white shadow has no gradient left to sit in and produces a
 *     hard glowing outline that reads as a stroke, not as light. So the
 *     light shadow collapses into a faint inset rim and the depth is carried
 *     entirely by a longer, softer dark shadow.
 *
 * Named by depth meaning ("raised" < "lifted" < "floating"). Composite
 * values are verbatim `var()` chains — copying them as anything else would
 * break byte parity with `:root`.
 */

/* --- Marketing (light) ---------------------------------------------------- */

export const clayFill = { '--clay-fill': '#f1f1f8' } as const;

export const raised = {
	'--clay-raised-shadow-light': '0 1px 2px rgba(22, 22, 40, 0.05)',
	'--clay-raised-shadow-dark': '0 1px 2px rgba(22, 22, 40, 0.05)',
	'--clay-raised-rim': 'none',
	'--clay-raised': 'var(--clay-raised-shadow-dark) var(--clay-raised-shadow-light)',
} as const;

export const lifted = {
	'--clay-lifted-shadow-light': '0 2px 6px rgba(22, 22, 40, 0.07)',
	'--clay-lifted-shadow-dark': '0 2px 6px rgba(22, 22, 40, 0.07)',
	'--clay-lifted-rim': 'none',
	'--clay-lifted': 'var(--clay-lifted-shadow-dark) var(--clay-lifted-shadow-light)',
} as const;

export const floating = {
	'--clay-floating-shadow-light': '0 10px 30px rgba(22, 22, 40, 0.1)',
	'--clay-floating-shadow-dark': '0 10px 30px rgba(22, 22, 40, 0.1)',
	'--clay-floating-rim': 'none',
	'--clay-floating': 'var(--clay-floating-shadow-dark) var(--clay-floating-shadow-light)',
} as const;

export const focusRing = {
	'--clay-focus-ring': '0 0 0 3px rgba(79, 70, 229, 0.35)',
} as const;

/* --- App (dark) ------------------------------------------------------------ */

export const appClayFill = { '--clay-fill': '#171726' } as const;

export const appRaised = {
	'--clay-raised-shadow-light': 'inset 0 1px 0 rgba(255, 255, 255, 0.03)',
	'--clay-raised-shadow-dark': '0 1px 2px rgba(0, 0, 0, 0.5)',
	'--clay-raised-rim': 'none',
	'--clay-raised': 'var(--clay-raised-shadow-dark) var(--clay-raised-shadow-light)',
} as const;

export const appLifted = {
	'--clay-lifted-shadow-light': 'inset 0 1px 0 rgba(255, 255, 255, 0.04)',
	'--clay-lifted-shadow-dark': '0 4px 12px rgba(0, 0, 0, 0.55)',
	'--clay-lifted-rim': 'none',
	'--clay-lifted': 'var(--clay-lifted-shadow-dark) var(--clay-lifted-shadow-light)',
} as const;

export const appFloating = {
	'--clay-floating-shadow-light': 'inset 0 1px 0 rgba(255, 255, 255, 0.05)',
	'--clay-floating-shadow-dark': '0 12px 32px rgba(0, 0, 0, 0.6)',
	'--clay-floating-rim': 'none',
	'--clay-floating': 'var(--clay-floating-shadow-dark) var(--clay-floating-shadow-light)',
} as const;

export const appFocusRing = {
	'--clay-focus-ring': '0 0 0 3px rgba(129, 140, 248, 0.45)',
} as const;

/** Flat registry: every clay token name -> its `app.css :root` value. */
export const shadowTokens: Record<string, string> = {
	...clayFill,
	...raised,
	...lifted,
	...floating,
	...focusRing,
};

/** Flat registry: every clay token name -> its `[data-surface='app']` value. */
export const appShadowTokens: Record<string, string> = {
	...appClayFill,
	...appRaised,
	...appLifted,
	...appFloating,
	...appFocusRing,
};

export type ShadowToken = keyof typeof shadowTokens;
export type AppShadowToken = keyof typeof appShadowTokens;
