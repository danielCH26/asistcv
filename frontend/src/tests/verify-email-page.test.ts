import { render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// El link de verificación de email manda a /verify-email?token=... — una ruta
// que no existía: el link moría en un 404 y el usuario no podía confirmar su
// email (y sin email verificado el checkout devolvía 403).
vi.mock('$api/client', () => ({
	apiClient: {
		confirmEmailVerification: vi.fn()
	}
}));

import { apiClient } from '$api/client';
import { ApiError } from '$api/types';
import VerifyEmailPage from '../routes/verify-email/+page.svelte';

function setUrl(search: string): void {
	window.history.pushState({}, '', `/verify-email${search}`);
}

beforeEach(() => {
	vi.clearAllMocks();
	setUrl('');
});

describe('verify-email — página de confirmación', () => {
	it('confirma el email con el token del link', async () => {
		vi.mocked(apiClient.confirmEmailVerification).mockResolvedValue({ detail: 'Email verified' });
		setUrl('?token=token-crudo-123');

		render(VerifyEmailPage);

		await waitFor(() => {
			expect(apiClient.confirmEmailVerification).toHaveBeenCalledWith('token-crudo-123');
		});
		expect(await screen.findByText(/tu email quedó verificado/i)).toBeTruthy();
	});

	it('sin token en el link avisa y no llama a la API', async () => {
		setUrl('');

		render(VerifyEmailPage);

		await waitFor(() => {
			expect(screen.getByRole('alert')).toBeTruthy();
		});
		expect(apiClient.confirmEmailVerification).not.toHaveBeenCalled();
		expect(screen.getByText(/no trae el token de verificación/i)).toBeTruthy();
	});

	it('con un token inválido muestra el error', async () => {
		vi.mocked(apiClient.confirmEmailVerification).mockRejectedValue(
			new ApiError('Error: INVALID_TOKEN', 400, undefined, 'INVALID_TOKEN')
		);
		setUrl('?token=invalido');

		render(VerifyEmailPage);

		await waitFor(() => {
			expect(screen.getByRole('alert')).toBeTruthy();
		});
		expect(screen.getByText(/este link no es válido/i)).toBeTruthy();
	});
});
