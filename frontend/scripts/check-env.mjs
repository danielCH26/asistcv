/**
 * Pre-build guard: falla el build si PUBLIC_API_URL no está definida.
 * Se ejecuta antes de `vite build` para cumplir el scenario match-ui
 * "Build falla sin la env var".
 *
 * PUBLIC_BACKEND_API_KEY puede quedar vacía (modo abierto del backend).
 */
import { spawnSync } from 'node:child_process';

const REQUIRED = ['PUBLIC_API_URL'];

function fail(missing) {
	console.error(`[AsistCV] Faltan variables de entorno requeridas para build: ${missing.join(', ')}`);
	console.error('Definí las env vars antes de ejecutar npm run build. Ver frontend/.env.example.');
	process.exit(1);
}

const missing = REQUIRED.filter((name) => {
	const value = process.env[name];
	return !value || value.trim() === '';
});

if (missing.length > 0) {
	fail(missing);
}

console.log('[AsistCV] env guard OK — PUBLIC_API_URL definido.');

// No continuar — sólo es guard; vite build se ejecuta después por npm.
process.exit(0);

// Referencia a spawnSync para que Vite/Node no marquen unused.
void spawnSync;