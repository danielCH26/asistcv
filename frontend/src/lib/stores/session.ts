/**
 * Session store — Clerk-first implementation.
 *
 * All JWT machinery (localStorage pairs, proactivo refresh, single-flight,
 * JWT-decode expiry, /v1/auth/* endpoints) has been removed.
 * Clerk manages token issuance, short-lived JWT delivery via
 * `clerk.session.getToken()`, and automatic refresh.
 *
 * The exported surface is intentionally identical to the previous API so
 * that the 12 existing consumers (layout, pages, client) need no changes.
 */

import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import { derived, get, writable } from 'svelte/store';
import type { Readable } from 'svelte/store';
import type { Role, SessionUser } from '$api/types';
import type { UserResource } from '@clerk/shared/types/user';
import { ApiError } from '$api/types';
import { API_BASE } from '$api/base';
import {
	clerkReady,
	clerkUser,
	clerkSignOut,
	getToken,
	mountSignIn,
	mountSignUp,
} from '$lib/clerk';

// ─── Onboarding wizard (localStorage, unchanged) ──────────────────────────────

const ONBOARDING_KEY = 'asistcv.onboarding';

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

// ─── Audit token helpers (localStorage, unchanged) ────────────────────────────

const AUDIT_TOKEN_KEY = 'asistcv.audit_token';

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

// ─── Internal: backend user ─────────────────────────────────────────────────

/** Backend `SessionUser` populated from `/v1/users/me`. */
const backendUser = writable<SessionUser | null>(null);

// Track whether a pending audit claim has been fired to avoid double-sending.
let _auditClaimed = false;

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
		// body no JSON — use raw text.
	}
	return new ApiError(message || `Error HTTP ${res.status}`, res.status, text || res.statusText, code);
}

async function fetchBackendUser(): Promise<SessionUser> {
	const token = await getToken();
	if (!token) throw new ApiError('No Clerk token available', 401);
	const res = await fetch(`${API_BASE}/v1/users/me`, {
		headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
	});
	if (!res.ok) throw await parseError(res);
	return (await res.json()) as SessionUser;
}

/**
 * Fetches the backend user. On 401 (not yet provisioned) retries once after
 * 1 s — the backend auto-provisions on the first authenticated call.
 */
async function ensureBackendUser(): Promise<SessionUser | null> {
	try {
		return await fetchBackendUser();
	} catch (err) {
		if (err instanceof ApiError && err.status === 401) {
			// User not yet provisioned — wait for backend propagation.
			await new Promise((r) => setTimeout(r, 1_000));
			try {
				return await fetchBackendUser();
			} catch {
				return null;
			}
		}
		return null;
	}
}

/**
 * Best-effort claim of a pending audit token.
 * Called after `backendUser` first becomes non-null.
 */
async function claimPendingAudit(): Promise<void> {
	const token = getPendingAuditToken();
	if (!token || _auditClaimed) return;
	_auditClaimed = true;
	try {
		// The API client will call getToken() for the bearer.
		const { apiClient } = await import('$api/client');
		await apiClient.linkAudit(token);
		clearPendingAuditToken();
	} catch {
		// Claim is best-effort; do not block the session.
	}
}

// ─── clerkUser → backendUser propagation ──────────────────────────────────────

// Track the previous clerkUser value to detect null→non-null transitions.
let _prevClerkUserId: string | undefined;

clerkUser.subscribe((user) => {
	const currentId = user?.id;

	if (user && currentId !== _prevClerkUserId) {
		// Signed in or switched user — fetch backend user.
		_prevClerkUserId = currentId;
		_auditClaimed = false;
		void ensureBackendUser().then((bu) => {
			backendUser.set(bu);
			// After backend user is available, claim pending audit (if any).
			if (bu) void claimPendingAudit();
		});
	} else if (!user && _prevClerkUserId !== undefined) {
		// Signed out.
		_prevClerkUserId = undefined;
		_auditClaimed = false;
		backendUser.set(null);
	}
});

// ─── Public session surface ───────────────────────────────────────────────────

export interface Session {
	user: SessionUser;
}

/**
 * Derived session: non-null only when both Clerk user AND backend user exist.
 * The `Session` shape intentionally matches the old surface so that
 * `$session?.user.email` etc. continue to work in existing templates.
 */
