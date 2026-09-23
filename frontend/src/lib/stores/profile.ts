import { writable, type Writable } from 'svelte/store';

/**
 * Store del perfil activo. En single-user asumimos `profile_id = 1`
 * por default (decisión cerrada en la propuesta). Cuando exista el
 * selector de perfil, este writable se reemplaza por la selección del
 * usuario sin cambiar la interfaz del resto de la app.
 */

const DEFAULT_PROFILE_ID = 1;
const STORAGE_KEY = 'asistcv.activeProfileId';

function loadInitial(): number {
	if (typeof localStorage === 'undefined') return DEFAULT_PROFILE_ID;
	const raw = localStorage.getItem(STORAGE_KEY);
	if (!raw) return DEFAULT_PROFILE_ID;
	const parsed = Number.parseInt(raw, 10);
	return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_PROFILE_ID;
}

function persist(value: number) {
	if (typeof localStorage === 'undefined') return;
	localStorage.setItem(STORAGE_KEY, String(value));
}

function createProfileStore() {
	const store: Writable<number> = writable(loadInitial());

	store.subscribe((value) => persist(value));

	function setProfile(id: number) {
		if (id > 0) {
			store.set(id);
		}
	}

	return {
		subscribe: store.subscribe,
		set: setProfile,
		reset() {
			store.set(DEFAULT_PROFILE_ID);
		}
	};
}

export const profileStore = createProfileStore();