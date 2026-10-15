import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { type AdaptationDetail, type AdaptationSummary } from '$api/types';

vi.mock('$stores/adaptation', () => ({
	adaptationStore: {
		subscribe: vi.fn(),
		createAdaptation: vi.fn(),
		listAdaptationsForCv: vi.fn(),
		reset: vi.fn()
	}
}));

vi.mock('$api/client', () => ({
	apiClient: {
		listCvs: vi.fn()
	}
}));

vi.mock('$stores/session', async () => {
	const { writable } = await import('svelte/store');
	const session = writable({
		user: { id: 1, email: 'test@asistcv.dev', full_name: 'Test', role: 'job_seeker' }
	});
	return {
		session,
		requireSession: vi.fn().mockResolvedValue(true),
		isOnboarding: vi.fn().mockReturnValue(false),
		completeOnboarding: vi.fn()
	};
});

import { apiClient } from '$api/client';
import { adaptationStore } from '$stores/adaptation';
import AdaptPage from '../routes/adapt/+page.svelte';

const mockedListCvs = vi.mocked(apiClient.listCvs);
const mockedCreate = vi.mocked(adaptationStore.createAdaptation);
const mockedListAdapters = vi.mocked(adaptationStore.listAdaptationsForCv);
const mockedReset = vi.mocked(adaptationStore.reset);

// Helper: set adaptationStore subscription to return the given state.
function setAdaptationState(
	state: Partial<{
		status: 'idle' | 'pending' | 'completed' | 'failed';
		errorCode: string | null;
		errorMessage: string | null;
		adaptation: AdaptationDetail | null;
	}> = {}
) {
	vi.mocked(adaptationStore.subscribe).mockImplementation((run) => {
		run({
			status: state.status ?? 'idle',
			errorCode: state.errorCode ?? null,
			errorMessage: state.errorMessage ?? null,
			adaptation: state.adaptation ?? null,
			jobId: null
		});
		return () => {};
	});
}

const MOCK_CVS = [
	{ id: 7, original_filename: 'cv-original.pdf', last_edited_at: '2024-01-01T00:00:00Z' },
	{ id: 9, original_filename: 'cv-final.pdf', last_edited_at: '2024-06-15T00:00:00Z' }
];

beforeEach(() => {
	vi.clearAllMocks();
	mockedListCvs.mockResolvedValue([]);
	mockedCreate.mockResolvedValue(null);
	mockedListAdapters.mockResolvedValue([]);
	mockedReset.mockImplementation(() => {});
	setAdaptationState({ status: 'idle' });
});

describe('adapt page — renderizado básico', () => {
	it('muestra el heading y subtítulo', async () => {
		render(AdaptPage);

		expect(await screen.findByRole('heading', { name: /adaptá tu cv/i })).toBeTruthy();
		expect(screen.getByText(/reescribimos/i)).toBeTruthy();
	});

	it('muestra la empty state cuando no hay CVs cargados', async () => {
		render(AdaptPage);

		expect(await screen.findByText(/subí un cv primero/i)).toBeTruthy();
	});

	it('muestra el textarea de JD', async () => {
		render(AdaptPage);

		expect(await screen.findByPlaceholderText(/pegá acá la descripción/i)).toBeTruthy();
	});

	it('el botón submit está disabled cuando no hay CV seleccionado', async () => {
		render(AdaptPage);

		const btn = (await screen.findByRole('button', { name: /adaptar mi cv/i })) as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
	});
});

