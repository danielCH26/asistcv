/**
 * Typography tokens — typed registry of the Swiss type system in `app.css`
 * (Layer 2). app.css is canonical; `tokens.test.ts` enforces parity.
 *
 * Type tightens as it grows: a falling line-height paired with negative
 * tracking on display sizes is the strongest Swiss signal. Positive tracking
 * is reserved for small caps labels.
 */
export const typeScale = {
	'--text-2xs': '0.6875rem',
	'--text-xs': '0.75rem',
	'--text-sm': '0.875rem',
	'--text-md': '1rem',
	'--text-lg': '1.125rem',
	'--text-xl': '1.25rem',
	'--text-2xl': '1.5rem',
	'--text-3xl': '1.875rem',
	'--text-4xl': '2.25rem',
	'--text-5xl': '3rem',
	'--text-6xl': '3.75rem',
} as const;

/** Line heights: tighter the larger the size. */
export const leading = {
	'--leading-tight': '1.1',
	'--leading-snug': '1.25',
	'--leading-normal': '1.5',
	'--leading-relaxed': '1.65',
} as const;

/** Letter spacing: negative on display, positive only on small caps labels. */
export const tracking = {
	'--tracking-tighter': '-0.03em',
	'--tracking-tight': '-0.02em',
	'--tracking-snug': '-0.01em',
	'--tracking-normal': '0',
	'--tracking-wide': '0.04em',
	'--tracking-widest': '0.08em',
} as const;

/** Inter is the stack the app already shipped — exposed, not replaced. */
export const fontFamilies = {
	'--font-sans': `'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif`,
	'--font-mono': `ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace`,
} as const;

/** Flat registry: every typography token name -> its `app.css :root` value. */
export const typographyTokens: Record<string, string> = {
	...typeScale,
	...leading,
	...tracking,
	...fontFamilies,
};

export type TypographyToken = keyof typeof typographyTokens;
