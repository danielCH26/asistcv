import { writable, type Writable } from 'svelte/store';
import { ApiError, type MatchAnalysis } from '$api/types';
import { apiClient } from '$api/client';

export type RequestStatus = 'idle' | 'loading' | 'error' | 'done';

export interface AnalysisState {
	status: RequestStatus;
	result: MatchAnalysis | null;
	error: string | null;
}

const initial: AnalysisState = {
	status: 'idle',
	result: null,
	error: null
};

function createAnalysisStore() {
	const store: Writable<AnalysisState> = writable(initial);

	async function submit(jdText: string, profileId: number): Promise<MatchAnalysis | null> {
		store.set({ status: 'loading', result: null, error: null });

		try {
			const result = await apiClient.match({ jd_text: jdText, profile_id: profileId });
			store.set({ status: 'done', result, error: null });
			return result;
		} catch (err) {
			const message = err instanceof ApiError ? err.message : 'Error inesperado';
			store.set({ status: 'error', result: null, error: message });
			return null;
		}
	}

	function reset() {
		store.set(initial);
	}

	return {
		subscribe: store.subscribe,
		submit,
		reset
	};
}

export const analysisStore = createAnalysisStore();