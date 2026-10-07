/**
 * Shadow tokens — typed registry of the clay elevation system in `app.css`
 * (Layer 1). app.css is canonical; `tokens.test.ts` enforces parity.
 *
 * Named by depth meaning ("raised" < "lifted" < "floating"), each depth
 * composing three parts: a light shadow, a dark shadow and an inner rim
 * highlight. Composite values are verbatim `var()` chains — copying them as
 * anything else would break byte parity with `:root`.
 *
 * Light surfaces are LIT, so the light shadow does real work (the convex
 * bounce). Offsets stay small and blurs stay wide on purpose: hard offsets
 * and tight blurs are what turn clay into 2000s Web 2.0.
 */
export const clayFill = { '--clay-fill': '#eef1f6' } as const;

export const raised = {
	'--clay-raised-shadow-light': '-3px -3px 7px rgba(255, 255, 255, 0.9)',
	'--clay-raised-shadow-dark': '3px 3px 7px rgba(163, 177, 198, 0.38)',
	'--clay-raised-rim': 'inset 1.5px 1.5px 2px rgba(255, 255, 255, 0.75)',
	'--clay-raised':
		'var(--clay-raised-shadow-dark) var(--clay-raised-shadow-light) var(--clay-raised-rim)',
} as const;

export const lifted = {
	'--clay-lifted-shadow-light': '-5px -5px 11px rgba(255, 255, 255, 0.92)',
	'--clay-lifted-shadow-dark': '5px 5px 11px rgba(163, 177, 198, 0.44)',
	'--clay-lifted-rim': 'inset 1.5px 1.5px 2.5px rgba(255, 255, 255, 0.8)',
	'--clay-lifted':
		'var(--clay-lifted-shadow-dark) var(--clay-lifted-shadow-light) var(--clay-lifted-rim)',
} as const;

export const floating = {
	'--clay-floating-shadow-light': '-8px -8px 18px rgba(255, 255, 255, 0.95)',
	'--clay-floating-shadow-dark': '8px 8px 18px rgba(148, 163, 184, 0.48)',
	'--clay-floating-rim': 'inset 2px 2px 3px rgba(255, 255, 255, 0.85)',
	'--clay-floating':
		'var(--clay-floating-shadow-dark) var(--clay-floating-shadow-light) var(--clay-floating-rim)',
} as const;

export const focusRing = {
	'--clay-focus-ring': '0 0 0 3px rgba(3, 105, 161, 0.45)',
} as const;

/** Flat registry: every clay token name -> its `app.css :root` value. */
export const shadowTokens: Record<string, string> = {
	...clayFill,
	...raised,
	...lifted,
	...floating,
	...focusRing,
};

export type ShadowToken = keyof typeof shadowTokens;
