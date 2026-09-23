// La página de detalle se resuelve en el cliente (SPA fallback).
// Nada que prerenderizar; el adapter-static sirve `index.html`.
export const ssr = false;
export const prerender = false;