/**
 * Post-build guard: verifica el artefacto realmente publicado.
 *
 * `check-env.mjs` (prebuild) valida las ENTRADAS del build — el código
 * fuente y el entorno. Este script valida la SALIDA: lo que termina
 * sirviéndose a los visitantes.
 *
 * Con `@sveltejs/adapter-static` toda env `PUBLIC_*` se materializa en
 * `build/_app/env.js`, un archivo público. Si `PUBLIC_BACKEND_API_KEY` está
 * definida en el entorno de build, ese archivo la publica y cualquier
 * visitante puede extraer la key de servicio del backend y llamar a toda la
 * superficie protegida de `/v1` con ella.
 *
 * El grep sobre `src/` no lo detecta: la key no está en el código, está en
 * el entorno del host de build. Por eso el control tiene que mirar el
 * artefacto.
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const FORBIDDEN_KEY = 'PUBLIC_BACKEND_API_KEY';
const BUILD_DIR = fileURLToPath(new URL('../build', import.meta.url));

if (!existsSync(BUILD_DIR)) {
	console.error('[AsistCV] No existe build/ — el postbuild se ejecutó sin un build previo.');
	process.exit(1);
}

function walk(dir, files = []) {
	for (const entry of readdirSync(dir)) {
		const full = join(dir, entry);
		if (statSync(full).isDirectory()) {
			walk(full, files);
		} else {
			files.push(full);
		}
	}
	return files;
}

const offenders = walk(BUILD_DIR).filter((file) => {
	try {
		return readFileSync(file, 'utf8').includes(FORBIDDEN_KEY);
	} catch {
		return false;
	}
});

if (offenders.length > 0) {
	console.error(`[AsistCV] ${FORBIDDEN_KEY} aparece en el build publicado. Esos archivos se sirven a cualquier visitante:`);
	for (const file of offenders) console.error(`  - ${relative(BUILD_DIR, file)}`);
	console.error(
		`\n  Quitala del entorno del host de build (Cloudflare Pages -> Settings -> Environment variables)\n` +
			`  y rebuild. La autenticación del frontend es exclusivamente por sesión Clerk/JWT.`
	);
	process.exit(1);
}

console.log(`[AsistCV] build guard OK — sin ${FORBIDDEN_KEY} en el artefacto publicado.`);
process.exit(0);
