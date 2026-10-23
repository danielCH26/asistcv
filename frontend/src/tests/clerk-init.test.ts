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

vi.mock('$env/dynamic/public', () => ({
	get PUBLIC_CLERK_PUBLISHABLE_KEY() {
		return publishableKey.value;
	}
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
