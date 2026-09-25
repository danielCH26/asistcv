/**
 * API base URL. Single source of truth for both the API client and the
 * session store (which does its own token calls to avoid circular imports).
 *
 * `PUBLIC_API_URL` es requerida en builds de producción (guard en
 * `scripts/check-env.mjs`); en dev cae al backend local.
 *
 * NOTE: usamos `$env/static/public` (patrón idiomático SvelteKit) en lugar
 * de `import.meta.env.PUBLIC_API_URL` (patrón Vite), porque Vite por default
 * solo expone al cliente vars con prefijo `VITE_`. Con SvelteKit,
 * `$env/static/public` inlinea el valor al bundle del cliente en build time.
 */

import { PUBLIC_API_URL } from '$env/static/public';

const DEV_FALLBACK = 'http://localhost:8000';

function resolveBase(): string {
	const raw = (PUBLIC_API_URL ?? '').trim();
	if (raw === '') return DEV_FALLBACK;
	return raw.replace(/\/+$/, '');
}

export const API_BASE = resolveBase();
