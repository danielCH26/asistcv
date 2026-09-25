import type { Role } from '$api/types';

/**
 * Reglas de negocio del signup (spec user-accounts §6.1).
 * Extraídas a un módulo puro para poder testearlas sin montar el componente.
 */

export const TOS_VERSION = '2025-sprint2';

export interface SignupFormInput {
	role: Role;
	acceptTos: boolean;
	goodFaith: boolean;
}

/** El recruiter debe aceptar el ToS y la declaración de buena fe; el seeker no. */
export function canSubmitSignup(input: SignupFormInput): boolean {
	if (input.role !== 'recruiter') return true;
	return input.acceptTos && input.goodFaith;
}

/** Password ≥10 con mayúscula, minúscula y dígito (mirror del backend). */
export function isPasswordValid(password: string): boolean {
	return (
		password.length >= 10 &&
		/[A-Z]/.test(password) &&
		/[a-z]/.test(password) &&
		/\d/.test(password)
	);
}

/** Redirección post-login/registro según rol. */
export function homeForRole(role: Role): string {
	return role === 'recruiter' ? '/recruiter' : '/profile';
}
