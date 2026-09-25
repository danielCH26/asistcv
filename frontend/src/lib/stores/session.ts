import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import { derived, get, writable, type Readable } from 'svelte/store';
import { ApiError, type Role, type SessionUser, type SignUpPayload, type TokenResponse } from '$api/types';
import { API_BASE } from '$api/base';

/**
 * Sesión de usuario (JWT dual access + refresh).
 *
 * Persistencia en `localStorage` (clave `asistcv.session`): la app es un
 * SPA estático single-device, según design §8.1. El refresh proactivo
 * renueva el access token cuando le falta menos de 60 s para expirar.
 */

const STORAGE_KEY = 'asistcv.session';
const ONBOARDING_KEY = 'asistcv.onboarding';
const AUDIT_TOKEN_KEY = 'asistcv.audit_token';
const REFRESH_THRESHOLD_MS = 60_000;
const ACCESS_TTL_FALLBACK_MS = 15 * 60 * 1000;

export interface Session {
	accessToken: string;
	refreshToken: string;
	user: SessionUser;
	/** ms epoch en que expira el access token. */
	expiresAt: number;
}

function decodeJwtExpMs(jwt: string): number {
	try {
		const payload = jwt.split('.')[1];
		if (!payload) return Date.now() + ACCESS_TTL_FALLBACK_MS;
		const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
		const json = decodeURIComponent(
			atob(normalized)
				.split('')
				.map((c) => `%${`00${c.charCodeAt(0).toString(16)}`.slice(-2)}`)
				.join('')
		);
		const claims = JSON.parse(json) as { exp?: number };
		if (typeof claims.exp === 'number' && claims.exp > 0) return claims.exp * 1000;
	} catch {
		// Token opaco o malformado: usamos el TTL default.
	}
	return Date.now() + ACCESS_TTL_FALLBACK_MS;
}

function loadPersisted(): Session | null {
	if (!browser) return null;
	const raw = localStorage.getItem(STORAGE_KEY);
	if (!raw) return null;
	try {
		const parsed = JSON.parse(raw) as Session;
		if (!parsed.accessToken || !parsed.refreshToken || !parsed.user) return null;
		return parsed;
	} catch {
		return null;
	}
}

function createSessionStore() {
	const store = writable<Session | null>(loadPersisted());

	store.subscribe((value) => {
		if (!browser) return;
		if (value === null) {
			localStorage.removeItem(STORAGE_KEY);
		} else {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
		}
	});

	return {
		subscribe: store.subscribe,
		set(value: Session) {
			store.set(value);
		},
		clear() {
			store.set(null);
		}
	};
}

export const session = createSessionStore();

export const isAuthenticated = derived(session, ($s) => $s !== null);
export const isRecruiter = derived(session, ($s) => $s?.user.role === 'recruiter');
export const currentRole: Readable<Role | null> = derived(session, ($s) => $s?.user.role ?? null);

/** Evento de sesión para banners (login page). */
export const sessionEvent = writable<'expired' | 'token_reused' | null>(null);

async function parseError(res: Response): Promise<ApiError> {
	const text = await res.text().catch(() => '');
	let code = '';
	let message = text;
	try {
		const parsed = JSON.parse(text) as { detail?: unknown };
		if (typeof parsed.detail === 'string') {
			message = parsed.detail;
			code = parsed.detail;
		} else if (parsed.detail && typeof parsed.detail === 'object') {
			const d = parsed.detail as { code?: string; message?: string };
			code = d.code ?? '';
			message = d.message ?? JSON.stringify(parsed.detail);
		}
	} catch {
		// body no JSON: usamos el texto crudo.
	}
	return new ApiError(message || `Error HTTP ${res.status}`, res.status, text || res.statusText, code);
}

async function fetchMe(accessToken: string): Promise<SessionUser> {
	const res = await fetch(`${API_BASE}/v1/users/me`, {
		headers: { Authorization: `Bearer ${accessToken}`, Accept: 'application/json' }
	});
	if (!res.ok) {
		throw await parseError(res);
	}
	return (await res.json()) as SessionUser;
}

function toSession(tokens: TokenResponse, user: SessionUser): Session {
	return {
		accessToken: tokens.access_token,
		refreshToken: tokens.refresh_token,
		user,
		expiresAt: decodeJwtExpMs(tokens.access_token)
	};
}

let refreshInflight: Promise<boolean> | null = null;

/**
 * Refresh silencioso, single-flight: llamadas concurrentes comparten
 * la misma promesa para no rotar el refresh token dos veces.
 */
