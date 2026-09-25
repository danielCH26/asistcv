import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/navigation', () => ({
	goto: vi.fn().mockResolvedValue(undefined)
}));

const OLD_ACCESS = ['old', 'access', 'token'].join('.');

function fakeJwt(expiresInSeconds: number): string {
	const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).replace(/=+$/, '');
	const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + expiresInSeconds, sub: '1' })).replace(
		/=+$/,
		''
	);
	return `${header}.${payload}.sig`;
}

const USER: { id: number; email: string; role: 'recruiter'; full_name: string; locale: string } = {
	id: 7,
	email: 'a@b.com',
	role: 'recruiter',
	full_name: 'Ana',
	locale: 'es'
};

function jsonRes(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

beforeEach(() => {
	localStorage.clear();
	vi.unstubAllGlobals();
	vi.resetModules();
});

async function bootstrapSession() {
	// Sesión con access fresco (no dispara refresh proactivo).
	const { session } = await import('$stores/session');
	session.set({
		accessToken: OLD_ACCESS,
		refreshToken: 'r-current',
		user: USER,
		expiresAt: Date.now() + 15 * 60 * 1000
	});
}

describe('api client', () => {
	it('adjunta Authorization: Bearer cuando hay sesión', async () => {
		const fetchMock = vi.fn(async () => jsonRes([{ id: 1 }]));
		vi.stubGlobal('fetch', fetchMock);
		await bootstrapSession();

		const { apiClient } = await import('./client');
		await apiClient.listCvs();

		const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/v1/cvs');
		expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${OLD_ACCESS}`);
	});

	it('sin sesión no envía Authorization (endpoints públicos)', async () => {
		const fetchMock = vi.fn(async () => jsonRes([{ plan_id: 'free' }]));
		vi.stubGlobal('fetch', fetchMock);

		const { apiClient } = await import('./client');
		await apiClient.plans();

		const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
	});

	it('ante 401 refresca una vez y reintenta con el nuevo token', async () => {
		const NEW_ACCESS = fakeJwt(900);
		let businessCalls = 0;
		const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
			const url = String(input);
			if (url.includes('/v1/auth/refresh')) {
				return jsonRes({ access_token: NEW_ACCESS, refresh_token: 'r-new', token_type: 'bearer' });
			}
			businessCalls += 1;
			if (businessCalls === 1) {
				return jsonRes({ detail: 'TOKEN_INVALID' }, 401);
			}
			const auth = (init?.headers as Record<string, string>)?.Authorization ?? '';
			expect(auth).toBe(`Bearer ${NEW_ACCESS}`);
			return jsonRes([{ id: 1 }]);
		});
		vi.stubGlobal('fetch', fetchMock);
		await bootstrapSession();

		const { apiClient } = await import('./client');
		const result = await apiClient.listCvs();

		expect(result).toEqual([{ id: 1 }]);
		expect(businessCalls).toBe(2);
		const persisted = JSON.parse(localStorage.getItem('asistcv.session') ?? '{}');
		expect(persisted.refreshToken).toBe('r-new');
	});

	it('ante 401 definitivo (refresh falla) limpia sesión y redirige a /login', async () => {
		const { goto } = await import('$app/navigation');
		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			const url = String(input);
			if (url.includes('/v1/auth/refresh')) {
				return jsonRes({ detail: 'TOKEN_INVALID' }, 401);
			}
			return jsonRes({ detail: 'TOKEN_INVALID' }, 401);
		});
		vi.stubGlobal('fetch', fetchMock);
		await bootstrapSession();

		const { apiClient } = await import('./client');
		await expect(apiClient.listAnalyses()).rejects.toThrow();

		expect(localStorage.getItem('asistcv.session')).toBeNull();
		expect(goto).toHaveBeenCalledWith('/login?reason=expired');
	});

	it('no reintenta más de una vez: dos 401 seguidos con refresh OK → error', async () => {
		let businessCalls = 0;
		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			const url = String(input);
			if (url.includes('/v1/auth/refresh')) {
				return jsonRes({ access_token: fakeJwt(900), refresh_token: 'r-new', token_type: 'bearer' });
			}
			businessCalls += 1;
			return jsonRes({ detail: 'TOKEN_INVALID' }, 401);
		});
		vi.stubGlobal('fetch', fetchMock);
		await bootstrapSession();

		const { apiClient } = await import('./client');
		await expect(apiClient.listAnalyses()).rejects.toThrow();

		expect(businessCalls).toBe(2);
		expect(localStorage.getItem('asistcv.session')).toBeNull();
	});
});