/**
 * Email carried by the Clerk session.
 *
 * Used when the backend record is not there (yet): the local `users` row is
 * created by the first `/v1/users/me`, so until that call answers — or when
 * it fails — Clerk's own email is what the UI can show.
 */
function clerkEmail(user: UserResource | null): string | null {
	if (!user) return null;
	const direct = user.primaryEmailAddress?.emailAddress;
	if (direct) return direct;
	const addresses = user.emailAddresses ?? [];
	const primary = addresses.find((a) => a.id === user.primaryEmailAddressId);
	return primary?.emailAddress ?? addresses[0]?.emailAddress ?? null;
}

export const session: Readable<Session | null> = derived(
	[clerkUser, backendUser],
	([$clerkUser, $backendUser]) => {
		if (!$clerkUser || !$backendUser) return null;
		return { user: $backendUser };
	}
);

/**
 * Signed-in state: Clerk holds a session.
 *
 * Deliberately NOT "the backend returned a profile". Those are two different
 * facts, and the second one is slower and failure-prone: the first
 * `/v1/users/me` after a sign-in has to provision the local user, and it
 * fails on its own whenever the service is not configured for Clerk.
 * Deriving the navigation from it made a signed-in user look signed-out —
 * the header offered "Ingresar" to someone who had a live session, with no
 * way to tell that they were logged in.
 */
export const isAuthenticated = derived(clerkUser, ($u) => $u !== null);

/**
 * Email of the signed-in user: the backend record when it is loaded, Clerk's
 * own email otherwise.
 */
export const sessionEmail: Readable<string | null> = derived(
	[clerkUser, backendUser],
	([$clerkUser, $backendUser]) => $backendUser?.email ?? clerkEmail($clerkUser)
);

export const isRecruiter = derived(session, ($s) => $s?.user.role === 'recruiter');

/** Role from the authoritative backend user record. */
export const currentRole: Readable<Role | null> = derived(
	session,
	($s) => $s?.user.role ?? null
);

// ─── Guards ─────────────────────────────────────────────────────────────────

/**
 * Waits up to 5 s for Clerk to finish loading, then returns false if still
 * not signed in (treats as "not authenticated").  Otherwise ensures the
 * backend user record exists and returns true.
 */
export async function requireSession(): Promise<boolean> {
	if (!browser) return false;

	// Wait for Clerk to be ready (max 5 s).
	// Svelte stores emit the current value SYNCHRONOUSLY on subscribe, so the
	// ready case must not touch `unsub` inside the first callback invocation
	// (it would hit the temporal dead zone before assignment). Clean up via
	// microtask instead.
	const ready = await Promise.race([
		(async () => {
			if (get(clerkReady)) return true;
			return new Promise<boolean>((resolve) => {
				let unsub: (() => void) | undefined;
				unsub = clerkReady.subscribe((v) => {
					if (!v) return;
					queueMicrotask(() => unsub?.());
					resolve(true);
				});
			});
		})(),
		new Promise<boolean>((resolve) => setTimeout(() => resolve(false), 5_000)),
	]);

	if (!ready) {
		// Clerk not loaded — treat as signed out.
		await goto('/login?reason=required');
		return false;
	}

	const u = get(clerkUser);
	if (!u) {
		await goto('/login?reason=required');
		return false;
	}

	// Ensure backend user is populated (may trigger auto-provision).
	await ensureBackendUser();
	if (get(backendUser) === null) {
		// Could not reach backend; still treat as authenticated (Clerk session OK).
		// Guards below will fail if they need backend user specifically.
	}
	return true;
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

// ─── Logout ─────────────────────────────────────────────────────────────────

export async function logout(): Promise<void> {
	await clerkSignOut();
	backendUser.set(null);
	_prevClerkUserId = undefined;
	_auditClaimed = false;
	if (browser) await goto('/');
}

// ─── Re-export Clerk mount helpers for use by pages ──────────────────────────

/** Mounts Clerk's SignIn component (exported so login/+page.svelte can call it). */
export { mountSignIn, mountSignUp };

// NOTE: `login()` and `signup()` functions were removed — their call sites
// (login page and signup page) now use Clerk's hosted components instead.
// `refreshTokens`, `refreshIfNeeded`, `startSessionRefresh`, `refreshTimer`,
// `decodeJwtExpMs`, `sessionEvent`, and the localStorage `asistcv.session`
// key are all gone (replaced by Clerk's own session management).
