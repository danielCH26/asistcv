import { browser } from '$app/environment';
import { PUBLIC_API_URL, PUBLIC_BACKEND_API_KEY } from '$env/static/public';
import { ApiError, type AnalysisDetail, type AnalysisSummary, type MatchAnalysis, type MatchRequest } from './types';

/**
 * Wrapper sobre `fetch` que pega `Authorization: Bearer <key>` cuando
 * la env var `PUBLIC_BACKEND_API_KEY` está definida. En modo abierto
 * (env vacía), no envía el header y el backend debe permitirlo.
 *
 * El build de producción falla con error explícito si `PUBLIC_API_URL`
 * no está definida (ver `scripts/check-env.mjs`).
 */

const DEFAULT_TIMEOUT_MS = 60_000;

function authHeaders(): HeadersInit {
	if (typeof PUBLIC_BACKEND_API_KEY === 'string' && PUBLIC_BACKEND_API_KEY.length > 0) {
		return { Authorization: `Bearer ${PUBLIC_BACKEND_API_KEY}` };
	}
	return {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
	if (!PUBLIC_API_URL) {
		throw new ApiError('PUBLIC_API_URL no está definida', 0, 'missing-env');
	}
	const base = PUBLIC_API_URL;

	const url = `${base.replace(/\/$/, '')}${path}`;
	const headers: HeadersInit = {
		'Content-Type': 'application/json',
		Accept: 'application/json',
		...authHeaders(),
		...(init.headers as Record<string, string> | undefined)
	};

	const controller = new AbortController();
	const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

	try {
		const response = await fetch(url, {
			...init,
			headers,
			signal: controller.signal
		});

		if (!response.ok) {
			const text = await response.text().catch(() => '');
			throw new ApiError(
				humanizeStatus(response.status, text),
				response.status,
				text || response.statusText
			);
		}

		const contentType = response.headers.get('content-type') ?? '';
		if (contentType.includes('application/json')) {
			return (await response.json()) as T;
		}
		return (await response.text()) as unknown as T;
	} catch (err) {
		if (err instanceof ApiError) {
			throw err;
		}
		if (err instanceof DOMException && err.name === 'AbortError') {
			throw new ApiError(
				'La solicitud excedió el tiempo de espera (60 s). El servidor puede estar en cold start; reintentá.',
				0,
				'timeout'
			);
		}
		const message = err instanceof Error ? err.message : 'Error desconocido';
		throw new ApiError(`Error de red: ${message}`, 0, 'network');
	} finally {
		clearTimeout(timeout);
	}
}

function humanizeStatus(status: number, body: string): string {
	if (status === 401) {
		return 'Credenciales inválidas o ausentes. Verificá PUBLIC_BACKEND_API_KEY en el build.';
	}
	if (status === 404) {
		return 'Recurso no encontrado.';
	}
	if (status === 422) {
		return body || 'Datos inválidos.';
	}
	if (status === 429) {
		return 'Rate limit alcanzado. Esperá unos segundos y reintentá.';
	}
	if (status >= 500) {
		return 'Error del servidor. Reintentá en unos minutos.';
	}
	return body || `Error HTTP ${status}`;
}

export const apiClient = {
	match(payload: MatchRequest): Promise<MatchAnalysis> {
		return request<MatchAnalysis>('/v1/match', {
			method: 'POST',
			body: JSON.stringify(payload)
		});
	},

	listAnalyses(params: { limit?: number; offset?: number; profileId?: number } = {}): Promise<AnalysisSummary[]> {
		const search = new URLSearchParams();
		if (params.limit !== undefined) search.set('limit', String(params.limit));
		if (params.offset !== undefined) search.set('offset', String(params.offset));
		if (params.profileId !== undefined) search.set('profile_id', String(params.profileId));
		const qs = search.toString();
		return request<AnalysisSummary[]>(`/v1/analyses${qs ? `?${qs}` : ''}`);
	},

	getAnalysis(id: number): Promise<AnalysisDetail> {
		return request<AnalysisDetail>(`/v1/analyses/${id}`);
	},

	isBrowser() {
		return browser;
	}
};