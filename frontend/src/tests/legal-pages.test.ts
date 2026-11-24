import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';

// Las páginas legales no llaman al backend ni a stores de sesión: son
// contenido estático por idioma ($i18n/legal). El test cubre que cada ruta
// renderiza su documento, que las secciones numeradas existen y que los
// compromisos legales clave están presentes en el texto.
import CookiesPage from '../routes/cookies/+page.svelte';
import PrivacyPage from '../routes/privacy/+page.svelte';
import TermsPage from '../routes/terms/+page.svelte';
import { LEGAL_DOCS } from '$i18n/legal';

describe('páginas legales (locale por defecto: es)', () => {
	it('términos renderiza el documento con sus secciones numeradas', () => {
		render(TermsPage);

		expect(screen.getByRole('heading', { level: 1, name: LEGAL_DOCS.es.terms.title })).toBeTruthy();
		expect(screen.getByText(LEGAL_DOCS.es.terms.meta)).toBeTruthy();
		for (const section of LEGAL_DOCS.es.terms.sections) {
			expect(screen.getByRole('heading', { level: 2, name: section.title })).toBeTruthy();
		}
		expect(document.title).toBe(`eptus · ${LEGAL_DOCS.es.terms.title}`);
	});

	it('términos declara el retracto de 5 días hábiles y las pasarelas reales', () => {
		render(TermsPage);

		expect(screen.getByText(/cinco \(5\) días hábiles/i)).toBeTruthy();
		expect(screen.getByText(/Ley 1480 de 2011/i)).toBeTruthy();
		expect(screen.getByText(/Wompi y Mercado Pago/i)).toBeTruthy();
		expect(screen.getByText(/29\.000 COP\/mes/)).toBeTruthy();
	});

	it('privacidad renderiza la política con el marco de la Ley 1581', () => {
		render(PrivacyPage);

		expect(
			screen.getByRole('heading', { level: 1, name: LEGAL_DOCS.es.privacy.title })
		).toBeTruthy();
		// "Ley 1581" se menciona en intro, autorización y derechos: todas válidas.
		expect(screen.getAllByText(/Ley 1581 de 2012/i).length).toBeGreaterThan(0);
		// Los encargados del tratamiento son la lista que el backend usa de verdad.
		for (const processor of ['Neon', 'Render', 'Cloudflare', 'Groq', 'Resend']) {
			expect(screen.getAllByText(new RegExp(processor)).length).toBeGreaterThan(0);
		}
		// Los 30 días de la auditoría anónima vienen del modelo audit_uploads.
		expect(screen.getAllByText(/treinta \(30\) días/i).length).toBeGreaterThan(0);
	});

	it('cookies describe las claves reales de localStorage', () => {
		render(CookiesPage);

		expect(
			screen.getByRole('heading', { level: 1, name: LEGAL_DOCS.es.cookies.title })
		).toBeTruthy();
		expect(screen.getByText(/asistcv\.session/)).toBeTruthy();
		expect(screen.getByText(/asistcv\.audit_token/)).toBeTruthy();
	});

	it('el contenido en inglés existe para los tres documentos', () => {
		expect(LEGAL_DOCS.en.terms.title).toBe('Terms and Conditions');
		expect(LEGAL_DOCS.en.privacy.title).toBe('Privacy and Personal Data Processing Policy');
		expect(LEGAL_DOCS.en.cookies.title).toBe('Cookie and Local Storage Policy');
		for (const doc of [LEGAL_DOCS.en.terms, LEGAL_DOCS.en.privacy, LEGAL_DOCS.en.cookies]) {
			expect(doc.sections.length).toBeGreaterThan(0);
			expect(doc.meta).toContain('2026');
		}
	});
});
