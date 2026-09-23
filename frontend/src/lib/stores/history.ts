import { writable, derived, type Readable, type Writable } from 'svelte/store';
import { ApiError, type AnalysisDetail, type AnalysisSummary } from '$api/types';
import { apiClient } from '$api/client';

export type HistoryStatus = 'idle' | 'loading' | 'error' | 'done';

export interface HistoryState {
	status: HistoryStatus;
	items: AnalysisSummary[];
	limit: number;
	offset: number;
	total: number;
	error: string | null;
}

const DEFAULT_LIMIT = 20;

function createHistoryStore() {
	const store: Writable<HistoryState> = writable({
		status: 'idle',
		items: [],
		limit: DEFAULT_LIMIT,
		offset: 0,
		total: 0,
		error: null
	});

	async function load(params: { limit?: number; offset?: number; profileId?: number } = {}): Promise<void> {
		const limit = params.limit ?? DEFAULT_LIMIT;
		const offset = params.offset ?? 0;

		store.update((s) => ({ ...s, status: 'loading', error: null }));

		try {
			const items = await apiClient.listAnalyses({ limit, offset, profileId: params.profileId });
			store.update((s) => ({
				...s,
				status: 'done',
				items,
				limit,
				offset,
				total: items.length,
				error: null
			}));
		} catch (err) {
			const message = err instanceof ApiError ? err.message : 'Error inesperado';
			store.update((s) => ({ ...s, status: 'error', error: message }));
		}
	}

	function reset() {
		store.set({
			status: 'idle',
			items: [],
			limit: DEFAULT_LIMIT,
			offset: 0,
			total: 0,
			error: null
		});
	}

	return {
		subscribe: store.subscribe,
		load,
		reset
	};
}

export const historyStore = createHistoryStore();

export const hasMore: Readable<boolean> = derived(historyStore, ($h) => $h.items.length >= $h.limit && $h.offset + $h.limit <= 200);

export async function loadAnalysisDetail(id: number): Promise<AnalysisDetail | null> {
	try {
		return await apiClient.getAnalysis(id);
	} catch (err) {
		if (err instanceof ApiError) {
			console.error(`[history] detalle ${id} falló: ${err.message}`);
		}
		return null;
	}
}