// La página de detalle se resuelve en el cliente (SPA fallback).
// Nada que prerenderizar; el adapter-static sirve `index.html`.
export const ssr = false;
export const prerender = false;

// Devuelve el id del route param para que SvelteKit lo proyecte en
// `data`. Sin esto, `data` es `{}` y el bail-out de la página
// (parseInt de `''` → NaN) renderiza "Análisis no encontrado" en
// el 100% de las visitas (issue #86).
export function load({ params }: { params: { id: string } }) {
	return { id: params.id };
}