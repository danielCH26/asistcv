import { writable, type Writable } from 'svelte/store';

/**
 * Store del perfil activo.
 *
 * El valor es `number | null`: `null` significa "todavía no sabemos qué
 * perfil es de este usuario". Antes este store hardcodeaba `1`, lo que
 * hacía que TODO usuario matcheara contra el perfil de otro (issue #85):
 * el backend no tenía filtro de ownership y el frontend siempre pedía el
 * id 1. Ningún id puede darse por bueno sin verificar que el llamador lo
 * posea — el backend devuelve 404 para un perfil ajeno, y ese 404 es
 * justamente la señal para olvidar el id cacheado.
 *
 * El id se persiste para no crear un perfil nuevo en cada visita, pero
 * siempre se valida antes de usarse (ver `ensureProfile` en la página de
 * perfil, que es quien resuelve y, si hace falta, crea el perfil propio).
 */
const STORAGE_KEY = 'asistcv.activeProfileId';

function loadInitial(): number | null {
	if (typeof localStorage === 'undefined') return null;
	const raw = localStorage.getItem(STORAGE_KEY);
	if (!raw) return null;
	const parsed = Number.parseInt(raw, 10);
	return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function persist(value: number | null) {
	if (typeof localStorage === 'undefined') return;
	if (value === null) {
		localStorage.removeItem(STORAGE_KEY);
		return;
	}
	localStorage.setItem(STORAGE_KEY, String(value));
}

function createProfileStore() {
	const store: Writable<number | null> = writable(loadInitial());

	store.subscribe((value) => persist(value));

	function setProfile(id: number) {
		if (id > 0) {
			store.set(id);
		}
	}

	return {
		subscribe: store.subscribe,
		set: setProfile,
		/**
		 * Olvida el id cacheado. Se llama cuando el backend responde 404:
		 * o el perfil ya no existe, o pertenece a otro usuario. En ambos
		 * casos dejarlo guardado haría que el usuario volviera a apuntar al
		 * perfil equivocado.
		 */
		forget() {
			store.set(null);
		},
		reset() {
			store.set(null);
		}
	};
}

export const profileStore = createProfileStore();
