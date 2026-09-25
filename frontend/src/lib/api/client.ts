import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import { get } from 'svelte/store';
import { API_BASE } from './base';
import {
	ApiError,
	type AnalysisDetail,
	type AnalysisSummary,
	type AuditAnonymousResult,
	type CVDetail,
	type CVSummary,
	type CVUploadResult,
	type CVStructuredData,
	type Candidate,
	type CandidateListResponse,
	type CandidateMatchResult,
	type ConsentState,
	type MatchAnalysis,
	type MatchRequest,
	type Plan,
	type RankedCandidates,
	type SubscriptionInfo
} from './types';
import {
	refreshIfNeeded,
	refreshTokens,
	session,
	sessionEvent,
	clearPendingAuditToken
} from '$stores/session';

/**
 * Wrapper sobre `fetch` que envía `Authorization: Bearer <access_token>`
 * cuando existe sesión JWT. Ante 401 intenta un refresh silencioso y
 * reintenta una única vez; si el refresh también falla, limpia la sesión
 * y redirige a `/login?reason=expired`.
 *
 * No hay API key de build-time: la autenticación es exclusivamente por
 * sesión JWT (spec match-ui — "Sesión de usuario vía JWT").
 * `PUBLIC_API_URL` es la única env var requerida (guard en
 * `scripts/check-env.mjs`).
 */

const DEFAULT_TIMEOUT_MS = 60_000;

interface RequestOptions {
	/** false para endpoints públicos (auth, audit anónimo). */
	auth?: boolean;
}

async function toApiError(response: Response): Promise<ApiError> {
	const text = await response.text().catch(() => '');
	let code = '';
	try {
		const parsed = JSON.parse(text) as { detail?: unknown };
		if (typeof parsed.detail === 'string') code = parsed.detail;
		else if (parsed.detail && typeof parsed.detail === 'object') {
			code = ((parsed.detail as { code?: string }).code) ?? '';
		}
	} catch {
		// Body no JSON.
	}
	const retryAfterHeader = response.headers.get('Retry-After');
	const retryAfter = retryAfterHeader ? Number.parseInt(retryAfterHeader, 10) : undefined;
	return new ApiError(
		humanizeStatus(response.status, code, text),
		response.status,
		text || response.statusText,
		code || undefined,
		Number.isFinite(retryAfter) ? retryAfter : undefined
	);
}

