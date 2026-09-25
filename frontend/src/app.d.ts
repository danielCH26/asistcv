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
declare module '$env/static/public' {
	export const PUBLIC_API_URL: string;
}

export {};