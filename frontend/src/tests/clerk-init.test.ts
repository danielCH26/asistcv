/**
 * Clerk initialization module — failure handling.
 *
 * Two properties are pinned here, both learned from the production incident
 * where `/signup` hung forever:
 *
 *   1. `initClerk()` never resolves indefinitely. A `clerk.load()` that
 *      neither resolves nor rejects (Clerk answers HTTP 200 with
 *      `"client": null`) must surface as a timeout error.
 *   2. A failed attempt is not cached. The module-level promise cache is
 *      reset on failure, otherwise a retry would re-await the rejected
 *      promise and could never succeed.
 */

import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/environment', () => ({
	browser: true
}));

const loadMock = vi.fn();
const addListenerMock = vi.fn();
const publishableKey = { value: 'pk_test_dummy' };

vi.mock('@clerk/clerk-js', () => ({
	Clerk: class {
		addListener = addListenerMock;
		load = loadMock;
	}
}));

vi.mock('@clerk/localizations', () => ({
	esES: {}
}));

// The publishable key is read from `$env/static/public`, which inlines the
// value into the client bundle at build time. `$env/dynamic/public` cannot
// be used: its browser module exports a single `env` object, so
// `mod.PUBLIC_CLERK_PUBLISHABLE_KEY` is always undefined.
vi.mock('$env/static/public', () => ({
	get PUBLIC_CLERK_PUBLISHABLE_KEY() {
		return publishableKey.value;
	}
}));

// The Clerk UI bundle is loaded from the Frontend API CDN in production.
// Tests stub it: jsdom does not fetch external scripts, so the real loader
// would never settle.
const loadUIBundleMock = vi.fn().mockResolvedValue(undefined);
vi.mock('$lib/clerk-ui', () => ({
	loadClerkUIBundle: loadUIBundleMock,
	clerkUIBundleConstructor: () => ({})
}));

/** Fresh module instance per test: the singleton cache is module-level. */
async function freshModule() {
	vi.resetModules();
	return import('../lib/clerk');
}

beforeEach(() => {
	loadMock.mockReset();
	addListenerMock.mockReset();
	publishableKey.value = 'pk_test_dummy';
	loadUIBundleMock.mockReset().mockResolvedValue(undefined);
});

afterEach(() => {
	vi.useRealTimers();
});

describe('initClerk — failure handling', () => {
	it('rejects and publishes the failure when clerk.load() throws', async () => {
		loadMock.mockRejectedValue(new Error('network down'));

		const { initClerk, clerkError } = await freshModule();

		await expect(initClerk()).rejects.toThrow();
		expect(get(clerkError)).toBe('load_failed');
	});

	it('rejects with a timeout when clerk.load() never settles', async () => {
		loadMock.mockReturnValue(new Promise(() => {}));

		const { initClerk, clerkError } = await freshModule();

		await expect(initClerk({ timeoutMs: 50 })).rejects.toMatchObject({ code: 'timeout' });
		expect(get(clerkError)).toBe('timeout');
	});

	it('rejects with missing_key when the publishable key is absent', async () => {
		publishableKey.value = '';

		const { initClerk, clerkError } = await freshModule();

		await expect(initClerk()).rejects.toMatchObject({ code: 'missing_key' });
		expect(get(clerkError)).toBe('missing_key');
	});

	it('rejects with a timeout when the UI bundle never settles', async () => {
		// A blocked or slow Frontend API CDN must not hang the page: the
		// bundle load runs inside the initialization timeout.
		loadUIBundleMock.mockReturnValue(new Promise(() => {}));

		const { initClerk, clerkError } = await freshModule();

		await expect(initClerk({ timeoutMs: 50 })).rejects.toMatchObject({ code: 'timeout' });
		expect(get(clerkError)).toBe('timeout');
		expect(loadMock).not.toHaveBeenCalled();
	});

	it('rejects with load_failed when the UI bundle fails to load', async () => {
		loadUIBundleMock.mockRejectedValue(new Error('Failed to load @clerk/ui bundle'));

		const { initClerk, clerkError } = await freshModule();

		await expect(initClerk()).rejects.toMatchObject({ code: 'load_failed' });
		expect(get(clerkError)).toBe('load_failed');
	});

	it('can retry after a failed initialization', async () => {
		loadMock.mockRejectedValueOnce(new Error('network down'));

		const { initClerk, clerkError } = await freshModule();

		await expect(initClerk()).rejects.toThrow();
		expect(get(clerkError)).toBe('load_failed');

		// The rejected promise must not be cached: the second call starts a
		// fresh attempt instead of re-awaiting the failure.
		loadMock.mockResolvedValueOnce(undefined);
		await expect(initClerk()).resolves.toBeTruthy();
		expect(get(clerkError)).toBe('load_failed');
	});
});
