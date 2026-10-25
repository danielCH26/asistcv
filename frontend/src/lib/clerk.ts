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
import { PUBLIC_CLERK_PUBLISHABLE_KEY } from '$env/static/public';
import type { Clerk } from '@clerk/clerk-js';
import type { UserResource } from '@clerk/shared/types/user';
import type { SignedInSessionResource } from '@clerk/shared/types/session';

/**
 * Clerk v6 (Core 3) split the SDK in two: `@clerk/clerk-js` ships the
 * headless client, and the prebuilt components (`<SignIn/>`, `<SignUp/>`)
 * live in a separate `@clerk/ui` bundle that the SDK does NOT download on
 * its own. Without it, `clerk.load()` leaves the component renderer
 * unattached and `mountSignIn()` throws
 * "Clerk was not loaded with Ui components".
 *
 * The bundle is loaded as a standalone UMD script from the Clerk Frontend
 * API CDN (per the official JS quickstart), which sets
 * `window.__internal_ClerkUICtor` — the constructor `clerk.load()` expects
 * in `ui.ClerkUI`.
 */
async function loadClerkUIBundle(publishableKey: string): Promise<void> {
	// Derive the Frontend API domain from the publishable key:
	// `pk_test_<base64(frontendApi$)>` → `frontendApi`.
	const encoded = publishableKey.split('_')[2];
	if (!encoded) {
		throw new Error('Malformed Clerk publishable key: missing frontend API segment.');
	}
	let frontendApi: string;
	try {
		frontendApi = atob(encoded).slice(0, -1);
	} catch {
		throw new Error('Malformed Clerk publishable key: not base64-decodable.');
	}

	const scriptUrl = `https://${frontendApi}/npm/@clerk/ui@1/dist/ui.browser.js`;

	await new Promise<void>((resolve, reject) => {
		const script = document.createElement('script');
		script.src = scriptUrl;
		script.async = true;
		script.crossOrigin = 'anonymous';
		script.onload = () => resolve();
		script.onerror = () => reject(new Error(`Failed to load @clerk/ui bundle from ${scriptUrl}`));
		document.head.appendChild(script);
	});
}

// Module-level singleton — survives SvelteKit re-imports within a single page.
// The promise resolves to `null` when initialisation failed (the reason is
// published through `clerkError`).
let _clerkPromise: Promise<Clerk | null> | null = null;
let _clerkInstance: Clerk | null = null;

/** Svelte store: null until Clerk finishes loading. */
export const clerkReady = writable(false);

/**
 * Svelte store: error message when Clerk failed to initialise.
 *
 * `initClerk()` never rejects: a failure (missing publishable key, blocked
 * `@clerk/ui` bundle, unreachable Clerk Frontend API) is reported here
 * instead. Without this, the login/signup pages stayed on their loading
 * spinner forever with no explanation — QA 2026-10.
 */
export const clerkError = writable<string | null>(null);

/** Svelte store: Clerk UserResource when signed in, null otherwise. */
export const clerkUser = writable<UserResource | null>(null);

/** Svelte store: Clerk SessionResource when signed in, null otherwise. */
export const clerkSession = writable<SignedInSessionResource | null>(null);

/**
 * Lazily initialises the Clerk singleton and returns it.
 * Safe to call from `onMount` / dynamic event handlers; never from
 * module-level (top-level) code.
 */
export async function initClerk(): Promise<Clerk | null> {
	if (!browser) throw new Error('Clerk may only be initialised in the browser.');
	if (_clerkInstance) return _clerkInstance;

	if (!_clerkPromise) {
		_clerkPromise = (async () => {
			// Dynamic import keeps Clerk out of the SSR bundle.
			const { Clerk: ClerkClass } = await import('@clerk/clerk-js');
			const { esES } = await import('@clerk/localizations');

			// Build-time literal. `$env/static/public` inlines the value into
			// the client bundle at build time (same pattern as
			// `$lib/api/base.ts` uses for PUBLIC_API_URL).
			//
			// Do NOT use `$env/dynamic/public`: its browser module exports a
			// single `env` object, so `mod.PUBLIC_CLERK_PUBLISHABLE_KEY` is
			// always `undefined` — that was the root cause of the "Clerk keys
			// are missing from your environment" failure in prod (QA 2026-10).
			const publishableKey = (PUBLIC_CLERK_PUBLISHABLE_KEY ?? '').trim();
			if (!publishableKey) {
				throw new Error('PUBLIC_CLERK_PUBLISHABLE_KEY is not set at build time.');
			}

			// The UI bundle must be present BEFORE `clerk.load()` — the SDK
			// resolves `ui.ClerkUI` at load time and never fetches it itself.
			await loadClerkUIBundle(publishableKey);

			const clerk = new ClerkClass(publishableKey) as Clerk;

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
				// Clerk v6: the prebuilt components come from the @clerk/ui
				// bundle loaded above (sets window.__internal_ClerkUICtor).
				// eslint-disable-next-line @typescript-eslint/no-explicit-any
				ui: { ClerkUI: (window as any).__internal_ClerkUICtor },
			});

			clerkReady.set(true);
			clerkError.set(null);
			_clerkInstance = clerk;
			return clerk;
		})().catch((err: unknown) => {
			// Report the failure instead of rejecting silently: the login and
			// signup pages await this call, and an unhandled rejection left
			// them spinning on the loading state with no feedback at all.
			clerkError.set(err instanceof Error ? err.message : String(err));
			// Allow a later attempt to retry the initialisation.
			_clerkPromise = null;
			return null;
		});
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
