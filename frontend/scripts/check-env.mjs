/**
 * Pre-build guard: falla el build si PUBLIC_API_URL o
 * PUBLIC_CLERK_PUBLISHABLE_KEY no están definidas.
 * Se ejecuta antes de `vite build` para cumplir el scenario match-ui
 * "Build falla sin la env var".
 *
 * PUBLIC_CLERK_PUBLISHABLE_KEY es REQUIRED: sin ella el bundle de Clerk
 * arranca sin publishable key y el login muere con "Clerk keys are missing
 * from your environment" en runtime (fallo observado en prod, QA 2026-10).
 *
 * Además, falla si `PUBLIC_BACKEND_API_KEY` reaparece en `src/`:
 * la autenticación es por sesión JWT desde el sprint 2 y la API key
 * de build-time no debe volver al bundle (spec match-ui — guard G10).
 *
 * Y falla si `PUBLIC_BACKEND_API_KEY` está DEFINIDA en el entorno de build.
 * Ese caso es el queFwiltro en producción: con `adapter-static` las env
 * públicas viajan en `/_app/env.js`, que se sirve a cualquier visitante.
 * El grep sobre `src/` no lo detecta (la key no está en el código, está en
 * el entorno del host de build), pero el resultado es el mismo o peor: la
 * key de servicio del backend queda publicada y sirve para llamar a toda la
 * superficie protegida de `/v1`.
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const REQUIRED = ['PUBLIC_API_URL', 'PUBLIC_CLERK_PUBLISHABLE_KEY'];
const FORBIDDEN_KEY = 'PUBLIC_BACKEND_API_KEY';
const SRC_DIR = fileURLToPath(new URL('../src', import.meta.url));
const ROOT_DIR = fileURLToPath(new URL('..', import.meta.url));

/**
 * Lee una variable desde `process.env` y, si no está, desde los archivos
 * `.env` / `.env.local` del frontend (mismo criterio de precedencia que
 * Vite). Cloudflare Pages y CI inyectan las vars en `process.env`; en local
 * suelen vivir solo en `.env.local`.
 */
function readEnv(name) {
	const fromProcess = process.env[name];
	if (fromProcess && fromProcess.trim() !== '') return fromProcess.trim();

	for (const file of ['.env', '.env.local']) {
		const full = join(ROOT_DIR, file);
		if (!existsSync(full)) continue;
		for (const line of readFileSync(full, 'utf8').split('\n')) {
			const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
			if (!match || match[1] !== name) continue;
			const value = match[2].replace(/^["']|["']$/g, '').trim();
			if (value !== '') return value;
		}
	}
	return '';
}

function fail(missing) {
	console.error(`[AsistCV] Faltan variables de entorno requeridas para build: ${missing.join(', ')}`);
	console.error('Definí las env vars antes de ejecutar npm run build. Ver frontend/.env.example.');
	process.exit(1);
}

const missing = REQUIRED.filter((name) => readEnv(name) === '');

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

// La key puede colarse por el entorno de build (panel del host de build).
// Con `adapter-static` toda env `PUBLIC_*` se publica en `/_app/env.js`.
if (process.env[FORBIDDEN_KEY]) {
	console.error(
		`[AsistCV] ${FORBIDDEN_KEY} está definida en el entorno de build.\n` +
			`  Con adapter-static se publica en /_app/env.js y queda accesible a cualquier visitante.\n` +
			`  Quitala del entorno del host de build (Cloudflare Pages -> Settings -> Environment variables).\n` +
			`  La autenticación del frontend es exclusivamente por sesión Clerk/JWT.`
	);
	process.exit(1);
}

// Si el build ya existe, verificar el artefacto servido: la clave no puede
// estar en el bundle ni en el módulo de env público.
// Nota: la verificación del artefacto construido vive en `check-build.mjs`
// (postbuild). Aquí sólo se validan las ENTRADAS del build; leer un
// `build/` viejo desde el prebuild bloquearía builds legítimos.
console.log(
	`[AsistCV] env guard OK — ${REQUIRED.join(' y ')} definidas, sin ${FORBIDDEN_KEY} en el código ni en el entorno.`
);
process.exit(0);
