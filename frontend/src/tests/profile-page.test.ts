import { render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// /profile muestra: user info + onboarding + CV list. El mock cubre los
// métodos que la página llama al montar.
vi.mock('$api/client', () => ({
	apiClient: {
		createCvStructured: vi.fn(),
		createProfile: vi.fn(),
		deleteCv: vi.fn(),
		getCv: vi.fn(),
		getProfile: vi.fn(),
		listCvs: vi.fn().mockResolvedValue([]),
		updateCv: vi.fn(),
		uploadCv: vi.fn()
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
import ProfilePage from '../routes/profile/+page.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	vi.mocked(apiClient.listCvs).mockResolvedValue([]);
});

describe('profile page — estructura básica', () => {
	it('renderiza el heading y la info del usuario', async () => {
		render(ProfilePage);

		expect(await screen.findByRole('heading', { name: /mi perfil/i })).toBeTruthy();
		// El texto del usuario está partido en nodos por el interpolador i18n.
		expect(screen.getAllByText(/test@asistcv\.dev/i)[0]).toBeTruthy();
	});

	it('muestra la sección de CVs con la empty state cuando no hay ninguno', async () => {
		render(ProfilePage);

		expect(await screen.findByText(/mis cv/i)).toBeTruthy();
		// Texto i18n broken-up en nodos — se busca el fragmento único más robusto.
		expect(screen.getAllByText(/CV cargados/i)[0]).toBeTruthy();
	});

	it('renderiza los controles de subida de CV', async () => {
		render(ProfilePage);

		expect(await screen.findByText(/subir cv en pdf/i)).toBeTruthy();
		expect(screen.getByText(/crear cv con el editor estructurado/i)).toBeTruthy();
	});
});
