#!/usr/bin/env node
/**
 * Verifica paridad de claves entre los catálogos i18n del frontend.
 *
 * Spec match-ui → "Cobertura i18n completa":
 *   WHEN se valida en CI, THEN todas las claves usadas en componentes tienen
 *        entrada en ambos idiomas, AND CI falla si falta alguna clave.
 *
 * Implementación:
 *   1. Lee `src/lib/i18n/locales/es.json` y `en.json`.
 *   2. Aplana cada objeto a un set de paths estilo "a.b.c".
 *   3. Compara los sets: claves que están en uno y faltan en el otro son error.
 *
 * El catálogo `es.json` es la fuente canónica (las specs están en español);
 * `en.json` debe espejar exactamente la misma estructura.
 *
 * Uso:
 *   node scripts/check-i18n-keys.mjs
 *
 * Exit codes:
 *   0 → paridad OK
 *   1 → faltan claves o hay claves con valores vacíos
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const LOCALES_DIR = resolve(__dirname, '..', 'src', 'lib', 'i18n', 'locales');
const SOURCE_LOCALE = 'es';
const REQUIRED_LOCALES = ['es', 'en'];

function flatten(obj, prefix = '', out = new Set()) {
	if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) {
		if (prefix) out.add(prefix);
		return out;
	}
	const entries = Object.entries(obj);
	if (entries.length === 0 && prefix) {
		out.add(prefix);
		return out;
	}
	for (const [key, value] of entries) {
		const next = prefix ? `${prefix}.${key}` : key;
		if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
			flatten(value, next, out);
		} else {
			out.add(next);
		}
	}
	return out;
}

function emptyLeafPaths(obj, prefix = '', out = []) {
	if (typeof obj !== 'object' || obj === null) {
		if (prefix && (obj === '' || obj === null || obj === undefined)) {
			out.push(prefix);
		}
		return out;
	}
	for (const [key, value] of Object.entries(obj)) {
		const next = prefix ? `${prefix}.${key}` : key;
		if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
			emptyLeafPaths(value, next, out);
		} else if (value === '' || value === null || value === undefined) {
			out.push(next);
		}
	}
	return out;
}

function diff(a, b) {
	const missingInB = [];
	for (const key of a) {
		if (!b.has(key)) missingInB.push(key);
	}
	return missingInB.sort();
}

function load(locale) {
	const path = resolve(LOCALES_DIR, `${locale}.json`);
	const raw = readFileSync(path, 'utf8');
	return JSON.parse(raw);
}

const failures = [];

const source = load(SOURCE_LOCALE);
const sourceKeys = flatten(source);

for (const locale of REQUIRED_LOCALES) {
	if (locale === SOURCE_LOCALE) continue;
	const target = load(locale);
	const targetKeys = flatten(target);

	const missingInTarget = diff(sourceKeys, targetKeys);
	const extraInTarget = diff(targetKeys, sourceKeys);

	if (missingInTarget.length > 0) {
		failures.push(`[${locale}] claves presentes en ${SOURCE_LOCALE}.json pero faltan en ${locale}.json:`);
		for (const key of missingInTarget) failures.push(`  - ${key}`);
	}
	if (extraInTarget.length > 0) {
		failures.push(`[${locale}] claves presentes en ${locale}.json pero NO existen en ${SOURCE_LOCALE}.json:`);
		for (const key of extraInTarget) failures.push(`  - ${key}`);
	}

	const empty = emptyLeafPaths(target);
	if (empty.length > 0) {
		failures.push(`[${locale}] valores vacíos en ${locale}.json:`);
		for (const key of empty) failures.push(`  - ${key}`);
	}
}

const emptyInSource = emptyLeafPaths(source);
if (emptyInSource.length > 0) {
	failures.push(`[${SOURCE_LOCALE}] valores vacíos en ${SOURCE_LOCALE}.json (canónico):`);
	for (const key of emptyInSource) failures.push(`  - ${key}`);
}

const totalKeys = sourceKeys.size;
console.log(`[i18n] ${SOURCE_LOCALE}.json tiene ${totalKeys} claves.`);

if (failures.length > 0) {
	console.error('\n[i18n] FAILED — corrija las siguientes diferencias:');
	for (const line of failures) console.error(line);
	process.exit(1);
}

console.log(`[i18n] OK — paridad verificada entre ${REQUIRED_LOCALES.join(', ')}.`);