/**
 * Guard de variables de entorno en tiempo de build.
 *
 * El spec match-ui fija:
 *   "Build falla sin la env var" — el build de producción falla con
 *   error explícito si `PUBLIC_API_URL` no está definida.
 *
 * La verificación fuerte corre en `scripts/check-env.mjs` (prebuild).
 * Esta función queda como guard runtime para debug y diagnóstico.
 */

import { PUBLIC_API_URL, PUBLIC_BACKEND_API_KEY } from '$env/static/public';

export function assertBuildEnv(): void {
	const errors: string[] = [];
	if (!PUBLIC_API_URL || PUBLIC_API_URL.trim() === '') {
		errors.push('PUBLIC_API_URL');
	}

	if (errors.length > 0) {
		const message = `[AsistCV] Faltan variables de entorno requeridas: ${errors.join(', ')}. Definilas antes de ejecutar el build.`;
		console.error(message);
		throw new Error(message);
	}
}

export function getEnvSnapshot(): { apiUrl: string; hasApiKey: boolean } {
	return {
		apiUrl: PUBLIC_API_URL ?? '',
		hasApiKey: Boolean(PUBLIC_BACKEND_API_KEY && PUBLIC_BACKEND_API_KEY.length > 0)
	};
}