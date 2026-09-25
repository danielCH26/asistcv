import { describe, expect, it } from 'vitest';
import { canSubmitSignup, homeForRole, isPasswordValid } from './rules';

describe('canSubmitSignup', () => {
	it('job_seeker no requiere consentimiento', () => {
		expect(canSubmitSignup({ role: 'job_seeker', acceptTos: false, goodFaith: false })).toBe(true);
	});

	it('recruiter sin checkboxes → bloqueado', () => {
		expect(canSubmitSignup({ role: 'recruiter', acceptTos: false, goodFaith: false })).toBe(false);
	});

	it('recruiter con sólo un checkbox → bloqueado', () => {
		expect(canSubmitSignup({ role: 'recruiter', acceptTos: true, goodFaith: false })).toBe(false);
		expect(canSubmitSignup({ role: 'recruiter', acceptTos: false, goodFaith: true })).toBe(false);
	});

	it('recruiter con ambos checkboxes → habilitado', () => {
		expect(canSubmitSignup({ role: 'recruiter', acceptTos: true, goodFaith: true })).toBe(true);
	});
});

describe('isPasswordValid', () => {
	it('rechaza corta, sin mayúscula, sin minúscula o sin dígito', () => {
		expect(isPasswordValid('Ab1defg')).toBe(false);
		expect(isPasswordValid('abcdefg123')).toBe(false);
		expect(isPasswordValid('ABCDEFG123')).toBe(false);
		expect(isPasswordValid('Abcdefg123')).toBe(true);
	});
});

describe('homeForRole', () => {
	it('recruiter → /recruiter, seeker → /profile', () => {
		expect(homeForRole('recruiter')).toBe('/recruiter');
		expect(homeForRole('job_seeker')).toBe('/profile');
	});
});
