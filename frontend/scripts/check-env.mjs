/**
 * Pre-build guard: falla el build si PUBLIC_API_URL no está definida.
 * Se ejecuta antes de `vite build` para cumplir el scenario match-ui
 * "Build falla sin la env var".
 *
 * Además, falla si `PUBLIC_BACKEND_API_KEY` reaparece en `src/`:
 * la autenticación es por sesión JWT desde el sprint 2 y la API key
 * de build-time no debe volver al bundle (spec match-ui — guard G10).
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const REQUIRED = ['PUBLIC_API_URL'];
const FORBIDDEN_KEY = 'PUBLIC_BACKEND_API_KEY';
const SRC_DIR = fileURLToPath(new URL('../src', import.meta.url));

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

function walk(dir, files = []) {
	for (const entry of readdirSync(dir)) {
		const full = join(dir, entry);
		if (statSync(full).isDirectory()) {
			walk(full, files);
		} else if (/\.(ts|js|svelte|json)$/.test(entry)) {
			files.push(full);
		}
	}
	return files;
}

const offenders = walk(SRC_DIR).filter((file) => readFileSync(file, 'utf8').includes(FORBIDDEN_KEY));
if (offenders.length > 0) {
	console.error(`[AsistCV] ${FORBIDDEN_KEY} reapareció en el código del frontend (sesión JWT es la única auth):`);
	for (const file of offenders) console.error(`  - ${file}`);
	process.exit(1);
}

console.log('[AsistCV] env guard OK — PUBLIC_API_URL definido, sin API key en el código.');
process.exit(0);
