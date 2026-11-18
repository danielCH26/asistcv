/**
 * Navigation bar — the signed-in state.
 *
 * The header used to decide "am I signed in?" from the backend profile: the
 * navigation appeared only once `/v1/users/me` had answered with a local
 * user. That request is a separate, slower fact — it has to provision the
 * user (Clerk → local `users` row) and it fails on its own when the service
 * has no Clerk configuration. The result was a signed-in user looking at the
 * signed-out navigation ("Ingresar / Crear cuenta") with no way to tell that
 * they were logged in.
 *
 * These tests pin the user-visible contract: a Clerk session is enough for
 * the navigation to switch, whatever the backend says.
 */

import { render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/navigation', () => ({
	goto: vi.fn().mockResolvedValue(undefined)
}));

vi.mock('$app/environment', () => ({
	browser: true
}));

vi.mock('$app/stores', () => ({
	page: {
		subscribe(
			fn: (v: {
				url: { pathname: string; searchParams: { get: (k: string) => string | null } };
			}) => void
		) {
			fn({ url: { pathname: '/', searchParams: { get: () => null } } });
			return () => {};
		}
	}
}));

// ─── Clerk module mock (the stores are shared with the session store) ────────

function makeStore<T>(initial: T) {
	let value = initial;
	const subs = new Set<(v: T) => void>();
	return {
		subscribe(fn: (v: T) => void) {
			subs.add(fn);
			fn(value);
			return () => subs.delete(fn);
		},
		set(v: T) {
			value = v;
			subs.forEach((fn) => fn(v));
		}
	};
}

const clerkUser = makeStore<unknown>(null);
const clerkReady = makeStore(false);
const clerkSession = makeStore<unknown>(null);

vi.mock('$lib/clerk', () => ({
	initClerk: vi.fn().mockResolvedValue(null),
	clerkUser,
	clerkReady,
	clerkSession,
	getToken: vi.fn().mockResolvedValue('jwt'),
	clerkSignOut: vi.fn().mockResolvedValue(undefined),
	mountSignIn: vi.fn(),
	mountSignUp: vi.fn(),
	resetClerkError: vi.fn()
}));

const CLERK_USER = {
	id: 'u1',
	primaryEmailAddressId: 'e1',
	emailAddresses: [{ id: 'e1', emailAddress: 'ana@example.com' }],
	publicMetadata: {}
};

beforeEach(() => {
	localStorage.clear();
	// The layout picks the locale on import: force Spanish so the assertions
	// read the labels the product actually shows.
	localStorage.setItem('asistcv.locale', 'es');
	clerkUser.set(null);
	clerkReady.set(false);
	clerkSession.set(null);
	// The backend never answers with a profile: this is the situation the
	// navigation used to get wrong.
	vi.stubGlobal(
		'fetch',
		vi.fn(async () => new Response(JSON.stringify({ detail: 'Invalid credentials' }), { status: 401 }))
	);
});

async function renderLayout() {
	const mod = await import('../routes/+layout.svelte');
	return render(mod.default);
}

describe('layout navigation — signed-in state', () => {
	it('shows the signed-out navigation when there is no Clerk session', async () => {
		await renderLayout();

		await waitFor(() => {
			expect(screen.getByRole('link', { name: 'Ingresar' })).toBeTruthy();
		});
		expect(screen.queryByRole('link', { name: 'Mi perfil' })).toBeNull();
	});

	it('shows the signed-in navigation as soon as Clerk has a session', async () => {
		clerkUser.set(CLERK_USER);
		await renderLayout();

		await waitFor(() => {
			expect(screen.getByRole('link', { name: 'Mi perfil' })).toBeTruthy();
		});
		expect(screen.queryByRole('link', { name: 'Ingresar' })).toBeNull();
		expect(screen.queryByRole('link', { name: 'Crear cuenta' })).toBeNull();
	});

	it('offers the logout action and shows the signed-in email', async () => {
		clerkUser.set(CLERK_USER);
		await renderLayout();

		await waitFor(() => {
			expect(screen.getByRole('button', { name: 'Salir' })).toBeTruthy();
		});
		// The backend profile never loaded: the email has to come from Clerk.
		expect(screen.getByRole('button', { name: 'Salir' }).getAttribute('title')).toBe(
			'ana@example.com'
		);
	});
});
