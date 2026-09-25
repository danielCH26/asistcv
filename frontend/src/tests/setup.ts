import { cleanup } from '@testing-library/svelte';
import { afterEach } from 'vitest';
import { setupI18n } from '$i18n/index';

// jsdom reporta navigator.language 'en-US': fijamos el catálogo canónico
// (es) antes de inicializar svelte-i18n (detectInitial lee localStorage).
localStorage.setItem('asistcv.locale', 'es');
setupI18n();

afterEach(() => {
	cleanup();
	localStorage.clear();
	sessionStorage.clear();
});
