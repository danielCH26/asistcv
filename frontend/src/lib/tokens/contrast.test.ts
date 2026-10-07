/**
 * WCAG 2.1 AA contrast checks (S3 of feat-design-tokens-v1).
 *
 * `app.css` documented its text/surface pairs as "measured >= 4.5:1" for a
 * year while admitting the checking script was never committed. This file is
 * that missing check, run against the TS registry on every `vitest` pass.
 *
 * Ratios are computed with the WCAG 2.1 relative-luminance formula. The
 * headline score-fill ratios are additionally pinned to the values documented
 * in `colors.ts` (+/- 0.05) so the comments cannot silently rot.
 */
import { describe, expect, it } from 'vitest';

import { colorTokens } from './colors';

/** Parse `#rgb` / `#rrggbb` into an [r, g, b] triplet of 0-255 integers. */
function parseHex(hex: string): [number, number, number] {
	const raw = hex.replace(/^#/, '');
	const full =
		raw.length === 3
			? raw
					.split('')
					.map((c) => c + c)
					.join('')
			: raw;
	if (full.length !== 6) throw new Error(`Unsupported colour format: ${hex}`);
	return [
		Number.parseInt(full.slice(0, 2), 16),
		Number.parseInt(full.slice(2, 4), 16),
		Number.parseInt(full.slice(4, 6), 16),
	];
}

/** WCAG 2.1 relative luminance of an sRGB channel triplet. */
function relativeLuminance([r, g, b]: [number, number, number]): number {
	const lin = (channel: number) => {
		const srgb = channel / 255;
		return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
	};
	return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** WCAG contrast ratio between two hex colours, rounded to 2 decimals. */
export function contrastRatio(fgHex: string, bgHex: string): number {
	const l1 = relativeLuminance(parseHex(fgHex));
	const l2 = relativeLuminance(parseHex(bgHex));
	const lighter = Math.max(l1, l2);
	const darker = Math.min(l1, l2);
	return Math.round(((lighter + 0.05) / (darker + 0.05)) * 100) / 100;
}

function token(name: string): string {
	const value = colorTokens[name];
	if (!value) throw new Error(`colorTokens has no entry for ${name}`);
	if (!value.startsWith('#')) throw new Error(`${name} is not a plain hex value: ${value}`);
	return value;
}

const AA_NORMAL_TEXT = 4.5;

/**
 * Every pair the product renders as normal-size text (or that app.css already
 * documents as measured). Each entry: [fg token, bg token, documented ratio
 * or null when app.css documents only the threshold].
 */
const DOCUMENTED_PAIRS: ReadonlyArray<readonly [string, string, number | null]> = [
	['--color-on-score-fill', '--score-low', 4.83],
	['--color-on-score-fill', '--score-mid', 7.09],
	['--color-on-score-fill', '--score-high', 5.48],
	['--color-ink', '--color-canvas', null],
	['--color-ink', '--color-surface', null],
	['--color-ink-strong', '--color-canvas', null],
	['--color-ink-muted', '--color-surface', null],
	['--color-on-action', '--color-action', null],
	['--color-warning', '--color-warning-muted', null],
	['--color-warning', '--color-canvas', null],
	['--color-ink', '--color-action-muted', null],
];

describe('WCAG 2.1 AA contrast (light scheme, from TS registry)', () => {
	it.each(DOCUMENTED_PAIRS)('%s on %s clears AA (4.5:1)', (fg, bg) => {
		const ratio = contrastRatio(token(fg), token(bg));
		expect(ratio, `${fg} on ${bg} measures ${ratio}:1`).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
	});

	it('headline score-fill ratios match the documented values', () => {
		// Pins the comments in colors.ts / app.css so they cannot rot.
		const cases: ReadonlyArray<readonly [string, number]> = [
			['--score-low', 4.83],
			['--score-mid', 7.09],
			['--score-high', 5.48],
		];
		for (const [fill, documented] of cases) {
			const ratio = contrastRatio(token('--color-on-score-fill'), token(fill));
			expect(
				Math.abs(ratio - documented),
				`${fill}: measured ${ratio}:1, documented ${documented}:1 — update colors.ts/app.css comments together with any colour change`,
			).toBeLessThanOrEqual(0.05);
		}
	});

	it('the WCAG ratio helper itself is correct (sanity)', () => {
		// Black on white is exactly 21:1; white on white is 1:1.
		expect(contrastRatio('#000000', '#ffffff')).toBe(21);
		expect(contrastRatio('#ffffff', '#ffffff')).toBe(1);
	});
});
