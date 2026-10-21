/**
 * Signup page tests — Clerk component integration.
 *
 * The old tests (form submission to /v1/auth/register, consent gate) are gone.
 * The page now mounts Clerk's SignUp component.  Tests verify:
 *   - page renders without crashing
 *   - Clerk initClerk + mountSignUp are called
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
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

// ─── Mock Clerk module ────────────────────────────────────────────────────────

const mockInitClerk = vi.fn();
const mockMountSignUp = vi.fn();

// clerkReady starts as false so loading state is shown, then flips to true
// after a tick to simulate Clerk finishing load.
let clerkReadyValue = false;
const clerkReadySubscribers = new Set<(v: boolean) => void>();
function emitClerkReady(v: boolean) {
	clerkReadyValue = v;
	clerkReadySubscribers.forEach((fn) => fn(v));
}

vi.mock('$lib/clerk', () => ({
	initClerk: mockInitClerk.mockImplementation(async () => {
		// Simulate async load — mark ready after a tick.
		await Promise.resolve();
		emitClerkReady(true);
	}),
	mountSignUp: mockMountSignUp,
	clerkReady: {
		subscribe(fn: (v: boolean) => void) {
			clerkReadySubscribers.add(fn);
			fn(clerkReadyValue);
			return () => {
				clerkReadySubscribers.delete(fn);
			};
		},
	},
}));

// ─── Mock startOnboarding (called in onMount) ─────────────────────────────────

vi.mock('$stores/session', () => ({
	startOnboarding: vi.fn(),
	isOnboarding: vi.fn(() => false),
	completeOnboarding: vi.fn(),
}));

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
	localStorage.clear();
	vi.unstubAllGlobals();
	// Reset Clerk ready state for each test.
	clerkReadyValue = false;
	clerkReadySubscribers.clear();
	mockInitClerk.mockClear();
	mockMountSignUp.mockClear();
	mockInitClerk.mockImplementation(async () => {
		await Promise.resolve();
		emitClerkReady(true);
	});
});

describe('signup page — Clerk mount', () => {
	it('renders heading from i18n', async () => {
		render(await import('../routes/signup/+page.svelte').then((m) => m.default));

		// Heading must be present and contain the i18n text.
		const heading = screen.getByRole('heading', { level: 1 });
		expect(heading).toBeTruthy();
		expect(heading.textContent).toContain('Creá tu cuenta');
	});

	it('calls initClerk on mount', async () => {
		render(await import('../routes/signup/+page.svelte').then((m) => m.default));

		// Wait for initClerk to be called (it's async, so give it a tick).
		await waitFor(() => {
			expect(mockInitClerk).toHaveBeenCalled();
		});
	});

	it('mountSignUp is called with redirectUrl=/profile after Clerk is ready', async () => {
		render(await import('../routes/signup/+page.svelte').then((m) => m.default));

		await waitFor(() => {
			expect(mockMountSignUp).toHaveBeenCalled();
		});

		const call = mockMountSignUp.mock.calls[0];
		const opts = call[1] as { redirectUrl?: string };
		expect(opts.redirectUrl).toBe('/profile');
	});

	it('calls startOnboarding before Clerk mount', async () => {
		const { startOnboarding } = await import('$stores/session');

		render(await import('../routes/signup/+page.svelte').then((m) => m.default));

		await waitFor(() => {
			expect(mockInitClerk).toHaveBeenCalled();
		});
		expect(startOnboarding).toHaveBeenCalled();
	});
});
