/**
 * Motion tokens — typed registry of durations and easings in `app.css`
 * (Layer 4). app.css is canonical; `tokens.test.ts` enforces parity.
 *
 * Durations are short and the default easing decelerating, which suits a
 * mostly-static layout. Nothing animates by itself; components opt in.
 * The shipped values (80/140/220/340ms) replace the issue's initial
 * 100/200/400 sketch — see `odd/tasks/feat-design-tokens-v1.md` S1.
 */
export const durations = {
	'--duration-instant': '80ms',
	'--duration-fast': '140ms',
	'--duration-base': '220ms',
	'--duration-slow': '340ms',
} as const;

export const easings = {
	'--ease-standard': 'cubic-bezier(0.2, 0, 0, 1)',
	'--ease-out': 'cubic-bezier(0.16, 1, 0.3, 1)',
	'--ease-in': 'cubic-bezier(0.4, 0, 1, 1)',
	'--ease-spring': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
} as const;

/** Flat registry: every motion token name -> its `app.css :root` value. */
export const motionTokens: Record<string, string> = {
	...durations,
	...easings,
};

export type MotionToken = keyof typeof motionTokens;