export function refreshTokens(): Promise<boolean> {
	if (!refreshInflight) {
		refreshInflight = doRefresh().finally(() => {
			refreshInflight = null;
		});
	}
	return refreshInflight;
}

async function doRefresh(): Promise<boolean> {
	const s = get(session);
	if (!s) return false;
	try {
		const res = await fetch(`${API_BASE}/v1/auth/refresh`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
			body: JSON.stringify({ refresh_token: s.refreshToken })
		});
		if (!res.ok) {
			if (res.status === 401) {
				const err = await parseError(res);
				sessionEvent.set(err.code === 'TOKEN_REUSED' ? 'token_reused' : 'expired');
				session.clear();
			}
			return false;
		}
		const tokens = (await res.json()) as TokenResponse;
		session.set(toSession(tokens, s.user));
		return true;
	} catch {
		return false;
	}
}

/** Refresca si el access token expira en <60 s. Devuelve true si hay sesión utilizable. */
export async function refreshIfNeeded(): Promise<boolean> {
	const s = get(session);
	if (!s) return false;
	if (s.expiresAt - Date.now() > REFRESH_THRESHOLD_MS) return true;
	return refreshTokens();
}

export async function login(email: string, password: string): Promise<SessionUser> {
	const res = await fetch(`${API_BASE}/v1/auth/login`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
		body: JSON.stringify({ email, password })
	});
	if (!res.ok) throw await parseError(res);
	const tokens = (await res.json()) as TokenResponse;
	const user = await fetchMe(tokens.access_token);
	session.set(toSession(tokens, user));
	return user;
}

export async function signup(payload: SignUpPayload): Promise<SessionUser> {
	const res = await fetch(`${API_BASE}/v1/auth/register`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
		body: JSON.stringify(payload)
	});
	if (!res.ok) throw await parseError(res);
	const tokens = (await res.json()) as TokenResponse;
	const user = await fetchMe(tokens.access_token);
	session.set(toSession(tokens, user));
	await claimPendingAudit(user.id);
	return user;
}

/** Audit token pendiente de vincular (funnel anónimo → cuenta). */
export function getPendingAuditToken(): string | null {
	if (!browser) return null;
	return localStorage.getItem(AUDIT_TOKEN_KEY);
}

export function setPendingAuditToken(token: string): void {
	if (browser) localStorage.setItem(AUDIT_TOKEN_KEY, token);
}

export function clearPendingAuditToken(): void {
	if (browser) localStorage.removeItem(AUDIT_TOKEN_KEY);
}

async function claimPendingAudit(userId: number): Promise<void> {
	const token = getPendingAuditToken();
	if (!token) return;
	try {
		const res = await fetch(`${API_BASE}/v1/audit/${encodeURIComponent(token)}/claim`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
			body: JSON.stringify({ audit_token: token, user_id: userId })
		});
		if (res.ok) clearPendingAuditToken();
	} catch {
		// Claim best-effort: no bloquea el registro.
	}
}

export async function logout(): Promise<void> {
	const s = get(session);
	if (s) {
		try {
			await fetch(`${API_BASE}/v1/auth/logout`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${s.accessToken}` },
				body: JSON.stringify({ refresh_token: s.refreshToken })
			});
		} catch {
			// Logout best-effort: la sesión local se limpia igual.
		}
	}
	session.clear();
	sessionEvent.set(null);
	if (browser) await goto('/');
}

// === Onboarding wizard (3 pasos, design §8.4) ===

export function startOnboarding(): void {
	if (browser) localStorage.setItem(ONBOARDING_KEY, '1');
}

export function isOnboarding(): boolean {
	if (!browser) return false;
	return localStorage.getItem(ONBOARDING_KEY) === '1';
}

export function completeOnboarding(): void {
	if (browser) localStorage.removeItem(ONBOARDING_KEY);
}

// === Guards de ruta (ssr=false: todo corre client-side) ===

export async function requireSession(): Promise<boolean> {
	if (!browser) return false;
	const s = get(session);
	if (!s) {
		await goto('/login?reason=required');
		return false;
	}
	await refreshIfNeeded();
	return get(session) !== null;
}

export async function requireRole(role: Role): Promise<boolean> {
	if (!(await requireSession())) return false;
	const s = get(session);
	if (s?.user.role !== role) {
		await goto('/');
		return false;
	}
	return true;
}

let refreshTimer: ReturnType<typeof setInterval> | null = null;

/** Refresh proactivo cada 30 s (design §8.1). Idempotente. */
export function startSessionRefresh(): void {
	if (!browser || refreshTimer !== null) return;
	refreshTimer = setInterval(() => {
		void refreshIfNeeded();
	}, 30_000);
}
