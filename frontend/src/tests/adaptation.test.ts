import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';

vi.mock('$app/navigation', () => ({
	goto: vi.fn().mockResolvedValue(undefined)
}));

vi.mock('$api/client', async (importOriginal) => {
	const actual = await importOriginal<typeof import('$api/client')>();
	return {
		apiClient: {
			...actual.apiClient,
			createAdaptation: vi.fn(),
			getAdaptation: vi.fn(),
			listAdaptationsForCv: vi.fn()
		}
	};
});

import { apiClient } from '$api/client';
import { ApiError, type AdaptationDetail, type AdaptationSummary } from '$api/types';
import { adaptationStore } from '$stores/adaptation';
import AdaptationResult from '$components/AdaptationResult.svelte';

const mockedCreate = vi.mocked(apiClient.createAdaptation);
const mockedGet = vi.mocked(apiClient.getAdaptation);
const mockedList = vi.mocked(apiClient.listAdaptationsForCv);

const ADAPTED_CV = {
	full_name: 'Ana Pérez',
	experience: [
		{
			title: 'Senior Backend Engineer',
			company: 'Acme Corp',
			dates: '2021 — Presente',
			description: 'Diseñé servicios en Python sobre AWS Lambda.'
		}
	],
	skills: ['Python', 'AWS', 'PostgreSQL']
};

function makeCompleted(id = 42): AdaptationDetail {
	return {
		id,
		cv_id: 7,
		jd_text_hash: 'h-1',
		status: 'completed',
		adapted_cv: ADAPTED_CV,
		error_code: null,
		error_message: null,
		created_at: '2024-01-01T00:00:00Z',
		completed_at: '2024-01-01T00:00:10Z'
	};
}

function makePending(id = 42): AdaptationDetail {
	return {
		id,
		cv_id: 7,
		jd_text_hash: 'h-1',
		status: 'pending',
		adapted_cv: null,
		error_code: null,
		error_message: null,
		created_at: '2024-01-01T00:00:00Z',
		completed_at: null
	};
}

beforeEach(() => {
	vi.clearAllMocks();
	adaptationStore.reset();
	vi.useRealTimers();
});

// === Store ===

describe('adaptationStore.createAdaptation', () => {
	it('idle → pending → completed con polling feliz', async () => {
		mockedCreate.mockResolvedValueOnce({ adaptation_id: 42, status: 'pending' });
		mockedGet
			.mockResolvedValueOnce(makePending(42))
			.mockResolvedValueOnce(makeCompleted(42));

		const promise = adaptationStore.createAdaptation(7, 'Necesito un backend Python con AWS');

		await waitFor(() => expect(get(adaptationStore).status).toBe('completed'), { timeout: 6000 });

		const result = await promise;
		expect(result?.adapted_cv?.full_name).toBe('Ana Pérez');
		expect(mockedCreate).toHaveBeenCalledWith({ cv_id: 7, jd_text: expect.any(String) });
		expect(mockedGet).toHaveBeenCalledTimes(2);
	});

	it('error 402 PLAN_LIMIT_REACHED expone errorCode para upsell', async () => {
		mockedCreate.mockRejectedValueOnce(new ApiError('limit', 402, '', 'PLAN_LIMIT_REACHED'));

		const result = await adaptationStore.createAdaptation(7, 'JD corto de prueba');
		expect(result).toBeNull();
		const state = get(adaptationStore);
		expect(state.status).toBe('failed');
		expect(state.errorCode).toBe('PLAN_LIMIT_REACHED');
		expect(state.adaptation).toBeNull();
	});

	it('error genérico expone errorMessage en el estado', async () => {
		mockedCreate.mockRejectedValueOnce(new ApiError('boom', 500, 'server boom'));

		await adaptationStore.createAdaptation(7, 'JD corto de prueba');
		const state = get(adaptationStore);
		expect(state.status).toBe('failed');
		expect(state.errorCode).toBeNull();
		expect(state.errorMessage).toBe('boom');
	});

	it('runner failed (LLM_ERROR) queda capturado con error_code del backend', async () => {
		mockedCreate.mockResolvedValueOnce({ adaptation_id: 99, status: 'pending' });
		const failed: AdaptationDetail = {
			id: 99,
			cv_id: 7,
			jd_text_hash: 'h',
			status: 'failed',
			adapted_cv: null,
			error_code: 'LLM_ERROR',
			error_message: 'rate limit',
			created_at: '2024-01-01T00:00:00Z',
			completed_at: '2024-01-01T00:00:10Z'
		};
		mockedGet.mockResolvedValueOnce(failed);

		await adaptationStore.createAdaptation(7, 'JD corto de prueba');

		await waitFor(() => expect(get(adaptationStore).status).toBe('failed'), { timeout: 6000 });
		const state = get(adaptationStore);
		expect(state.errorCode).toBe('LLM_ERROR');
	});

	it('reset() vuelve al estado idle', () => {
		adaptationStore.reset();
		expect(get(adaptationStore).status).toBe('idle');
		expect(get(adaptationStore).jobId).toBeNull();
		expect(get(adaptationStore).adaptation).toBeNull();
	});
});

