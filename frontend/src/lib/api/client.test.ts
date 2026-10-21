/**
 * API client tests — Clerk token source.
 *
 * Removed: refresh-rotation tests (feature gone), TOKEN_REUSED 401 tests,
 * multiple-refresh retry tests.  Replaced with:
 *   - 401 propagates parsed ApiError without refresh attempts
 *   - Bearer from Clerk getToken() (mocked)
 *   - Error parsing preserved
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

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

// ─── Minimal clerk mock (all exports session.ts needs) ─────────────────────────

function makeWritable(initialValue: unknown) {
	let value = initialValue;
	const subs = new Set<(v: unknown) => void>();
	return {
		subscribe(fn: (v: unknown) => void) {
			subs.add(fn);
			fn(value);
			return () => subs.delete(fn);
		},
		set(v: unknown) {
			value = v;
			subs.forEach((fn) => fn(v));
		},
		update(fn: (v: unknown) => unknown) {
			const next = fn(value);
			value = next;
			subs.forEach((fn) => fn(next));
		},
	};
}

let fakeToken = 'clerk.jwt.token';
const clerkUser = makeWritable(null);
const clerkSession = makeWritable(null);
const clerkReady = makeWritable(true);

vi.mock('$lib/clerk', () => ({
	clerkReady,
	clerkUser,
	clerkSession,
	getToken: async () => fakeToken,
	clerkSignOut: async () => {},
	mountSignIn: vi.fn(),
	mountSignUp: vi.fn(),
	initClerk: vi.fn(),
}));

// ─── Helpers ─────────────────────────────────────────────────────────────────

function jsonRes(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'Content-Type': 'application/json' },
	});
}

beforeEach(() => {
	localStorage.clear();
	vi.unstubAllGlobals();
	fakeToken = 'clerk.jwt.token';
	vi.resetModules();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('apiClient — token source', () => {
	it('attaches Authorization: Bearer from Clerk getToken()', async () => {
		const fetchMock = vi.fn(async () => jsonRes([{ id: 1 }]));
		vi.stubGlobal('fetch', fetchMock);

		const { apiClient } = await import('./client');
		await apiClient.listCvs();

		const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/v1/cvs');
		expect((init.headers as Record<string, string>).Authorization).toBe(
			'Bearer clerk.jwt.token'
		);
	});

	it('no Authorization on public endpoints (plans)', async () => {
		const fetchMock = vi.fn(async () => jsonRes([{ plan_id: 'free' }]));
		vi.stubGlobal('fetch', fetchMock);

		const { apiClient } = await import('./client');
		await apiClient.plans();

		const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
	});

	it('null Clerk token → unauthenticated request (no crash)', async () => {
		fakeToken = '';
		const fetchMock = vi.fn(async () => jsonRes({ detail: 'Unauthorized' }, 401));
		vi.stubGlobal('fetch', fetchMock);

		const { apiClient } = await import('./client');

		// 401 → humanized "Tu sesión expiró" (same message as any 401 from Clerk).
		await expect(apiClient.listCvs()).rejects.toThrow('Tu sesión expiró');
	});
});

describe('apiClient — 401 handling (no refresh)', () => {
	it('401 throws ApiError without attempting any refresh', async () => {
		const fetchMock = vi.fn(async () => jsonRes({ detail: 'TOKEN_INVALID' }, 401));
		vi.stubGlobal('fetch', fetchMock);

		const { apiClient } = await import('./client');
		await expect(apiClient.listAnalyses()).rejects.toThrow('Tu sesión expiró');

		// Only one fetch call (the business call that returned 401).
		// No refresh, no retry.
		expect(fetchMock).toHaveBeenCalledTimes(1);
		const [url] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/v1/analyses');
	});

	it('401 redirects to /login?reason=expired in browser', async () => {
		const { goto } = await import('$app/navigation');
		const fetchMock = vi.fn(async () => jsonRes({ detail: 'TOKEN_INVALID' }, 401));
		vi.stubGlobal('fetch', fetchMock);

		const { apiClient } = await import('./client');
		await expect(apiClient.listAnalyses()).rejects.toThrow();

		expect(goto).toHaveBeenCalledWith('/login?reason=expired');
	});
});

describe('apiClient — error parsing', () => {
	it('structured {detail: string} → ApiError with code', async () => {
		const fetchMock = vi.fn(async () => jsonRes({ detail: 'EMAIL_TAKEN' }, 409));
		vi.stubGlobal('fetch', fetchMock);

		const { apiClient } = await import('./client');

		await expect(apiClient.listCvs()).rejects.toMatchObject({
			status: 409,
			code: 'EMAIL_TAKEN',
		});
	});

	it('structured {detail: {code, message}} → ApiError with message', async () => {
		const fetchMock = vi.fn(async () =>
			jsonRes({ detail: { code: 'RATE_LIMITED', message: 'Demasiados intentos.' } }, 429)
		);
		vi.stubGlobal('fetch', fetchMock);

		const { apiClient } = await import('./client');

		await expect(apiClient.listCvs()).rejects.toMatchObject({
			status: 429,
			code: 'RATE_LIMITED',
		});
	});

	it('non-JSON 500 → generic error', async () => {
		const fetchMock = vi.fn(
			async () => new Response('Internal Server Error', { status: 500 }) as unknown as Response
		);
		vi.stubGlobal('fetch', fetchMock);

		const { apiClient } = await import('./client');

		await expect(apiClient.listCvs()).rejects.toThrow('Error del servidor');
	});
});

describe('apiClient — FormData (CV upload, no Content-Type header)', () => {
	it('does not set Content-Type for FormData (browser sets it with boundary)', async () => {
		const fetchMock = vi.fn(async () => jsonRes({ cv_id: 1 }));
		vi.stubGlobal('fetch', fetchMock);

		const { apiClient } = await import('./client');
		const fakeFile = new File(['pdf-content'], 'cv.pdf', { type: 'application/pdf' });
		await apiClient.uploadCv(fakeFile);

		const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		// Browser sets Content-Type with boundary for FormData; our code must not override.
		expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined();
	});
});
