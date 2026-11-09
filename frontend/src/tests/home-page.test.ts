import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// La home resuelve el perfil propio antes de matchear: lo crea desde el CV
// del usuario si no hay uno (issue #132). Sin ese paso, `profileStore` se
// quedaba en null y el submit salía con un `return` silencioso — el botón
// "Analizar" no disparaba ninguna llamada.
vi.mock('$api/client', () => ({
	apiClient: {
		createProfile: vi.fn(),
		getCv: vi.fn(),
		getProfile: vi.fn(),
		listCvs: vi.fn().mockResolvedValue([]),
		match: vi.fn(),
		subscription: vi.fn().mockRejectedValue(new Error('sin suscripción'))
	}
}));

// `isAuthenticated` es un derived store en la versión Clerk; un writable con
// `true` cumple el mismo contrato para esta página.
vi.mock('$stores/session', async () => {
	const { writable } = await import('svelte/store');
	return {
		isAuthenticated: writable(true)
	};
});

import { apiClient } from '$api/client';
import { analysisStore } from '$stores/analysis';
import { profileStore } from '$stores/profile';
import HomePage from '../routes/+page.svelte';

const JD = 'Buscamos un Backend Engineer Senior con Python, FastAPI, PostgreSQL y Docker.';

const CV_SUMMARY = {
	id: 7,
	original_filename: 'cv.pdf',
	detected_locale: 'es',
	created_at: '2026-11-07T00:00:00Z',
	last_edited_at: '2026-11-07T00:00:00Z'
};

const CV_DETAIL = {
	...CV_SUMMARY,
	structured: {
		full_name: 'QA Tester',
		skills: ['Python', 'FastAPI'],
		experience: [{ title: 'Backend Engineer', company: 'Acme', years: '5' }],
		location: 'Bogotá'
	},
	raw_text: null
};

const MATCH = {
	score: 85,
	strengths: ['Python'],
	gaps: ['Kubernetes'],
	energy_level: 'high' as const,
	reasoning: 'Buen match'
};

async function submitJd(text = JD) {
	const textarea = document.getElementById('jd-text') as HTMLTextAreaElement;
	await fireEvent.input(textarea, { target: { value: text } });
	await fireEvent.click(screen.getByRole('button', { name: /analizar/i }));
}

beforeEach(() => {
	vi.clearAllMocks();
	localStorage.clear();
	profileStore.forget();
	analysisStore.reset();
	vi.mocked(apiClient.listCvs).mockResolvedValue([]);
	vi.mocked(apiClient.subscription).mockRejectedValue(new Error('sin suscripción'));
});

describe('home — resolución del perfil propio antes del match', () => {
	it('crea el perfil desde el CV y matchea con ese id', async () => {
		vi.mocked(apiClient.listCvs).mockResolvedValue([CV_SUMMARY]);
		vi.mocked(apiClient.getCv).mockResolvedValue(CV_DETAIL);
		vi.mocked(apiClient.createProfile).mockResolvedValue({ id: 42, name: 'QA Tester' });
		vi.mocked(apiClient.match).mockResolvedValue(MATCH);

		render(HomePage);
		await submitJd();

		await waitFor(() => {
			expect(apiClient.match).toHaveBeenCalledTimes(1);
		});

		expect(apiClient.createProfile).toHaveBeenCalledTimes(1);
		expect(apiClient.createProfile).toHaveBeenCalledWith({
			name: 'QA Tester',
			headline: null,
			experience: { items: [{ title: 'Backend Engineer', company: 'Acme', years: '5' }] },
			skills: { items: ['Python', 'FastAPI'] },
			preferences: { location: 'Bogotá' }
		});
		expect(apiClient.match).toHaveBeenCalledWith({ jd_text: JD.trim(), profile_id: 42 });
		expect(getProfileId()).toBe(42);
	});

	it('reusa el perfil cacheado si sigue siendo del usuario', async () => {
		profileStore.set(9);
		vi.mocked(apiClient.getProfile).mockResolvedValue({ id: 9, name: 'QA Tester' });
		vi.mocked(apiClient.match).mockResolvedValue(MATCH);

		render(HomePage);
		await submitJd();

		await waitFor(() => {
			expect(apiClient.match).toHaveBeenCalledWith({ jd_text: JD.trim(), profile_id: 9 });
		});
		expect(apiClient.createProfile).not.toHaveBeenCalled();
	});

	it('olvida un perfil cacheado que ya no es del usuario y crea otro', async () => {
		profileStore.set(9);
		vi.mocked(apiClient.getProfile).mockRejectedValue(new Error('404'));
		vi.mocked(apiClient.listCvs).mockResolvedValue([CV_SUMMARY]);
		vi.mocked(apiClient.getCv).mockResolvedValue(CV_DETAIL);
		vi.mocked(apiClient.createProfile).mockResolvedValue({ id: 42, name: 'QA Tester' });
		vi.mocked(apiClient.match).mockResolvedValue(MATCH);

		render(HomePage);
		await submitJd();

		await waitFor(() => {
			expect(apiClient.match).toHaveBeenCalledWith({ jd_text: JD.trim(), profile_id: 42 });
		});
		expect(apiClient.createProfile).toHaveBeenCalledTimes(1);
	});

	it('sin CV no matchea: avisa con el CTA en vez de fallar en silencio', async () => {
		vi.mocked(apiClient.listCvs).mockResolvedValue([]);

		render(HomePage);
		await submitJd();

		await waitFor(() => {
			expect(screen.getByTestId('home-setup-error')).toBeTruthy();
		});

		expect(apiClient.match).not.toHaveBeenCalled();
		expect(apiClient.createProfile).not.toHaveBeenCalled();
		expect(screen.getByText(/necesitás un cv cargado/i)).toBeTruthy();
		const alert = screen.getByTestId('home-setup-error');
		expect(within(alert).getByRole('link', { name: /configurá tu perfil/i })).toBeTruthy();
	});
});

function getProfileId(): number | null {
	let value: number | null = null;
	const unsubscribe = profileStore.subscribe((v) => (value = v));
	unsubscribe();
	return value;
}
