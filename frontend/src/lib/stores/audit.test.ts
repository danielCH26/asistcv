import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$api/client', () => ({
	apiClient: {
		auditAnonymous: vi.fn(),
		captureAuditEmail: vi.fn()
	}
}));

import { apiClient } from '$api/client';
import { auditStore } from './audit';

const mockedAudit = vi.mocked(apiClient.auditAnonymous);
const mockedCapture = vi.mocked(apiClient.captureAuditEmail);

const RESULT = {
	audit_token: 'tok-123',
	score: 72,
	strengths: ['Python'],
	gaps: ['SQL'],
	energy_level: 'high',
	reasoning: 'Buen match general.'
};

beforeEach(() => {
	vi.clearAllMocks();
	auditStore.reset();
});

describe('auditStore', () => {
	it('bloquea JD corto sin llamar a la API', async () => {
		const result = await auditStore.submit('corto', 'cv');
		expect(result).toBeNull();
		expect(mockedAudit).not.toHaveBeenCalled();
		expect(get(auditStore).status).toBe('error');
	});

	it('submit exitoso expone el resultado para render', async () => {
		mockedAudit.mockResolvedValueOnce(RESULT);

		const result = await auditStore.submit('x'.repeat(60), 'mi cv de texto');
		expect(result).toEqual(RESULT);
		const state = get(auditStore);
		expect(state.status).toBe('done');
		expect(state.result?.score).toBe(72);
		expect(state.result?.strengths).toEqual(['Python']);
		expect(state.result?.gaps).toEqual(['SQL']);
	});

	it('429 con Retry-After queda expuesto para la UI', async () => {
		mockedAudit.mockRejectedValueOnce(
			new (await import('$api/types')).ApiError('rate', 429, '', 'RATE_LIMITED', 300)
		);

		await auditStore.submit('x'.repeat(60), '');
		const state = get(auditStore);
		expect(state.status).toBe('error');
		expect(state.retryAfter).toBe(300);
	});

	it('captureEmail usa el audit_token del resultado', async () => {
		mockedAudit.mockResolvedValueOnce(RESULT);
		mockedCapture.mockResolvedValueOnce({ message: 'ok' });

		await auditStore.submit('x'.repeat(60), '');
		const sent = await auditStore.captureEmail('ana@mail.com');

		expect(sent).toBe(true);
		expect(mockedCapture).toHaveBeenCalledWith('tok-123', 'ana@mail.com');
	});

	it('captureEmail falla si el backend rechaza', async () => {
		mockedAudit.mockResolvedValueOnce(RESULT);
		mockedCapture.mockRejectedValueOnce(new (await import('$api/types')).ApiError('expired', 410));

		await auditStore.submit('x'.repeat(60), '');
		const sent = await auditStore.captureEmail('ana@mail.com');
		expect(sent).toBe(false);
	});
});
