/**
 * API base URL. Single source of truth for both the API client and the
 * session store (which does its own token calls to avoid circular imports).
 *
 * `PUBLIC_API_URL` es requerida en builds de producción (guard en
 * `scripts/check-env.mjs`); en dev cae al backend local.
 */

const DEV_FALLBACK = 'http://localhost:8000';

function resolveBase(): string {
	const raw = import.meta.env.PUBLIC_API_URL ?? '';
	const trimmed = raw.trim();
	if (trimmed === '') return DEV_FALLBACK;
	return trimmed.replace(/\/+$/, '');
}

export const API_BASE = resolveBase();
