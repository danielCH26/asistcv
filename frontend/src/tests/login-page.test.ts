/**
 * Login page tests — Clerk component integration.
 *
 * Focus: the Clerk initialisation failure path.  `initClerk()` never
 * rejects; it publishes the reason through the `clerkError` store.  The page
 * must surface it and stop the loading spinner, otherwise the user stares at
 * an eternal "Cargando" with no explanation (QA 2026-10).
 */

import { render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/navigation', () => ({
	goto: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('$app/environment', () => ({
	browser: true,
}));

// Mock $app/stores before the component imports $page.
vi.mock('$app/stores', () => ({
	page: {
		subscribe(fn: (v: { url: { searchParams: { get: (k: string) => string | null } } }) => void) {
			fn({ url: { searchParams: { get: () => null } } });
			return () => {};
		},
	},
}));

const mockInitClerk = vi.fn();
const mockMountSignIn = vi.fn();

let clerkReadyValue = false;
const clerkReadySubscribers = new Set<(v: boolean) => void>();
function emitClerkReady(v: boolean) {
	clerkReadyValue = v;
	clerkReadySubscribers.forEach((fn) => fn(v));
}

let clerkErrorValue: string | null = null;
const clerkErrorSubscribers = new Set<(v: string | null) => void>();
function emitClerkError(v: string | null) {
	clerkErrorValue = v;
	clerkErrorSubscribers.forEach((fn) => fn(v));
}

vi.mock('$lib/clerk', () => ({
	initClerk: mockInitClerk,
	mountSignIn: mockMountSignIn,
	clerkReady: {
		subscribe(fn: (v: boolean) => void) {
			clerkReadySubscribers.add(fn);
			fn(clerkReadyValue);
			return () => {
				clerkReadySubscribers.delete(fn);
			};
		},
	},
	clerkError: {
		subscribe(fn: (v: string | null) => void) {
			clerkErrorSubscribers.add(fn);
			fn(clerkErrorValue);
			return () => {
				clerkErrorSubscribers.delete(fn);
			};
		},
	},
}));

beforeEach(() => {
	clerkReadyValue = false;
	clerkReadySubscribers.clear();
	clerkErrorValue = null;
	clerkErrorSubscribers.clear();
	mockInitClerk.mockClear();
	mockMountSignIn.mockClear();
	mockInitClerk.mockImplementation(async () => {
		await Promise.resolve();
		emitClerkReady(true);
	});
});

describe('login page — Clerk mount', () => {
	it('mounts the Clerk sign-in component once Clerk is ready', async () => {
		render(await import('../routes/login/+page.svelte').then((m) => m.default));

		await waitFor(() => {
			expect(mockMountSignIn).toHaveBeenCalled();
		});

		const opts = mockMountSignIn.mock.calls[0][1] as { redirectUrl?: string };
		expect(opts.redirectUrl).toBe('/');
	});
});

describe('login page — Clerk initialisation failure', () => {
	it('shows the error and stops the loading spinner instead of hanging', async () => {
		mockInitClerk.mockImplementation(async () => {
			await Promise.resolve();
			emitClerkError('Failed to load @clerk/ui bundle');
			return null;
		});

		const { container } = render(
			await import('../routes/login/+page.svelte').then((m) => m.default)
		);

		await waitFor(() => {
			expect(screen.getByRole('alert')).toBeTruthy();
		});

		expect(screen.getByRole('alert').textContent).toContain(
			'Failed to load @clerk/ui bundle'
		);
		// The loading spinner must be gone (this is what used to spin forever).
		expect(container.querySelector('.login__loading')).toBeNull();
		expect(mockMountSignIn).not.toHaveBeenCalled();
	});
});
