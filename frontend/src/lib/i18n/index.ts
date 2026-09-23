import { addMessages, init, locale } from 'svelte-i18n';
import { browser } from '$app/environment';
import en from './locales/en.json';
import es from './locales/es.json';

const STORAGE_KEY = 'asistcv.locale';
const SUPPORTED = ['es', 'en'] as const;
type SupportedLocale = typeof SUPPORTED[number];

function detectInitial(): SupportedLocale {
	if (browser) {
		const stored = localStorage.getItem(STORAGE_KEY);
		if (stored && (SUPPORTED as readonly string[]).includes(stored)) {
			return stored as SupportedLocale;
		}
		const navLang = (navigator.language ?? 'es').slice(0, 2).toLowerCase();
		if (navLang === 'en') return 'en';
	}
	return 'es';
}

let initialized = false;

export function setupI18n() {
	if (initialized) return;
	initialized = true;

	addMessages('es', es);
	addMessages('en', en);

	init({
		fallbackLocale: 'es',
		initialLocale: detectInitial()
	});
}

export function setLocale(value: SupportedLocale) {
	if (!(SUPPORTED as readonly string[]).includes(value)) return;
	locale.set(value);
	if (browser) {
		localStorage.setItem(STORAGE_KEY, value);
	}
}

export function toggleLocale() {
	let current: string = 'es';
	const unsub = locale.subscribe((v) => (current = v ?? 'es'));
	unsub();
	setLocale(current === 'es' ? 'en' : 'es');
}

export const SUPPORTED_LOCALES = SUPPORTED;