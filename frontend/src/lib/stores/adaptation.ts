import { derived, get, writable, type Readable, type Writable } from 'svelte/store';
import {
	ApiError,
	type AdaptationDetail,
	type AdaptationRequest,
	type AdaptationSummary
} from '$api/types';
import { apiClient } from '$api/client';

/**
 * Store del flujo de adaptación CV -> JD (Sprint 3 Slice A, PR3).
 *
 * Estado: una sola adaptación "activa" a la vez. La UI muestra idle /
 * loading / completed / failed; cuando llega a terminal, no vuelve a
 * llamar a la API salvo que el usuario haga un nuevo submit.
 *
 * Polling:
 * - 2 s × 15 polls  (0-30 s)
 * - 5 s × 6 polls   (30-60 s)
 * - 30 s × 2 polls  (60-120 s) — lejana para cold-start del runner
 * - Total: 95 s. Pasado eso, el job se considera colgado y se
 *   abandona con un mensaje dedicado.
 */

export type AdaptationStatus = 'idle' | 'pending' | 'completed' | 'failed';

export interface AdaptationState {
	status: AdaptationStatus;
	adaptation: AdaptationDetail | null;
	errorCode: string | null;
	errorMessage: string | null;
	jobId: number | null;
}

const initial: AdaptationState = {
	status: 'idle',
	adaptation: null,
	errorCode: null,
	errorMessage: null,
	jobId: null
};

interface PollStep {
	delayMs: number;
	tries: number;
}

const POLL_SCHEDULE: PollStep[] = [
	{ delayMs: 2_000, tries: 15 },
	{ delayMs: 5_000, tries: 6 },
	{ delayMs: 30_000, tries: 2 }
];
const POLL_GIVE_UP_MESSAGE = 'POLL_TIMEOUT';

function delay(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

function readError(err: unknown): { code: string | null; message: string } {
	if (err instanceof ApiError) {
		return { code: err.code ?? null, message: err.message };
	}
	if (err instanceof Error) {
		return { code: null, message: err.message };
	}
	return { code: null, message: 'Error inesperado' };
}

function createAdaptationStore() {
	const store: Writable<AdaptationState> = writable(initial);
	let inflight: Promise<void> | null = null;

	async function createAdaptation(
		cvId: number,
		jdText: string
	): Promise<AdaptationDetail | null> {
		const payload: AdaptationRequest = { cv_id: cvId, jd_text: jdText };
		store.set({ ...initial, status: 'pending' });
		try {
			const accepted = await apiClient.createAdaptation(payload);
			store.update((s) => ({
				...s,
				status: 'pending',
				jobId: accepted.adaptation_id,
				errorCode: null,
				errorMessage: null
			}));
			await pollAdaptation(accepted.adaptation_id);
		} catch (err) {
			const { code, message } = readError(err);
			store.update((s) => ({
				...s,
				status: 'failed',
				errorCode: code,
				errorMessage: message
			}));
			return null;
		}
		const state = get(store);
		return state.adaptation;
	}

	async function pollAdaptation(jobId: number): Promise<void> {
		if (inflight) {
			await inflight;
		}
		const run = async () => {
			for (const step of POLL_SCHEDULE) {
				for (let i = 0; i < step.tries; i += 1) {
					await delay(step.delayMs);
					let detail: AdaptationDetail;
					try {
						detail = await apiClient.getAdaptation(jobId);
					} catch (err) {
						const { code, message } = readError(err);
						store.update((s) => ({
							...s,
							status: 'failed',
							errorCode: code,
							errorMessage: message
						}));
						return;
					}
					if (detail.status === 'completed' && detail.adapted_cv) {
						store.update((s) => ({ ...s, status: 'completed', adaptation: detail }));
						return;
					}
					if (detail.status === 'failed') {
						store.update((s) => ({
							...s,
							status: 'failed',
							adaptation: detail,
							errorCode: detail.error_code ?? 'LLM_ERROR',
							errorMessage: detail.error_message ?? null
						}));
						return;
					}
				}
			}
			store.update((s) => ({
				...s,
				status: 'failed',
				errorCode: POLL_GIVE_UP_MESSAGE,
				errorMessage: null
			}));
		};
		inflight = run();
		try {
			await inflight;
		} finally {
			inflight = null;
		}
	}

	async function listAdaptationsForCv(cvId: number): Promise<AdaptationSummary[]> {
		try {
			return await apiClient.listAdaptationsForCv(cvId);
		} catch (err) {
			const { message } = readError(err);
			console.error(`[adaptation] listAdaptationsForCv(${cvId}) falló: ${message}`);
			return [];
		}
	}

	function reset() {
		store.set(initial);
	}

	return {
		subscribe: store.subscribe,
		createAdaptation,
		pollAdaptation,
		listAdaptationsForCv,
		reset
	};
}

export const adaptationStore = createAdaptationStore();
export const currentJob: Readable<number | null> = derived(
	adaptationStore,
	($s) => $s.jobId
);
