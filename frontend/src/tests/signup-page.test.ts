import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/navigation', () => ({
	goto: vi.fn().mockResolvedValue(undefined)
}));

import SignupPage from '../routes/signup/+page.svelte';

const ACCESS_TOKEN = `${btoa('{"alg":"HS256"}')}.${btoa(`{"exp":${Math.floor(Date.now() / 1000) + 900}}`)}.sig`;
const USER = { id: 3, email: 'r@corp.com', role: 'recruiter', full_name: 'Rita', locale: 'es' };

function stubAuthFetch(): ReturnType<typeof vi.fn> {
	const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
		const url = String(input);
		if (url.includes('/v1/users/me')) {
			return new Response(JSON.stringify(USER), { status: 200, headers: { 'Content-Type': 'application/json' } });
		}
		return new Response(
			JSON.stringify({ access_token: ACCESS_TOKEN, refresh_token: 'r1', token_type: 'bearer' }),
			{ status: 201, headers: { 'Content-Type': 'application/json' } }
		);
	});
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

function fillBasics() {
	fireEvent.input(screen.getAllByRole('textbox')[0], { target: { value: 'Rita Reclutadora' } });
	fireEvent.input(screen.getByLabelText(/email/i), { target: { value: 'r@corp.com' } });
	fireEvent.input(screen.getByLabelText(/contraseña/i), { target: { value: 'Passw0rd123' } });
}

beforeEach(() => {
	localStorage.clear();
	vi.unstubAllGlobals();
});

describe('signup page — consent gate del recruiter', () => {
	it('recruiter sin consentimiento → submit deshabilitado', async () => {
		render(SignupPage);

		const recruiterRadio = screen.getByRole('radio', { name: /reclutador/i });
		await fireEvent.click(recruiterRadio);

		const submit = screen.getByRole('button', { name: /crear cuenta/i }) as HTMLButtonElement;
		expect(submit.disabled).toBe(true);
	});

	it('recruiter con ambos consentimientos → llama a /v1/auth/register con el ToS', async () => {
		const fetchMock = stubAuthFetch();
		render(SignupPage);

		await fireEvent.click(screen.getByRole('radio', { name: /reclutador/i }));
		fillBasics();
		await fireEvent.click(screen.getByLabelText(/términos del servicio/i));
		await fireEvent.click(screen.getByLabelText(/buena fe/i));

		const submit = screen.getByRole('button', { name: /crear cuenta/i }) as HTMLButtonElement;
		expect(submit.disabled).toBe(false);
		await fireEvent.click(submit);

		await waitFor(() => expect(fetchMock).toHaveBeenCalled());
		const registerCall = fetchMock.mock.calls.find(([input]) => String(input).includes('/v1/auth/register'));
		expect(registerCall).toBeDefined();
		const body = JSON.parse((registerCall?.[1] as RequestInit).body as string);
		expect(body.role).toBe('recruiter');
		expect(body.accept_tos).toBe(true);
		expect(body.good_faith_declaration).toBe(true);
	});

	it('job_seeker no ve checkboxes de consentimiento y puede enviar directo', async () => {
		stubAuthFetch();
		render(SignupPage);

		expect(screen.queryByLabelText(/términos del servicio/i)).toBeNull();
		fillBasics();

		const submit = screen.getByRole('button', { name: /crear cuenta/i }) as HTMLButtonElement;
		expect(submit.disabled).toBe(false);
		await fireEvent.click(submit);

		await waitFor(() => expect(vi.mocked(globalThis.fetch)).toHaveBeenCalled());
		const registerCall = vi
			.mocked(globalThis.fetch)
			.mock.calls.find(([input]) => String(input).includes('/v1/auth/register'));
		const body = JSON.parse((registerCall?.[1] as RequestInit).body as string);
		expect(body.role).toBe('job_seeker');
	});
});
