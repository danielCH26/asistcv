/**
 * Clerk singleton bridge — browser-only lazy initialiser.
 *
 * Build-time safety: `$app/environment`'s `browser` guard means this module
 * is never evaluated during server-side rendering.  Since the app uses
 * `ssr=false` via `@sveltejs/adapter-static` the risk is purely theoretical,
 * but the guard stays to make the intent explicit.
 *
 * Multiple `initClerk()` calls in the same JS context share one instance
 * (module-level promise cache).  `mountSignIn` / `mountSignUp` are thin
 * pass-through wrappers that let callers pass an `HTMLElement` without
 * importing Clerk types.
 */

import { browser } from '$app/environment';
import { writable } from 'svelte/store';
import type { Clerk } from '@clerk/clerk-js';
import type { UserResource } from '@clerk/shared/types/user';
import type { SignedInSessionResource } from '@clerk/shared/types/session';

// Module-level singleton — survives SvelteKit re-imports within a single page.
let _clerkPromise: Promise<Clerk> | null = null;
let _clerkInstance: Clerk | null = null;

/** Svelte store: null until Clerk finishes loading. */
export const clerkReady = writable(false);

/** Svelte store: Clerk UserResource when signed in, null otherwise. */
export const clerkUser = writable<UserResource | null>(null);

/** Svelte store: Clerk SessionResource when signed in, null otherwise. */
export const clerkSession = writable<SignedInSessionResource | null>(null);

/**
 * Lazily initialises the Clerk singleton and returns it.
 * Safe to call from `onMount` / dynamic event handlers; never from
 * module-level (top-level) code.
 */
export async function initClerk(): Promise<Clerk> {
	if (!browser) throw new Error('Clerk may only be initialised in the browser.');
	if (_clerkInstance) return _clerkInstance;

	if (!_clerkPromise) {
		_clerkPromise = (async () => {
			// Dynamic import keeps Clerk out of the SSR bundle.
			const { Clerk: ClerkClass } = await import('@clerk/clerk-js');
			const { esES } = await import('@clerk/localizations');

			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			// Use $env/dynamic/public so the key is available at runtime.
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		const env = await import('$env/dynamic/public') as any;
		const PUBLIC_CLERK_PUBLISHABLE_KEY = env.PUBLIC_CLERK_PUBLISHABLE_KEY;

			const clerk = new ClerkClass(PUBLIC_CLERK_PUBLISHABLE_KEY) as Clerk;

			clerk.addListener(({ user, session }) => {
				clerkUser.set(user ?? null);
				clerkSession.set(session ?? null);
			});

			await clerk.load({
				localization: esES,
				appearance: {
					variables: {
						// Teal primary matching AsistCV's `--color-action` token
						// (palette['--color-action'] = '#0f766e').
						colorPrimary: '#0f766e',
					},
				},
			});

			clerkReady.set(true);
			_clerkInstance = clerk;
			return clerk;
		})();
	}

	return _clerkPromise;
}

/** Returns the current Clerk JWT (short-lived, auto-refreshed by Clerk). */
export async function getToken(): Promise<string | null> {
	if (!_clerkInstance) return null;
	return _clerkInstance.session?.getToken() ?? null;
}

/** Signs the user out and clears the singleton. */
export async function clerkSignOut(): Promise<void> {
	if (!_clerkInstance) return;
	await _clerkInstance.signOut();
	_clerkInstance = null;
	_clerkPromise = null;
	clerkReady.set(false);
	clerkUser.set(null);
	clerkSession.set(null);
}

/** Mounts Clerk's pre-built SignIn component into `el`. */
export function mountSignIn(el: HTMLElement, opts?: { redirectUrl?: string }): void {
	if (!_clerkInstance) return;
	_clerkInstance.mountSignIn(el as HTMLDivElement, {
		fallbackRedirectUrl: opts?.redirectUrl ?? '/',
	});
}

/** Mounts Clerk's pre-built SignUp component into `el`. */
export function mountSignUp(el: HTMLElement, opts?: { redirectUrl?: string }): void {
	if (!_clerkInstance) return;
	_clerkInstance.mountSignUp(el as HTMLDivElement, {
		fallbackRedirectUrl: opts?.redirectUrl ?? '/',
	});
}
