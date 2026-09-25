import { beforeEach, describe, expect, it, vi } from 'vitest';

// $app/navigation mockeado: fuera de una app SvelteKit viva, `goto` falla.
vi.mock('$app/navigation', () => ({
	goto: vi.fn().mockResolvedValue(undefined)
}));

// Tokens JWT de prueba: header.payload con exp a 15 minutos.
function fakeJwt(expiresInSeconds: number): string {
	const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).replace(/=+$/, '');
	const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + expiresInSeconds, sub: '1' })).replace(
		/=+$/,
		''
	);
	return `${header}.${payload}.sig`;
}

const USER = { id: 7, email: 'a@b.com', role: 'job_seeker', full_name: 'Ana', locale: 'es' };

function jsonRes(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

function stubFetch(routes: Array<[string, Response]>): ReturnType<typeof vi.fn> {
	const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
		const url = String(input);
		const match = routes.find(([path]) => url.includes(path));
		if (!match) throw new Error(`fetch inesperado: ${url}`);
		return match[1];
	});
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

beforeEach(() => {
	localStorage.clear();
	vi.unstubAllGlobals();
});

async function freshSession() {
	// Módulos frescos por test: el store cachea estado a nivel módulo.
	vi.resetModules();
	return import('./session');
}

describe('session store', () => {
	it('login persiste access+refresh y usuario en localStorage', async () => {
		const access = fakeJwt(900);
		const refresh = 'refresh-token-1';
		const fetchMock = stubFetch([
			['/v1/auth/login', jsonRes({ access_token: access, refresh_token: refresh, token_type: 'bearer' })],
			['/v1/users/me', jsonRes(USER)]
		]);

		const sessionModule = await freshSession();
		const user = await sessionModule.login('a@b.com', 'Passw0rd123');

		expect(user.id).toBe(7);
		const persisted = JSON.parse(localStorage.getItem('asistcv.session') ?? '{}');
		expect(persisted.accessToken).toBe(access);
		expect(persisted.refreshToken).toBe(refresh);
		expect(persisted.user.email).toBe('a@b.com');
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it('logout limpia la sesión y llama al endpoint con el refresh token', async () => {
		const { goto } = await import('$app/navigation');
		const access = fakeJwt(900);
		const fetchMock = stubFetch([
			['/v1/auth/login', jsonRes({ access_token: access, refresh_token: 'r1', token_type: 'bearer' })],
			['/v1/users/me', jsonRes(USER)],
			['/v1/auth/logout', new Response(null, { status: 204 })]
		]);

		const sessionModule = await freshSession();
		await sessionModule.login('a@b.com', 'Passw0rd123');
		await sessionModule.logout();

		expect(localStorage.getItem('asistcv.session')).toBeNull();
		const logoutCall = fetchMock.mock.calls.find(([input]) => String(input).includes('/v1/auth/logout'));
		expect(logoutCall).toBeDefined();
		expect((logoutCall?.[1] as RequestInit).body).toContain('r1');
		expect(goto).toHaveBeenCalledWith('/');
	});

	it('refreshIfNeeded renueva cuando el access expira en <60s', async () => {
		const access = fakeJwt(30);
		const newAccess = fakeJwt(900);
		const fetchMock = stubFetch([
			['/v1/auth/login', jsonRes({ access_token: access, refresh_token: 'r-old', token_type: 'bearer' })],
			['/v1/users/me', jsonRes(USER)],
			['/v1/auth/refresh', jsonRes({ access_token: newAccess, refresh_token: 'r-new', token_type: 'bearer' })]
		]);

		const sessionModule = await freshSession();
		await sessionModule.login('a@b.com', 'Passw0rd123');

		const ok = await sessionModule.refreshIfNeeded();
		expect(ok).toBe(true);

		const persisted = JSON.parse(localStorage.getItem('asistcv.session') ?? '{}');
		expect(persisted.accessToken).toBe(newAccess);
		expect(persisted.refreshToken).toBe('r-new');

		const refreshCalls = fetchMock.mock.calls.filter(([input]) => String(input).includes('/v1/auth/refresh'));
		expect(refreshCalls).toHaveLength(1);
	});

	it('refreshIfNeeded no renueva cuando falta mucho para expirar', async () => {
		const access = fakeJwt(900);
		const fetchMock = stubFetch([
			['/v1/auth/login', jsonRes({ access_token: access, refresh_token: 'r1', token_type: 'bearer' })],
			['/v1/users/me', jsonRes(USER)]
		]);

		const sessionModule = await freshSession();
		await sessionModule.login('a@b.com', 'Passw0rd123');

		const ok = await sessionModule.refreshIfNeeded();
		expect(ok).toBe(true);
		const refreshCalls = fetchMock.mock.calls.filter(([input]) => String(input).includes('/v1/auth/refresh'));
		expect(refreshCalls).toHaveLength(0);
	});

	it('refresh con 401 limpia la sesión (TOKEN_REUSED → evento)', async () => {
		const access = fakeJwt(30);
		stubFetch([
			['/v1/auth/login', jsonRes({ access_token: access, refresh_token: 'r1', token_type: 'bearer' })],
			['/v1/users/me', jsonRes(USER)],
			['/v1/auth/refresh', jsonRes({ detail: 'TOKEN_REUSED' }, 401)]
		]);

		const sessionModule = await freshSession();
		await sessionModule.login('a@b.com', 'Passw0rd123');

		const ok = await sessionModule.refreshIfNeeded();
		expect(ok).toBe(false);
		expect(localStorage.getItem('asistcv.session')).toBeNull();
	});

	it('signup registra y onboarding se marca/limpia con sus helpers', async () => {
		const access = fakeJwt(900);
		stubFetch([
			['/v1/auth/register', jsonRes({ access_token: access, refresh_token: 'r1', token_type: 'bearer' }, 201)],
			['/v1/users/me', jsonRes(USER)]
		]);

		const sessionModule = await freshSession();
		await sessionModule.signup({
			email: 'a@b.com',
			password: 'Passw0rd123',
			role: 'job_seeker',
			full_name: 'Ana',
			locale: 'es',
			accept_tos: false,
			good_faith_declaration: false,
			tos_version: '2025-sprint2'
		});
		expect(JSON.parse(localStorage.getItem('asistcv.session') ?? '{}').user.id).toBe(7);

		// El wizard lo dispara la página tras el registro (design §8.4).
		sessionModule.startOnboarding();
		expect(sessionModule.isOnboarding()).toBe(true);
		sessionModule.completeOnboarding();
		expect(sessionModule.isOnboarding()).toBe(false);
	});
});
