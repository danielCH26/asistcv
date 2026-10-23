/**
 * Clerk initialization failure — the page must not hang on a spinner.
 *
 * Production shipped a publishable key whose Clerk instance answers the FAPI
 * with `"client": null`, so `clerk.load()` never settled and `/signup` (and
 * `/login`) showed a spinner forever with no feedback at all.
 *
 * These tests pin the contract between the page and the Clerk store: when the
 * initialization fails, the page renders an actionable error, the spinner is
 * never the terminal state, and a retry re-runs the initialization.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/navigation', () => ({
	goto: vi.fn().mockResolvedValue(undefined)
}));

vi.mock('$app/environment', () => ({
	browser: true
}));

vi.mock('$app/stores', () => ({
	page: {
		subscribe(fn: (v: { url: { searchParams: { get: (k: string) => string | null } } }) => void) {
			fn({ url: { searchParams: { get: () => null } } });
			return () => {};
		}
	}
}));

// ─── Mock Clerk module ────────────────────────────────────────────────────────

const mockInitClerk = vi.fn();
const mockMountSignUp = vi.fn();
const mockResetClerkError = vi.fn();

let clerkErrorValue: string | null = null;
const clerkErrorSubscribers = new Set<(v: string | null) => void>();
function emitClerkError(v: string | null) {
	clerkErrorValue = v;
	clerkErrorSubscribers.forEach((fn) => fn(v));
}

vi.mock('$lib/clerk', () => ({
	initClerk: mockInitClerk,
	mountSignUp: mockMountSignUp,
	resetClerkError: mockResetClerkError,
	clerkReady: {
		subscribe(fn: (v: boolean) => void) {
			fn(false);
			return () => {};
		}
	},
	clerkError: {
		subscribe(fn: (v: string | null) => void) {
			clerkErrorSubscribers.add(fn);
			fn(clerkErrorValue);
			return () => {
				clerkErrorSubscribers.delete(fn);
			};
		}
	}
}));

vi.mock('$stores/session', () => ({
	startOnboarding: vi.fn(),
	isOnboarding: vi.fn(() => false),
	completeOnboarding: vi.fn()
}));

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
	localStorage.clear();
	clerkErrorValue = null;
	clerkErrorSubscribers.clear();
	mockInitClerk.mockReset();
	mockMountSignUp.mockReset();
	mockResetClerkError.mockReset();

	// Mirrors the real module: initClerk publishes the failure through
	// clerkError and then rethrows.
	mockInitClerk.mockImplementation(async () => {
		emitClerkError('load_failed');
		throw new Error('clerk failed to load');
	});
});

describe('signup page — Clerk initialization failure', () => {
	it('renders an actionable error instead of an endless spinner', async () => {
		render(await import('../routes/signup/+page.svelte').then((m) => m.default));

		await waitFor(() => {
			expect(screen.getByRole('alert')).toBeTruthy();
		});

		expect(screen.getByText('No pudimos cargar el acceso')).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Reintentar' })).toBeTruthy();

		// The spinner must never be the terminal state.
		expect(document.querySelector('.signup__spinner')).toBeNull();

		// No component was mounted: Clerk never became ready.
		expect(mockMountSignUp).not.toHaveBeenCalled();
	});

	it('re-runs the initialization when the user retries', async () => {
		render(await import('../routes/signup/+page.svelte').then((m) => m.default));

		await waitFor(() => {
			expect(screen.getByRole('alert')).toBeTruthy();
		});

		await fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }));

		await waitFor(() => {
			expect(mockInitClerk).toHaveBeenCalledTimes(2);
		});
		expect(mockResetClerkError).toHaveBeenCalled();
	});
});

describe('login page — Clerk initialization failure', () => {
	it('renders an actionable error instead of an endless spinner', async () => {
		render(await import('../routes/login/+page.svelte').then((m) => m.default));

		await waitFor(() => {
			expect(screen.getByRole('alert')).toBeTruthy();
		});

		expect(screen.getByText('No pudimos cargar el acceso')).toBeTruthy();
		expect(document.querySelector('.login__spinner')).toBeNull();
	});
});