function humanizeStatus(status: number, code: string, body: string): string {
	if (status === 401) {
		return code === 'TOKEN_REUSED'
			? 'Tu sesión fue invalidada por seguridad. Iniciá sesión nuevamente.'
			: 'Tu sesión expiró. Iniciá sesión nuevamente.';
	}
	if (status === 402) {
		return 'Alcanzaste el límite de tu plan. Actualizá para continuar.';
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

async function request<T>(path: string, init: RequestInit = {}, options: RequestOptions = {}, isRetry = false): Promise<T> {
	const wantsAuth = options.auth !== false;

	if (wantsAuth) {
		await refreshIfNeeded();
	}

	const s = get(session);
	const headers: Record<string, string> = {
		Accept: 'application/json',
		...(init.headers as Record<string, string> | undefined)
	};
	const isFormData = init.body instanceof FormData;
	if (!isFormData && init.body !== undefined && headers['Content-Type'] === undefined) {
		headers['Content-Type'] = 'application/json';
	}
	if (wantsAuth && s) {
		headers.Authorization = `Bearer ${s.accessToken}`;
	}

	const controller = new AbortController();
	const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

	let response: Response;
	try {
		response = await fetch(`${API_BASE}${path}`, {
			...init,
			headers,
			signal: controller.signal
		});
	} catch (err) {
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

	if (response.status === 401) {
		if (wantsAuth && s && !isRetry) {
			const refreshed = await refreshTokens();
			if (refreshed) {
				return request<T>(path, init, options, true);
			}
		}
		if (wantsAuth) {
			const err = await toApiError(response);
			sessionEvent.set(err.code === 'TOKEN_REUSED' ? 'token_reused' : 'expired');
			session.clear();
			if (browser && !window.location.pathname.startsWith('/login')) {
				await goto('/login?reason=expired');
			}
			throw err;
		}
		throw await toApiError(response);
	}

	if (!response.ok) {
		throw await toApiError(response);
	}

	const contentType = response.headers.get('content-type') ?? '';
	if (contentType.includes('application/json')) {
		return (await response.json()) as T;
	}
	return (await response.text()) as unknown as T;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
	const search = new URLSearchParams();
	for (const [key, value] of Object.entries(params)) {
		if (value !== undefined) search.set(key, String(value));
	}
	const qs = search.toString();
	return qs ? `?${qs}` : '';
}

export const apiClient = {
	// === Match / historial ===

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

	// === CVs ===

	uploadCv(file: File): Promise<CVUploadResult> {
		const form = new FormData();
		form.append('file', file);
		return request<CVUploadResult>('/v1/cvs', { method: 'POST', body: form });
	},

	createCvStructured(structured: CVStructuredData): Promise<CVUploadResult> {
		return request<CVUploadResult>('/v1/cvs/structured', {
			method: 'POST',
			body: JSON.stringify({ structured })
		});
	},

	listCvs(): Promise<CVSummary[]> {
		return request<CVSummary[]>('/v1/cvs');
	},

	getCv(id: number): Promise<CVDetail> {
		return request<CVDetail>(`/v1/cvs/${id}`);
	},

	updateCv(id: number, structured: CVStructuredData): Promise<CVDetail> {
		return request<CVDetail>(`/v1/cvs/${id}`, {
			method: 'PATCH',
			body: JSON.stringify({ structured })
		});
	},

	deleteCv(id: number): Promise<void> {
		return request<void>(`/v1/cvs/${id}`, { method: 'DELETE' });
	},

	// === Audit anónimo (público) ===

	auditAnonymous(payload: { jd_text?: string; cv_text?: string; cv_file?: File }): Promise<AuditAnonymousResult> {
		const form = new FormData();
		if (payload.jd_text && payload.jd_text.trim() !== '') {
			form.append('jd_text', payload.jd_text);
		}
		if (payload.cv_file) {
			form.append('cv_file', payload.cv_file);
		} else if (payload.cv_text && payload.cv_text.trim() !== '') {
			form.append('cv_text', payload.cv_text);
		}
		return request<AuditAnonymousResult>('/v1/audit/anonymous', {
			method: 'POST',
			body: form
		});
	},

	captureAuditEmail(auditToken: string, email: string): Promise<{ message: string }> {
		return request<{ message: string }>(
			`/v1/audit/${encodeURIComponent(auditToken)}/capture-email`,
			{ method: 'POST', body: JSON.stringify({ email }) },
			{ auth: false }
		);
	},

	linkAudit(token: string, userId: number): Promise<{ success: boolean; message: string }> {
		return request<{ success: boolean; message: string }>(
			`/v1/audit/${encodeURIComponent(token)}/claim`,
			{ method: 'POST', body: JSON.stringify({ audit_token: token, user_id: userId }) },
			{ auth: false }
		);
	},

	// === Recruiter ===

	listCandidates(page = 1, pageSize = 20): Promise<CandidateListResponse> {
		return request<CandidateListResponse>(`/v1/recruiter/candidates${buildQuery({ page, page_size: pageSize })}`);
	},

	createCandidate(data: { full_name: string; email?: string; phone?: string; notes?: string }, cvFile?: File): Promise<Candidate> {
		const form = new FormData();
		form.append('full_name', data.full_name);
		if (data.email) form.append('email', data.email);
		if (data.phone) form.append('phone', data.phone);
		if (data.notes) form.append('notes', data.notes);
		if (cvFile) form.append('file', cvFile);
		return request<Candidate>('/v1/recruiter/candidates', { method: 'POST', body: form });
	},

	updateCandidate(id: number, data: { full_name?: string; email?: string; phone?: string; notes?: string }): Promise<Candidate> {
		return request<Candidate>(`/v1/recruiter/candidates/${id}`, {
			method: 'PATCH',
			body: JSON.stringify(data)
		});
	},

	deleteCandidate(id: number): Promise<void> {
		return request<void>(`/v1/recruiter/candidates/${id}`, { method: 'DELETE' });
	},

	matchCandidate(id: number, jdText: string): Promise<CandidateMatchResult> {
		return request<CandidateMatchResult>(`/v1/recruiter/candidates/${id}/match`, {
			method: 'POST',
			body: JSON.stringify({ jd_text: jdText })
		});
	},

	rankedCandidates(jdText: string): Promise<RankedCandidates> {
		return request<RankedCandidates>(`/v1/recruiter/candidates/ranked${buildQuery({ jd_text: jdText })}`);
	},

	giveConsent(tosVersion: string): Promise<ConsentState> {
		return request<ConsentState>('/v1/recruiter/consent', {
			method: 'POST',
			body: JSON.stringify({ accept_tos: true, good_faith_declaration: true, tos_version: tosVersion })
		});
	},

	getConsent(): Promise<ConsentState> {
		return request<ConsentState>('/v1/recruiter/consent');
	},

	// === Billing ===

	plans(): Promise<Plan[]> {
		return request<Plan[]>('/v1/billing/plans', {}, { auth: false });
	},

	subscription(): Promise<SubscriptionInfo> {
		return request<SubscriptionInfo>('/v1/billing/subscription');
	},

	checkout(planId: string, paymentMethod: 'card' | 'pse'): Promise<{ checkout_url: string }> {
		return request<{ checkout_url: string }>(
			'/v1/billing/checkout',
			{
				method: 'POST',
				headers: { 'Idempotency-Key': `checkout-${planId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` },
				body: JSON.stringify({ plan_id: planId, payment_method: paymentMethod })
			}
		);
	},

	portal(): Promise<{ portal_url: string }> {
		return request<{ portal_url: string }>('/v1/billing/portal', { method: 'POST' });
	},

	// === Perfil de match (contexto del retrieval) ===

	getProfile(id: number): Promise<{ id: number; name: string }> {
		return request<{ id: number; name: string }>(`/v1/profiles/${id}`);
	},

	createProfile(payload: {
		name: string;
		headline?: string | null;
		experience?: Record<string, unknown>;
		skills?: Record<string, unknown>;
		preferences?: Record<string, unknown>;
	}): Promise<{ id: number; name: string }> {
		return request<{ id: number; name: string }>('/v1/profiles', {
			method: 'POST',
			body: JSON.stringify(payload)
		});
	},

	// === Utilidades ===

	isBrowser() {
		return browser;
	},

	/** Borra el audit token pendiente tras un claim exitoso. */
	clearAuditToken: clearPendingAuditToken
};
