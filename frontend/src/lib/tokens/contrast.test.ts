/**
 * WCAG 2.1 contrast checks for the AsistCV palette (S3 of feat-design-tokens-v1
 * + S1 of feat-palette-wcag-coverage).
 *
 * `app.css` documented its text/surface pairs as "measured >= 4.5:1" for a year
 * while admitting the checking script was never committed. This file is
 * that missing check, run against the TS registry on every `vitest` pass.
 *
 * Two layers:
 *
 * 1. **Documented pairs** (app.css comments + colors.ts comments) — pinned
 *    ratios so the comments cannot silently rot. AA threshold asserted for
 *    every pair.
 *
 * 2. **Coverage expansion** (issue #57 T1) — every reasonable text/bg
 *    combination of the shipped 24 tokens is now asserted. Text pairs need
 *    >= 4.5:1; UI/border pairs need >= 3:1 (WCAG 1.4.11). The body-text pair
 *    (ink on canvas) is also asserted for AAA (>= 7:1).
 *
 * Contract notes (issues #57 + the audit C6 follow-up):
 * - "Text on a status fill" = the *regular* ``--color-X`` on ``--color-X``,
 *   not ``--color-on-X`` on ``--color-X-muted`` (the muted tones are
 *   decorative tints intended for "regular text on pale background").
 * - ``--color-line`` is a decorative hairline (1.18:1–1.23:1 on surfaces)
 *   and is NOT asserted against 1.4.11 — that's a decorative element.
 *   ``--color-line-strong`` is the essential boundary (4.55:1+) and IS
 *   asserted at 3:1.
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
const AA_NON_TEXT = 3.0; // WCAG 1.4.11 for essential UI / graphical objects
const AAA_NORMAL_TEXT = 7.0;

/**
 * Documented pairs (pinned ratios in colors.ts / app.css comments). When
 * non-null, the third element asserts the ratio is within +/- 0.05 of the
 * documented value so the comments cannot silently rot.
 */
const DOCUMENTED_PAIRS: ReadonlyArray<readonly [string, string, number | null]> = [
	// Layer 0 (mode-invariant): score fills with white label.
	['--color-on-score-fill', '--score-low', 4.83],
	['--color-on-score-fill', '--score-mid', 7.09],
	['--color-on-score-fill', '--score-high', 5.48],
	// Layer 3: ink on surfaces and status (existing).
	['--color-ink', '--color-canvas', null],
	['--color-ink', '--color-surface', null],
	['--color-ink-strong', '--color-canvas', null],
	['--color-ink-muted', '--color-surface', null],
	['--color-on-action', '--color-action', null],
	['--color-warning', '--color-warning-muted', null],
	['--color-warning', '--color-canvas', null],
	['--color-ink', '--color-action-muted', null],
];

/**
 * Text-on-background pairs the product ships today. The closing of #57 T1 is
 * to assert >= 4.5:1 for every one of them. New pairs added by the next
 * token change should be appended here.
 *
 * IMPORTANT contract: the muted status siblings (``--color-X-muted``) are
 * pale tints intended to host the REGULAR text token (``--color-X``), not the
 * on-color. Putting the white on-color over a muted tint drops contrast to
 * 1.0x:1 — that is a contract bug, not a token bug, and is tracked
 * separately (T2 follow-up).
 */
const TEXT_PAIRS: ReadonlyArray<readonly [string, string]> = [
	// ink family on surfaces
	['--color-ink', '--color-canvas'],
	['--color-ink', '--color-surface'],
	['--color-ink', '--color-surface-alt'],
	['--color-ink-strong', '--color-canvas'],
	['--color-ink-strong', '--color-surface'],
	['--color-ink-strong', '--color-surface-alt'],
	['--color-ink-muted', '--color-canvas'],
	['--color-ink-muted', '--color-surface'],
	['--color-ink-muted', '--color-surface-alt'],
	// status: regular text token on the pale muted tint (chip body).
	// The muted siblings are pale backgrounds; the text that lives on them
	// is the REGULAR status color (dark enough), never the white on-color.
	['--color-action', '--color-action-muted'],
	['--color-success', '--color-success-muted'],
	['--color-warning', '--color-warning-muted'],
	['--color-danger', '--color-danger-muted'],
	['--color-info', '--color-info-muted'],
	// on-X white on the FILL (the "white chip on dark action" pattern)
	['--color-on-action', '--color-action'],
	['--color-on-success', '--color-success'],
	['--color-on-warning', '--color-warning'],
	['--color-on-danger', '--color-danger'],
	['--color-on-info', '--color-info'],
	// score inks as LABEL text on surfaces (EnergyBadge, StrengthsGapsList)
	['--score-low-ink', '--color-surface'],
	['--score-mid-ink', '--color-surface'],
	['--score-high-ink', '--color-surface'],
];

/**
 * UI / non-text contrast (WCAG 1.4.11 — 3:1 for focus rings, form-field
 * boundaries, and graphical objects). The sober palette's ``--color-line`` is
 * a decorative hairline (1.18:1–1.23:1 on surfaces) — WCAG 1.4.11 only
 * applies to *essential* UI, so it is exempt from this assertion. The
 * 1:1 chip-level readability is satisfied by the colour-difference cue.
 * ``--color-line-strong`` is the essential boundary (4.55:1+) and is
 * held to 3:1.
 */
const UI_PAIRS: ReadonlyArray<readonly [string, string]> = [
	['--color-line-strong', '--color-canvas'],
	['--color-line-strong', '--color-surface'],
];

describe('WCAG 2.1 AA contrast (light scheme, from TS registry)', () => {
	it.each(DOCUMENTED_PAIRS)('documented %s on %s clears AA (4.5:1)', (fg, bg) => {
		const ratio = contrastRatio(token(fg), token(bg));
		expect(ratio, `${fg} on ${bg} measures ${ratio}:1`).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
	});

	it.each(TEXT_PAIRS)('text %s on %s clears AA (4.5:1)', (fg, bg) => {
		const ratio = contrastRatio(token(fg), token(bg));
		expect(ratio, `${fg} on ${bg} measures ${ratio}:1`).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
	});

	it.each(UI_PAIRS)('essential UI %s on %s clears 1.4.11 (3:1)', (fg, bg) => {
		const ratio = contrastRatio(token(fg), token(bg));
		expect(ratio, `${fg} on ${bg} measures ${ratio}:1`).toBeGreaterThanOrEqual(AA_NON_TEXT);
	});

	it('body-text pair (ink on canvas) clears AAA (7:1)', () => {
		// The sober palette's --color-ink (#1f2937) on --color-canvas (#f8fafc)
		// measures ~14.6:1 — well above the AAA 7:1 threshold for normal text.
		// Pinning this prevents the ink from being lightened by accident.
		const ratio = contrastRatio(token('--color-ink'), token('--color-canvas'));
		expect(ratio, `ink on canvas measures ${ratio}:1`).toBeGreaterThanOrEqual(AAA_NORMAL_TEXT);
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
