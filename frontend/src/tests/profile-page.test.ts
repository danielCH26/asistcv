import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// /profile llama a estos métodos al montar y en cada sección. El mock cubre
// el inventario completo (ver feature doc L2) para que el mount no toque red.
vi.mock('$api/client', () => ({
	apiClient: {
		createCvStructured: vi.fn(),
		createProfile: vi.fn(),
		deleteCv: vi.fn(),
		getCv: vi.fn(),
		getProfile: vi.fn(),
		listCvs: vi.fn().mockResolvedValue([]),
		match: vi.fn(),
		updateCv: vi.fn(),
		uploadCv: vi.fn(),
		auditAnonymous: vi.fn(),
		captureAuditEmail: vi.fn()
	}
}));

// La página gatea todo el contenido detrás de requireSession() (client-side).
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
import type { MatchAnalysis } from '$api/types';
import ProfilePage from '../routes/profile/+page.svelte';

const mockedMatch = vi.mocked(apiClient.match);

const MATCH_RESULT: MatchAnalysis = {
	score: 72,
	strengths: ['Python'],
	gaps: ['SQL'],
	energy_level: 'high',
	reasoning: 'Buen match.'
};

beforeEach(() => {
	vi.clearAllMocks();
	vi.mocked(apiClient.listCvs).mockResolvedValue([]);
	// ensureProfile crea el perfil la primera vez; sin id resuelto, runMatch
	// nunca llega a apiClient.match.
	vi.mocked(apiClient.createProfile).mockResolvedValue({ id: 7 } as never);
});

const TAB_CV_VS_JD = /cv vs jd/i;
const TAB_CV_ONLY = /solo cv|cv only/i;
const JD_PLACEHOLDER =
	/descripci(o|ó)n (completa )?del puesto|descripci(o|ó)n completa de la vacante|full job description|job description/i;

/**
 * El textarea del JdForm vive dentro del tabpanel activo; la sección de
 * adaptación (fuera de los tabs) tiene su propio textarea con placeholder
 * parecido, así que todas las queries de JD se scopean al panel. El panel
 * sólo existe cuando la página pasó requireSession, así que se espera con
 * findBy antes de scoper.
 */
async function panel() {
	return within(await screen.findByRole('tabpanel'));
}

describe('profile page — tabs de análisis', () => {
	it('muestra dos tabs con CV vs JD activa por defecto', async () => {
		render(ProfilePage);

		const tab1 = await screen.findByRole('tab', { name: TAB_CV_VS_JD });
		const tab2 = screen.getByRole('tab', { name: TAB_CV_ONLY });
		expect(tab1.getAttribute('aria-selected')).toBe('true');
		expect(tab2.getAttribute('aria-selected')).toBe('false');
	});

	it('la tab CV vs JD muestra el input de JD (flujo match intacto)', async () => {
		render(ProfilePage);

		expect(await (await panel()).findByPlaceholderText(JD_PLACEHOLDER)).toBeTruthy();
	});

	it('cambiar a Solo CV oculta el input de JD y muestra su pista de modo', async () => {
		render(ProfilePage);

		await (await panel()).findByPlaceholderText(JD_PLACEHOLDER);
		await fireEvent.click(screen.getByRole('tab', { name: TAB_CV_ONLY }));

		expect(screen.getByRole('tab', { name: TAB_CV_ONLY }).getAttribute('aria-selected')).toBe(
			'true'
		);
		expect((await panel()).queryByPlaceholderText(JD_PLACEHOLDER)).toBeNull();
		expect(screen.getByText(/analiza tu cv|audits your cv/i)).toBeTruthy();
	});

	it('la tab CV vs JD sigue llamando apiClient.match con el JD pegado', async () => {
		mockedMatch.mockResolvedValueOnce(MATCH_RESULT);
		render(ProfilePage);

		const jd = await (await panel()).findByPlaceholderText(JD_PLACEHOLDER);
		await fireEvent.input(jd, { target: { value: 'x'.repeat(60) } });
		await fireEvent.click(screen.getByRole('button', { name: /analizar|analyze/i }));

		await waitFor(() => expect(mockedMatch).toHaveBeenCalledTimes(1));
		const payload = mockedMatch.mock.calls[0][0] as { jd_text: string };
		expect(payload.jd_text).toBe('x'.repeat(60));
	});
});
