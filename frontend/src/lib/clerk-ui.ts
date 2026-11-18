/**
 * Loader for the Clerk UI bundle (Clerk v6 / Core 3).
 *
 * `@clerk/clerk-js` ships the headless client. The prebuilt components
 * (`<SignIn/>`, `<SignUp/>`) live in a separate `@clerk/ui` bundle that the
 * SDK does NOT download on its own: without it, `clerk.load()` leaves the
 * component renderer unattached and `mountSignIn()` throws
 * "Clerk was not loaded with Ui components".
 *
 * The bundle is published as a standalone UMD script on the Clerk Frontend
 * API CDN (per the official JS quickstart). Loading it sets
 * `window.__internal_ClerkUICtor` — the constructor `clerk.load()` expects
 * in `ui.ClerkUI`.
 *
 * It lives in its own module so the loading path can be stubbed in tests
 * without touching the initialization logic.
 */
import type { ClerkUIConstructor } from '@clerk/shared/ui';

/**
 * Returns the UI constructor injected by the bundle, or `undefined` when the
 * bundle has not been loaded.
 */
export function clerkUIBundleConstructor(): ClerkUIConstructor | undefined {
	if (typeof window === 'undefined') return undefined;
	return (window as unknown as { __internal_ClerkUICtor?: ClerkUIConstructor })
		.__internal_ClerkUICtor;
}

/**
 * Derives the Frontend API domain from a Clerk publishable key.
 *
 * `pk_test_<base64(frontendApi$)>` → `frontendApi`.
 */
export function frontendApiFromPublishableKey(publishableKey: string): string {
	const encoded = publishableKey.split('_')[2];
	if (!encoded) {
		throw new Error('Malformed Clerk publishable key: missing frontend API segment.');
	}
	let decoded: string;
	try {
		decoded = atob(encoded);
	} catch {
		throw new Error('Malformed Clerk publishable key: not base64-decodable.');
	}
	// The decoded payload is the bare domain followed by "$".
	return decoded.slice(0, -1);
}

/**
 * Loads the Clerk UI bundle from the Frontend API CDN.
 *
 * Idempotent: when the bundle already injected its constructor, this
 * resolves without touching the network — a retry after a failed
 * initialization must not queue a second copy of the script.
 */
export async function loadClerkUIBundle(publishableKey: string): Promise<void> {
	if (clerkUIBundleConstructor() !== undefined) return;

	const frontendApi = frontendApiFromPublishableKey(publishableKey);
	const scriptUrl = `https://${frontendApi}/npm/@clerk/ui@1/dist/ui.browser.js`;

	await new Promise<void>((resolve, reject) => {
		const script = document.createElement('script');
		script.src = scriptUrl;
		script.async = true;
		script.crossOrigin = 'anonymous';
		script.onload = () => resolve();
		script.onerror = () =>
			reject(new Error(`Failed to load @clerk/ui bundle from ${scriptUrl}`));
		document.head.appendChild(script);
	});
}
