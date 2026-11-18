<script lang="ts">
	import { _ } from 'svelte-i18n';

	export let score: number;

	/**
	 * Constante compartida para el color del score:
	 *   rojo  < 50
	 *   amarillo 50–74
	 *   verde ≥ 75
	 * (Decisión cerrada en design.md §3)
	 */
	const RED_THRESHOLD = 50;
	const GREEN_THRESHOLD = 75;

	$: bucket = score < RED_THRESHOLD ? 'low' : score < GREEN_THRESHOLD ? 'mid' : 'high';
	$: clamped = Math.max(0, Math.min(100, Math.round(score)));
</script>

<div class="score score--{bucket}" aria-label={$_('result.scoreLabel')}>
	<div class="score__row">
		<span class="score__value">{clamped}</span>
		<span class="score__suffix">/100</span>
	</div>
	<div class="score__meter" role="presentation">
		<i style="width: {clamped}%"></i>
	</div>
	<span class="score__label">{$_('result.scoreLabel')}</span>
</div>

<style>
	/* El score es el protagonista del resultado: un número grande y una
	   medida. Ya no es un bloque de color — en una superficie oscura un
	   rectángulo rojo/verde compite con el contenido en vez de encabezarlo. */
	.score {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		min-width: 160px;
	}

	.score__row {
		display: flex;
		align-items: baseline;
		gap: var(--space-2);
	}

	.score__value {
		font-size: var(--text-6xl);
		font-weight: 650;
		line-height: 1;
		letter-spacing: var(--tracking-tighter);
	}

	.score--low .score__value {
		color: var(--score-low-ink);
	}

	.score--mid .score__value {
		color: var(--score-mid-ink);
	}

	.score--high .score__value {
		color: var(--score-high-ink);
	}

	.score__suffix {
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.score__meter {
		height: 4px;
		border-radius: var(--radius-pill);
		background: var(--color-surface-alt);
		overflow: hidden;
	}

	.score__meter i {
		display: block;
		height: 100%;
		border-radius: var(--radius-pill);
	}

	.score--low .score__meter i {
		background: var(--score-low);
	}

	.score--mid .score__meter i {
		background: var(--score-mid);
	}

	.score--high .score__meter i {
		background: var(--score-high);
	}

	.score__label {
		font-family: var(--font-mono);
		font-size: var(--text-2xs);
		letter-spacing: var(--tracking-widest);
		text-transform: uppercase;
		color: var(--color-ink-muted);
	}
</style>
