/**
 * Spacing tokens — typed registry of the 4px-grid scale in `app.css`
 * (Layer 2). app.css is canonical; `tokens.test.ts` enforces parity.
 *
 * The grid doubles then widens, so every gap is a multiple of the same base
 * step (0.25rem). A value that is not on this scale is a bug, not a style.
 */
export const spacing = {
	'--space-0': '0',
	'--space-1': '0.25rem',
	'--space-2': '0.5rem',
	'--space-3': '0.75rem',
	'--space-4': '1rem',
	'--space-5': '1.5rem',
	'--space-6': '2rem',
	'--space-7': '3rem',
	'--space-8': '4rem',
	'--space-9': '6rem',
	'--space-10': '8rem',
} as const;

/**
 * Recorded responsive constants. NOTE (from app.css): `--breakpoint-sm` is a
 * RECORDED value, not a consumable one — `var()` inside an `@media` condition
 * silently does nothing, so media preludes keep the literal `640px` on
 * purpose. `--layout-content-max` is a normal declaration value and works in
 * `max-width: var(--layout-content-max)`.
 */
export const responsive = {
	'--breakpoint-sm': '640px',
	'--layout-content-max': '880px',
} as const;

/** Flat registry: every spacing token name -> its `app.css :root` value. */
export const spacingTokens: Record<string, string> = {
	...spacing,
	...responsive,
};

export type SpacingToken = keyof typeof spacingTokens;