describe('adaptationStore.listAdaptationsForCv', () => {
	it('devuelve el listado para un CV', async () => {
		const summaries: AdaptationSummary[] = [
			{
				id: 1,
				cv_id: 7,
				jd_text_hash: 'h',
				status: 'completed',
				error_code: null,
				created_at: '2024-01-01T00:00:00Z',
				completed_at: '2024-01-01T00:00:10Z'
			}
		];
		mockedList.mockResolvedValueOnce(summaries);
		const result = await adaptationStore.listAdaptationsForCv(7);
		expect(result).toEqual(summaries);
		expect(mockedList).toHaveBeenCalledWith(7);
	});

	it('silencia errores y devuelve [] (la UI muestra su propio error)', async () => {
		mockedList.mockRejectedValueOnce(new ApiError('boom', 500));
		const result = await adaptationStore.listAdaptationsForCv(7);
		expect(result).toEqual([]);
	});
});

// === Componente ===

describe('AdaptationResult.svelte', () => {
	it('renderiza nombre, skills y experiencia adaptados', () => {
		render(AdaptationResult, { adapted: ADAPTED_CV });

		expect(screen.getByRole('heading', { name: 'Ana Pérez' })).toBeTruthy();
		expect(screen.getByText('Python')).toBeTruthy();
		expect(screen.getByText('AWS')).toBeTruthy();
		expect(screen.getByText('Senior Backend Engineer')).toBeTruthy();
		expect(screen.getByText('Acme Corp')).toBeTruthy();
		expect(screen.getByText('2021 — Presente')).toBeTruthy();
		expect(screen.getByText(/Diseñé servicios en Python sobre AWS Lambda\./)).toBeTruthy();
	});

	it('muestra fallback — cuando no hay skills ni experiencia', () => {
		render(AdaptationResult, {
			adapted: { full_name: 'Solo', experience: [], skills: [] }
		});
		expect(screen.getByRole('heading', { name: 'Solo' })).toBeTruthy();
		expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
	});
});

// === Client (sin mock — usa fetch stub) ===

describe('apiClient — adaptations', () => {
	beforeEach(() => {
		vi.unstubAllGlobals();
		vi.resetModules();
	});

	it('createAdaptation hace POST /v1/adaptations con cv_id y jd_text', async () => {
		const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
			const url = String(input);
			if (url.endsWith('/v1/adaptations') && init?.method === 'POST') {
				return new Response(JSON.stringify({ adaptation_id: 10, status: 'pending' }), {
					status: 202,
					headers: { 'Content-Type': 'application/json' }
				});
			}
			throw new Error(`unexpected fetch: ${url}`);
		});
		vi.stubGlobal('fetch', fetchMock);

		const real = await vi.importActual<typeof import('$api/client')>('$api/client');
		const result = await real.apiClient.createAdaptation({ cv_id: 5, jd_text: 'mi jd' });

		expect(result).toEqual({ adaptation_id: 10, status: 'pending' });
		const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toContain('/v1/adaptations');
		expect(init.method).toBe('POST');
		expect(JSON.parse(init.body as string)).toEqual({ cv_id: 5, jd_text: 'mi jd' });
	});

	it('getAdaptation hace GET /v1/adaptations/{id}', async () => {
		const detail = makeCompleted(55);
		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			const url = String(input);
			if (url.endsWith('/v1/adaptations/55')) {
				return new Response(JSON.stringify(detail), {
					status: 200,
					headers: { 'Content-Type': 'application/json' }
				});
			}
			throw new Error(`unexpected fetch: ${url}`);
		});
		vi.stubGlobal('fetch', fetchMock);

		const real = await vi.importActual<typeof import('$api/client')>('$api/client');
		const result = await real.apiClient.getAdaptation(55);

		expect(result.id).toBe(55);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it('listAdaptationsForCv hace GET /v1/adaptations/by-cv/{cvId}', async () => {
		const summaries: AdaptationSummary[] = [];
		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			const url = String(input);
			if (url.endsWith('/v1/adaptations/by-cv/9')) {
				return new Response(JSON.stringify(summaries), {
					status: 200,
					headers: { 'Content-Type': 'application/json' }
				});
			}
			throw new Error(`unexpected fetch: ${url}`);
		});
		vi.stubGlobal('fetch', fetchMock);

		const real = await vi.importActual<typeof import('$api/client')>('$api/client');
		const result = await real.apiClient.listAdaptationsForCv(9);

		expect(result).toEqual([]);
		const [url] = fetchMock.mock.calls[0] as unknown as [string];
		expect(url).toContain('/v1/adaptations/by-cv/9');
	});

	it('propaga ApiError cuando el backend rechaza (404 NO_CV_FOUND)', async () => {
		const fetchMock = vi.fn(async () =>
			new Response(JSON.stringify({ detail: 'NO_CV_FOUND' }), {
				status: 404,
				headers: { 'Content-Type': 'application/json' }
			})
		);
		vi.stubGlobal('fetch', fetchMock);

		const real = await vi.importActual<typeof import('$api/client')>('$api/client');
		await expect(real.apiClient.createAdaptation({ cv_id: 1, jd_text: 'x' })).rejects.toMatchObject({
			status: 404,
			code: 'NO_CV_FOUND'
		});
	});
});
