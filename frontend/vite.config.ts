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
			}
		]
	}
});
