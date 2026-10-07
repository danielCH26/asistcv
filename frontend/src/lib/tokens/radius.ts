/**
 * Shape tokens — typed registry of the radius and border-width scales in
 * `app.css` (Layer 2). app.css is canonical; `tokens.test.ts` enforces parity.
 *
 * Radii are named by what the shape IS, not by its number. The four pixel
 * steps (6/8/10/12) are a monotone scale; pill and circle are shape kinds,
 * not points on that scale. There is deliberately no "none" radius: places
 * that want no rounding say `border: none`.
 */
export const radius = {
	'--radius-control': '6px', // input, small button
	'--radius-card': '8px', // default button, list row, inline card
	'--radius-card-lg': '10px', // larger card, block on the canvas
	'--radius-panel': '12px', // the page's main panel
	'--radius-pill': '999px', // badge, status chip
	'--radius-circle': '50%', // spinner, avatar
} as const;

/**
 * Border widths, written as longhands in app.css so a component can change
 * width without restating style and colour.
 */
export const borderWidths = {
	'--border-width': '1px', // hairline: the default boundary
	'--border-width-thick': '2px', // emphasised boundary, spinnable arc
	'--border-width-heavy': '3px', // the arc of a large spinner
} as const;

/** Flat registry: every shape token name -> its `app.css :root` value. */
export const radiusTokens: Record<string, string> = {
	...radius,
	...borderWidths,
};

export type RadiusToken = keyof typeof radiusTokens;
