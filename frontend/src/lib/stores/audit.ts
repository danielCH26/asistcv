import { writable, type Writable } from 'svelte/store';
import { ApiError, type AuditAnonymousResult } from '$api/types';
import { apiClient } from '$api/client';

export type AuditStatus = 'idle' | 'loading' | 'error' | 'done';

export interface AuditState {
	status: AuditStatus;
	result: AuditAnonymousResult | null;
	error: string | null;
	errorCode: string | null;
	retryAfter: number | null;
}

const initial: AuditState = {
	status: 'idle',
	result: null,
	error: null,
	errorCode: null,
	retryAfter: null
};

function createAuditStore() {
	const store: Writable<AuditState> = writable(initial);

	async function submit(
		jdText: string,
		cvText: string,
		cvFile?: File
	): Promise<AuditAnonymousResult | null> {
		if (jdText.trim().length < 50) {
			store.set({
				status: 'error',
				result: null,
				error: 'JD_TOO_SHORT',
				errorCode: 'JD_TOO_SHORT',
				retryAfter: null
			});
			return null;
		}
		store.set({ status: 'loading', result: null, error: null, errorCode: null, retryAfter: null });
		try {
			const payload = cvFile
				? { jd_text: jdText.trim(), cv_file: cvFile }
				: { jd_text: jdText.trim(), cv_text: cvText.trim() || undefined };
			const result = await apiClient.auditAnonymous(payload);
			store.set({ status: 'done', result, error: null, errorCode: null, retryAfter: null });
			return result;
		} catch (err) {
			const retryAfter = err instanceof ApiError ? (err.retryAfter ?? null) : null;
			const message = err instanceof ApiError ? err.message : 'Error inesperado';
			const errorCode = err instanceof ApiError ? (err.code ?? null) : null;
			store.set({ status: 'error', result: null, error: message, errorCode, retryAfter });
			return null;
		}
	}

	async function captureEmail(email: string): Promise<boolean> {
		const current = storeSubscribeOnce(store);
		if (!current.result) return false;
		try {
			await apiClient.captureAuditEmail(current.result.audit_token, email.trim());
			return true;
		} catch {
			return false;
		}
	}

	function reset() {
		store.set(initial);
	}

	return {
		subscribe: store.subscribe,
		submit,
		captureEmail,
		reset
	};
}

function storeSubscribeOnce(store: Writable<AuditState>): AuditState {
	let value: AuditState = initial;
	const unsub = store.subscribe((v) => (value = v));
	unsub();
	return value;
}

export const auditStore = createAuditStore();
