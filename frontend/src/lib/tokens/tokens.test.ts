/**
 * Token-layer consistency tests (S2 of feat-design-tokens-v1).
 *
 * app.css is the canonical home of the CSS cascade; the TS files under
 * `src/lib/tokens/` are the typed registry. This suite fails if the two
 * layers drift apart in either direction:
 *
 *   1. every token exported from TS must exist in app.css `:root` with the
 *      byte-identical value, and
 *   2. the registry must cover the critical token groups the components
 *      actually consume.
 *
 * Values are compared as trimmed strings exactly as written in `:root`, so a
 * "harmless" reformat in either file fails here instead of silently drifting.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { colorTokens } from './colors';
import { typographyTokens } from './typography';
import { spacingTokens } from './spacing';
import { radiusTokens } from './radius';
import { shadowTokens } from './shadow';
import { motionTokens } from './motion';

// vitest always runs with cwd = frontend/ (npm scripts), and `import.meta.url`
// is not a file: URL under the esm-env alias this project aliases in, so the
// CSS file is resolved from the working directory.
const APP_CSS_PATH = resolve(process.cwd(), 'src', 'app.css');

/** Parse `--name: value;` declarations from the first `:root { ... }` block. */
function parseRootVars(css: string): Map<string, string> {
	const start = css.indexOf(':root');
	if (start === -1) throw new Error('app.css has no :root block');
	const open = css.indexOf('{', start);
	// Walk to the matching closing brace (blocks are not nested in :root).
	let depth = 0;
	let end = open;
	for (let i = open; i < css.length; i++) {
		if (css[i] === '{') depth++;
		if (css[i] === '}') {
			depth--;
			if (depth === 0) {
				end = i;
				break;
			}
		}
	}
	const body = css.slice(open + 1, end);
	const vars = new Map<string, string>();
	const decl = /(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g;
	for (const match of body.matchAll(decl)) {
		vars.set(match[1], match[2].trim());
	}
	return vars;
}

function loadRootVars(): Map<string, string> {
	return parseRootVars(readFileSync(APP_CSS_PATH, 'utf8'));
}

const registries: ReadonlyArray<readonly [string, Record<string, string>]> = [
	['colors', colorTokens],
	['typography', typographyTokens],
	['spacing', spacingTokens],
	['radius', radiusTokens],
	['shadow', shadowTokens],
	['motion', motionTokens],
];

describe('token registry ↔ app.css parity', () => {
	it('app.css :root exists and declares a substantial token set', () => {
		const vars = loadRootVars();
		expect(vars.size).toBeGreaterThanOrEqual(100);
	});

	for (const [name, registry] of registries) {
		it(`${name} registry is non-empty`, () => {
			expect(Object.keys(registry).length).toBeGreaterThan(0);
		});

		it(`every ${name} token exists in app.css :root with the byte-identical value`, () => {
			const vars = loadRootVars();
			const problems: string[] = [];
			for (const [token, value] of Object.entries(registry)) {
				const cssValue = vars.get(token);
				if (cssValue === undefined) {
					problems.push(`  - ${token}: missing in app.css :root`);
				} else if (cssValue !== value) {
					problems.push(`  - ${token}: TS "${value}" != CSS "${cssValue}"`);
				}
			}
			expect(problems, `Drift between TS registry and app.css:\n${problems.join('\n')}`).toEqual([]);
		});
	}

	it('registry covers the critical tokens components consume', () => {
		const critical: string[] = [
			// palette (S3 pairs are built on these)
			'--color-canvas',
			'--color-surface',
			'--color-ink',
			'--color-ink-muted',
			'--color-action',
			'--color-on-action',
			'--color-warning',
			'--color-warning-muted',
			// score fills (Layer 0, mode-invariant)
			'--score-low',
			'--score-mid',
			'--score-high',
			'--color-on-score-fill',
			// structure
			'--space-2',
			'--space-4',
			'--radius-card',
			'--radius-pill',
			'--text-md',
			'--text-2xl',
			'--font-sans',
			// clay + motion
			'--clay-raised',
			'--clay-focus-ring',
			'--duration-fast',
			'--ease-standard',
		];
		const all = new Map(registries.flatMap(([, r]) => Object.entries(r)));
		const missing = critical.filter((token) => !all.has(token));
		expect(missing, `Registry is missing critical tokens: ${missing.join(', ')}`).toEqual([]);
	});
});