describe('adapt page — selector de CVs', () => {
	it('muestra los CVs del usuario cuando existen', async () => {
		mockedListCvs.mockResolvedValue(MOCK_CVS as never);
		mockedListAdapters.mockResolvedValue([]);

		render(AdaptPage);

		const select = (await screen.findByRole('combobox')) as HTMLSelectElement;
		expect(select.options[0].text).toBe('cv-original.pdf');
		expect(select.options[1].text).toBe('cv-final.pdf');
	});

	it('el botón submit sigue disabled hasta que se selecciona un CV', async () => {
		mockedListCvs.mockResolvedValue(MOCK_CVS as never);
		mockedListAdapters.mockResolvedValue([]);

		render(AdaptPage);

		const select = (await screen.findByRole('combobox')) as HTMLSelectElement;
		await fireEvent.change(select, { target: { value: '7' } });

		const btn = await screen.findByRole('button', { name: /adaptar mi cv/i });
		// Still disabled because JD text is too short
		expect((btn as HTMLButtonElement).disabled).toBe(true);
	});

	it('el botón submit se habilita cuando hay CV seleccionado y JD >= 50 chars', async () => {
		mockedListCvs.mockResolvedValue(MOCK_CVS as never);
		mockedListAdapters.mockResolvedValue([]);

		render(AdaptPage);

		const select = (await screen.findByRole('combobox')) as HTMLSelectElement;
		await fireEvent.change(select, { target: { value: '7' } });

		const textarea = await screen.findByPlaceholderText(/pegá acá la descripción/i);
		await fireEvent.input(textarea, { target: { value: 'x'.repeat(60) } });

		const btn = (await screen.findByRole('button', { name: /adaptar mi cv/i })) as HTMLButtonElement;
		expect(btn.disabled).toBe(false);
	});
});

describe('adapt page — submit', () => {
	it('llama a adaptationStore.createAdaptation al hacer submit', async () => {
		mockedListCvs.mockResolvedValue(MOCK_CVS as never);
		mockedListAdapters.mockResolvedValue([]);
		mockedCreate.mockResolvedValue(null);

		render(AdaptPage);

		const select = (await screen.findByRole('combobox')) as HTMLSelectElement;
		await fireEvent.change(select, { target: { value: '7' } });

		const textarea = await screen.findByPlaceholderText(/pegá acá la descripción/i);
		await fireEvent.input(textarea, { target: { value: 'x'.repeat(60) } });

		const btn = await screen.findByRole('button', { name: /adaptar mi cv/i });
		await fireEvent.click(btn);

		await waitFor(() =>
			expect(mockedCreate).toHaveBeenCalledWith(7, expect.stringContaining('x'))
		);
	});
});

describe('adapt page — estados del store', () => {
	it('muestra el spinner cuando el estado es pending', async () => {
		mockedListCvs.mockResolvedValue(MOCK_CVS as never);
		mockedListAdapters.mockResolvedValue([]);
		setAdaptationState({ status: 'pending' });

		render(AdaptPage);

		// El texto aparece dos veces (botón disabled + div con role=status);
		// basta con encontrar al menos uno.
		expect((await screen.findAllByText(/adaptando tu cv/i))[0]).toBeTruthy();
	});

	it('muestra el mensaje de upsell cuando el plan está agotado', async () => {
		mockedListCvs.mockResolvedValue(MOCK_CVS as never);
		mockedListAdapters.mockResolvedValue([]);
		setAdaptationState({
			status: 'failed',
			errorCode: 'PLAN_LIMIT_REACHED'
		});

		render(AdaptPage);

		expect(
			await screen.findByText(/alcanzaste el límite de adaptaciones/i)
		).toBeTruthy();
		expect(screen.getByText(/¿sin límite/i)).toBeTruthy();
	});

	it('muestra botón de retry cuando falla por error genérico', async () => {
		mockedListCvs.mockResolvedValue(MOCK_CVS as never);
		mockedListAdapters.mockResolvedValue([]);
		setAdaptationState({
			status: 'failed',
			errorCode: 'LLM_ERROR',
			errorMessage: 'boom'
		});

		render(AdaptPage);

		expect(await screen.findByRole('button', { name: /reintentar/i })).toBeTruthy();
	});

	it('el botón de retry llama a adaptationStore.reset()', async () => {
		mockedListCvs.mockResolvedValue(MOCK_CVS as never);
		mockedListAdapters.mockResolvedValue([]);
		setAdaptationState({
			status: 'failed',
			errorCode: 'LLM_ERROR',
			errorMessage: 'boom'
		});

		render(AdaptPage);

		const retryBtn = await screen.findByRole('button', { name: /reintentar/i });
		await fireEvent.click(retryBtn);

		expect(mockedReset).toHaveBeenCalledTimes(1);
	});
});
