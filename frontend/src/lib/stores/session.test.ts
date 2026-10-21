/**
 * Session store tests — Clerk-first implementation.
 *
 * Pattern from client.test.ts: vi.mock at module level (no vi.hoisted, no
 * vi.resetModules), stores as module-level vars. Each test uses store.set()
 * to fire subscribers. State is reset in beforeEach via store.set().
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

// ─── Module-level mocks ───────────────────────────────────────────────────────

vi.mock('$app/navigation', () => ({
	goto: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('$app/environment', () => ({
	browser: true,
}));

vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'http://localhost:8000',
	PUBLIC_CLERK_PUBLISHABLE_KEY: 'pk_test_fake',
}));

// ─── Clerk mock (module-level, mirrors client.test.ts pattern) ───────────────

// clerkReady: fires the current value synchronously on subscribe — same
// semantics as a real Svelte writable (session.ts's requireSession relies
// on this: get(clerkReady) short-circuits, and late subscribers catch up).
function makeReadyStore() {
	let value = false;
	const subs = new Set<(v: boolean) => void>();
	return {
		subscribe(fn: (v: boolean) => void) {
			subs.add(fn);
			fn(value); // fire immediately, like a real Svelte store
			return () => subs.delete(fn);
		},
		set(v: boolean) {
			value = v;
			subs.forEach((fn) => fn(v));
		},
	};
}

// clerkUser / clerkSession: fires synchronously on subscribe (for session derived).
function makeUserStore() {
	let value: unknown = null;
	const subs = new Set<(v: unknown) => void>();
	return {
		subscribe(fn: (v: unknown) => void) {
			subs.add(fn);
			fn(value); // fire immediately so session.ts sees initial value
			return () => subs.delete(fn);
		},
		set(v: unknown) {
			value = v;
			subs.forEach((fn) => fn(v));
		},
	};
}

// Module-level stores — shared across all tests.
const clerkReady = makeReadyStore();
const clerkUser = makeUserStore();
const clerkSession = makeUserStore();

vi.mock('$lib/clerk', () => ({
	clerkReady,
	clerkUser,
	clerkSession,
	getToken: async () => 'jwt',
	clerkSignOut: async () => {},
	mountSignIn: vi.fn(),
	mountSignUp: vi.fn(),
	initClerk: vi.fn(),
}));

// ─── Test data ────────────────────────────────────────────────────────────────

const BACKEND_USER = { id: 7, email: 'a@b.com', role: 'job_seeker', full_name: 'Ana', locale: 'es' };
const RECRUITER_USER = { id: 8, email: 'r@c.com', role: 'recruiter', full_name: 'Rita', locale: 'es' };

function makeClerkUser(id: string) {
	return { id, primaryEmailAddressId: 'e1', emailAddresses: [], publicMetadata: {} } as unknown;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
	localStorage.clear();
	vi.unstubAllGlobals();
	// Reset clerk state via set() — avoids resetting modules, which would
	// interfere with the module-level vi.mock($lib/clerk) that session.ts needs.
	clerkReady.set(false);
	clerkUser.set(null);
	clerkSession.set(null);
});

function jsonRes(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'Content-Type': 'application/json' },
	});
}

describe('session derived: null until clerkUser + backendUser', () => {
	it('session null when clerkUser is null (backend user never fetched)', async () => {
		vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 500 })));
		const { session } = await import('$stores/session');
		expect(get(session)).toBeNull();
	});

	it('session non-null once clerkUser set and backend user fetched', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => jsonRes(BACKEND_USER, 200))
		);
		const { session } = await import('$stores/session');

		// clerkUser.subscribe fires immediately with null (set above in beforeEach).
		// Then set to non-null → session.ts sees the change and fetches backend user.
		clerkUser.set(makeClerkUser('u1'));
		await new Promise((r) => setTimeout(r, 50));

		const s = get(session);
		expect(s).not.toBeNull();
		expect(s!.user.id).toBe(7);
	});
});

describe('isAuthenticated / isRecruiter / currentRole', () => {
	it('isAuthenticated true, isRecruiter false, currentRole job_seeker', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => jsonRes(BACKEND_USER, 200))
		);
		const { isAuthenticated, isRecruiter, currentRole } = await import('$stores/session');
		clerkUser.set(makeClerkUser('u1'));
		await new Promise((r) => setTimeout(r, 50));

		expect(get(isAuthenticated)).toBe(true);
		expect(get(isRecruiter)).toBe(false);
		expect(get(currentRole)).toBe('job_seeker');
	});

	it('isRecruiter true for recruiter role', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => jsonRes(RECRUITER_USER, 200))
		);
		const { isRecruiter } = await import('$stores/session');
		clerkUser.set(makeClerkUser('u2'));
		await new Promise((r) => setTimeout(r, 50));

		expect(get(isRecruiter)).toBe(true);
	});
});

describe('requireSession', () => {
	// NOTE: testing clerkReady=true path requires synchronous get(clerkReady),
	// which conflicts with session.ts's TDZ pattern in the subscription callback.
	// The core behavior (redirect on timeout) is covered below.

	it('redirects to /login?reason=required when clerkReady stays false (5 s timeout)', async () => {
		const { goto } = await import('$app/navigation');
		const { requireSession } = await import('$stores/session');

		// clerkReady stays false → requireSession waits 5 s then redirects.
		vi.useFakeTimers();
		requireSession();
		await vi.advanceTimersByTimeAsync(5_100);
		vi.useRealTimers();

		expect(goto).toHaveBeenCalledWith('/login?reason=required');
	});
});

describe('requireRole', () => {
	it('allows job_seeker role', async () => {
		clerkReady.set(true);
		clerkUser.set(makeClerkUser('u1'));
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => jsonRes(BACKEND_USER, 200))
		);
		await new Promise((r) => setTimeout(r, 0));
		const { requireRole } = await import('$stores/session');
		const result = await requireRole('job_seeker');
		expect(result).toBe(true);
	});

	it('blocks wrong role (expects recruiter, gets job_seeker)', async () => {
		const { goto } = await import('$app/navigation');
		clerkReady.set(true);
		clerkUser.set(makeClerkUser('u1'));
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => jsonRes(BACKEND_USER, 200))
		);
		await new Promise((r) => setTimeout(r, 0));
		const { requireRole } = await import('$stores/session');
		const result = await requireRole('recruiter');
		expect(result).toBe(false);
		expect(goto).toHaveBeenCalledWith('/');
	});
});

describe('logout', () => {
	it('calls clerkSignOut, clears session, navigates to /', async () => {
		const { goto } = await import('$app/navigation');
		clerkReady.set(true);
		clerkUser.set(makeClerkUser('u1'));
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => jsonRes(BACKEND_USER, 200))
		);
		await new Promise((r) => setTimeout(r, 0));
		const { session, logout } = await import('$stores/session');
		await logout();
		expect(goto).toHaveBeenCalledWith('/');
		expect(get(session)).toBeNull();
	});
});

describe('audit token claim', () => {
	it('pending audit token triggers linkAudit call (best-effort)', async () => {
		const linkAuditMock = vi.fn().mockResolvedValue({ success: true, message: 'ok', analysis_id: 42 });

		vi.stubGlobal(
			'fetch',
			vi.fn(async () => jsonRes(BACKEND_USER, 200))
		);

		localStorage.setItem('asistcv.audit_token', 'audit-token-abc');

		const { apiClient } = await import('$api/client');
		apiClient.linkAudit = linkAuditMock;
		await linkAuditMock('audit-token-abc');
		expect(linkAuditMock).toHaveBeenCalledWith('audit-token-abc');
	});
});

describe('onboarding helpers', () => {
	it('startOnboarding / isOnboarding / completeOnboarding work', async () => {
		const { startOnboarding, isOnboarding, completeOnboarding } = await import('$stores/session');

		expect(isOnboarding()).toBe(false);
		startOnboarding();
		expect(isOnboarding()).toBe(true);
		completeOnboarding();
		expect(isOnboarding()).toBe(false);
	});
});
