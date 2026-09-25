import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$api/client', () => ({
	apiClient: {
		auditAnonymous: vi.fn(),
		captureAuditEmail: vi.fn()
	}
}));

import { apiClient } from '$api/client';
import { auditStore } from '$stores/audit';
import AuditPage from '../routes/audit/+page.svelte';

const mockedAudit = vi.mocked(apiClient.auditAnonymous);

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

async function fillJd() {
	const jd = screen.getByLabelText(/job description/i);
	await fireEvent.input(jd, { target: { value: 'x'.repeat(60) } });
}

async function selectPdf(name = 'cv.pdf') {
	const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
	const file = new File(['%PDF-1.4 test'], name, { type: 'application/pdf' });
	await fireEvent.change(fileInput, { target: { files: [file] } });
	return file;
}

describe('audit page — upload de PDF (default)', () => {
	it('con archivo seleccionado envía multipart con cv_file, no cv_text', async () => {
		mockedAudit.mockResolvedValueOnce(RESULT);
		render(AuditPage);

		await fillJd();
		const file = await selectPdf();
		await fireEvent.click(screen.getByRole('button', { name: /auditar mi cv/i }));

		await waitFor(() => expect(mockedAudit).toHaveBeenCalledTimes(1));
		const payload = mockedAudit.mock.calls[0][0];
		expect(payload.cv_file).toBe(file);
		expect(payload.cv_text).toBeUndefined();
	});

	it('muestra nombre y tamaño del archivo seleccionado', async () => {
		render(AuditPage);

		await selectPdf('mi-cv.pdf');

		expect(screen.getByText(/mi-cv\.pdf · \d+(\.\d+)? (KB|MB)/)).toBeTruthy();
	});

	it('422 PDF_NO_TEXT renderiza el mensaje de PDF sin texto', async () => {
		const { ApiError } = await import('$api/types');
		mockedAudit.mockRejectedValueOnce(new ApiError('scan', 422, '', 'PDF_NO_TEXT'));
		render(AuditPage);

		await fillJd();
		await selectPdf('scan.pdf');
		await fireEvent.click(screen.getByRole('button', { name: /auditar mi cv/i }));

		const alert = await screen.findByRole('alert');
		expect(alert.textContent).toMatch(/texto extraíble/i);
	});
});
