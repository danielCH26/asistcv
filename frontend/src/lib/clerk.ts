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
import { clerkUIBundleConstructor, loadClerkUIBundle } from '$lib/clerk-ui';
import type { Clerk } from '@clerk/clerk-js';
import type { UserResource } from '@clerk/shared/types/user';
import type { SignedInSessionResource } from '@clerk/shared/types/session';

// Module-level singleton — survives SvelteKit re-imports within a single page.
let _clerkPromise: Promise<Clerk> | null = null;
let _clerkInstance: Clerk | null = null;

/**
 * How long Clerk gets to finish loading before we give up on it.
 *
 * `clerk.load()` neither resolves nor rejects when the publishable key
 * points at an instance that cannot serve a client (Clerk answers HTTP 200
 * with `"client": null`). Without this bound the page waits forever.
 */
const CLERK_INIT_TIMEOUT_MS = 15_000;

/** Options for a Clerk initialization attempt. */
export interface ClerkInitOptions {
	/**
	 * Milliseconds to wait for Clerk to finish loading before failing.
	 * Defaults to {@link CLERK_INIT_TIMEOUT_MS}.
	 */
	timeoutMs?: number;
}

/** Diagnostic codes for a failed Clerk initialization. */
export type ClerkInitErrorCode = 'missing_key' | 'timeout' | 'load_failed';

/** Error thrown when Clerk cannot be initialized. Carries a diagnostic code. */
export class ClerkInitError extends Error {
	readonly code: ClerkInitErrorCode;

	constructor(code: ClerkInitErrorCode, cause?: unknown) {
		super(`Clerk initialization failed: ${code}`);
		this.name = 'ClerkInitError';
		this.code = code;
		if (cause !== undefined) this.cause = cause;
	}
}

/** Svelte store: null until Clerk finishes loading. */
export const clerkReady = writable(false);

/**
 * Svelte store: diagnostic code of the last Clerk initialization failure,
 * `null` when healthy. The UI renders a translated message; the code stays
 * for logs and tests, so a failed initialization is never silent.
 */
export const clerkError = writable<ClerkInitErrorCode | null>(null);

/** Svelte store: Clerk UserResource when signed in, null otherwise. */
export const clerkUser = writable<UserResource | null>(null);

/** Svelte store: Clerk SessionResource when signed in, null otherwise. */
export const clerkSession = writable<SignedInSessionResource | null>(null);

/**
 * Lazily initialises the Clerk singleton and returns it.
 * Safe to call from `onMount` / dynamic event handlers; never from
 * module-level (top-level) code.
 */
export async function initClerk(options: ClerkInitOptions = {}): Promise<Clerk> {
	if (!browser) throw new Error('Clerk may only be initialised in the browser.');
	if (_clerkInstance) return _clerkInstance;

	if (!_clerkPromise) {
		_clerkPromise = initializeClerk(options.timeoutMs ?? CLERK_INIT_TIMEOUT_MS).catch(
			(err: unknown) => {
				// A failed attempt must never be cached: a retry has to be able to
				// initialize Clerk from scratch, not re-await the rejected promise.
				_clerkPromise = null;
				clerkError.set(err instanceof ClerkInitError ? err.code : 'load_failed');
				throw err;
			}
		);
	}

	return _clerkPromise;
}

/**
 * Performs the actual Clerk initialization: loads the SDK, registers the
 * listeners and waits for `clerk.load()` to settle — with a timeout, so a
 * load that never settles becomes an error instead of an eternal wait.
 */
async function initializeClerk(timeoutMs: number): Promise<Clerk> {
	// Dynamic import keeps Clerk out of the SSR bundle.
	const { Clerk: ClerkClass } = await import('@clerk/clerk-js');
	const { esES } = await import('@clerk/localizations');

	// Build-time literal. `$env/static/public` inlines the value into the
	// client bundle at build time (same pattern as `$lib/api/base.ts` uses
	// for PUBLIC_API_URL).
	//
	// Do NOT use `$env/dynamic/public`: its browser module exports a single
	// `env` object, so `mod.PUBLIC_CLERK_PUBLISHABLE_KEY` is always
	// `undefined` — that was the root cause of the "Clerk keys are missing
	// from your environment" failure in prod (QA 2026-10).
	const publishableKey = (PUBLIC_CLERK_PUBLISHABLE_KEY ?? '').trim();
	if (!publishableKey) {
		throw new ClerkInitError('missing_key');
	}

	const clerk = new ClerkClass(publishableKey) as Clerk;

	// Clerk restaura la sesión desde el cookie de forma asíncrona: el
	// listener —que es quien entrega el usuario real— puede disparar un
	// tick DESPUÉS de que `load()` resuelva, y `clerk.user` sigue
	// `undefined` hasta entonces. `requireSession()` espera `clerkReady` y
	// lee `clerkUser` en el mismo turno, así que publicar el usuario antes
	// de marcar "ready" es lo que hace la guarda determinista: sin esto, una
	// carga completa de una página protegida expulsaba a un usuario que sí
	// tenía sesión.
	let settleUser: () => void = () => {};
	const userResolved = new Promise<void>((resolve) => {
		settleUser = resolve;
	});

	clerk.addListener(({ user, session }) => {
		clerkUser.set(user ?? null);
		clerkSession.set(session ?? null);
		settleUser();
	});

	let timer: ReturnType<typeof setTimeout> | undefined;
	const timeout = new Promise<never>((_resolve, reject) => {
		timer = setTimeout(() => reject(new ClerkInitError('timeout')), timeoutMs);
	});

	try {
		await Promise.race([
			(async () => {
				// The UI bundle must be present BEFORE `clerk.load()` — the SDK
				// resolves `ui.ClerkUI` at load time and never fetches it
				// itself. It runs INSIDE the timeout on purpose: a CDN that
				// never answers must surface as a timeout, not as an eternal
				// wait (the exact failure this module exists to prevent).
				await loadClerkUIBundle(publishableKey);

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
					ui: { ClerkUI: clerkUIBundleConstructor() },
				});
			})(),
			timeout
		]);
	} catch (err) {
		throw err instanceof ClerkInitError ? err : new ClerkInitError('load_failed', err);
	} finally {
		// Clear on both paths: a settled timer would keep the event loop alive.
		if (timer !== undefined) clearTimeout(timer);
	}

	// The session user may still be unresolved: Clerk restores it from the
	// cookie asynchronously, and the listener that delivers it can fire a
	// tick after `load()` settles. Waiting for it BEFORE signalling "ready"
	// is what makes the guard deterministic — `requireSession()` reads
	// `clerkUser` in the same turn it observes `clerkReady`. The instance's
	// own state is only read afterwards: Clerk populates it before it
	// notifies, so by then it is the resolved value and not `undefined`.
	await Promise.race([
		userResolved,
		new Promise<void>((resolve) => setTimeout(resolve, timeoutMs))
	]);
	clerkUser.set(clerk.user ?? null);
	clerkReady.set(true);
	_clerkInstance = clerk;
	return clerk;
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
	clerkError.set(null);
	clerkUser.set(null);
	clerkSession.set(null);
}

/**
 * Clears a previous initialization failure so the UI can offer a retry.
 * The next `initClerk()` call starts a fresh attempt.
 */
export function resetClerkError(): void {
	clerkError.set(null);
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
