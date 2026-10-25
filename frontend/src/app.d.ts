// See https://kit.svelte.dev/docs/types#app
declare global {
	namespace App {
		interface Error {
			message: string;
			code?: string;
		}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}
}

// Declarar las env vars públicas para que svelte-check no falle cuando
// no existe `.env` (por ejemplo, en CI antes de cargar secretos).
// SvelteKit reescribe este módulo con los tipos reales cuando `.env` está
// presente al ejecutar `svelte-kit sync`.
//
// `PUBLIC_CLERK_PUBLISHABLE_KEY` va aquí por la misma razón: el módulo
// virtual `$env/static/public` sólo declara las variables que existen en el
// entorno, así que sin esta declaración `import { PUBLIC_CLERK_PUBLISHABLE_KEY }
// from '$env/static/public'` rompe el typecheck en CI y en cualquier clone
// sin `.env`. El build sigue SIN esta variable: `scripts/check-env.mjs` lo
// detiene antes con un mensaje que dice qué falta.
declare module '$env/static/public' {
	export const PUBLIC_API_URL: string;
	export const PUBLIC_CLERK_PUBLISHABLE_KEY: string;
}

export {};