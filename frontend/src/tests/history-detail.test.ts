import { describe, expect, it } from 'vitest';
import { load } from '../routes/history/[id]/+page';

// Cubre #86: la página de detalle renderiza "Análisis no encontrado" en el
// 100% de las visitas porque el componente lee `data?.id`, pero `+page.ts`
// no exporta un `load` y `data` siempre llega `{}`. El fix es devolver el id
// del route param para que SvelteKit lo proyecte en `data`.

describe('history detail — +page load', () => {
	it('devuelve el id del route param', () => {
		expect(load({ params: { id: '42' } })).toEqual({ id: '42' });
	});

	it('devuelve el id aunque venga como string numérico', () => {
		expect(load({ params: { id: '4' } })).toEqual({ id: '4' });
	});

	it('no requiere mas campos en el resultado', () => {
		const result = load({ params: { id: '99' } });
		expect(result).toStrictEqual({ id: '99' });
	});
});