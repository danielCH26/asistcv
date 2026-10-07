import { fileURLToPath } from 'node:url';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		port: 5173,
		host: true
	},
	test: {
		environment: 'jsdom',
		setupFiles: ['./src/tests/setup.ts'],
		alias: [
			{
				// jsdom es un entorno browser: evitamos que esm-env resuelva a `false`
				// por la condición `development` de vitest ($app/environment.browser).
				find: 'esm-env/browser',
				replacement: fileURLToPath(new URL('./node_modules/esm-env/true.js', import.meta.url))
			},
			{
				// Pin `svelte` root to the REAL runtime. Under vitest's node
				// conditions the package export map resolves `svelte` ->
				// `src/runtime/ssr.js`, whose `onMount` is a silent no-op stub:
				// components under test mounted without ever running onMount,
				// with zero errors. `resolve.conditions: ['browser']` did not
				// survive the sveltekit() plugin's own config, so the alias wins
				// by precedence (same trick as esm-env above).
				find: /^svelte$/,
				replacement: fileURLToPath(
					new URL('./node_modules/svelte/src/runtime/index.js', import.meta.url)
				)
			}
		],
		// Inline svelte into the vitest transform pipeline. Externalized (node
		// CJS) svelte and vite-transformed svelte resolved to two module
		// instances: component `onMount` callbacks registered against one and
		// were flushed by the other — silently. Nothing rendered by onMount,
		// with no error, in ANY component under test. Inlining gives both sides
		// the same ESM instance (see odd/tasks/feat-profile-cv-jd-tabs.md L4).
		// Inline svelte deps into the vitest transform pipeline (module-instance
		// hygiene alongside the `svelte` alias above; see
		// odd/tasks/feat-profile-cv-jd-tabs.md L4).
		server: {
			deps: {
				inline: ['svelte', /^svelte\//, '@sveltejs/kit', /^@sveltejs\//, 'esm-env']
			}
		}
	}
});
