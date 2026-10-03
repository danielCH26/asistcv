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
</script>

<div class="score-card score-card--{bucket}" aria-label={$_('result.scoreLabel')}>
	<span class="score-card__label">{$_('result.scoreLabel')}</span>
	<span class="score-card__value">{Math.round(score)}</span>
	<span class="score-card__suffix">/100</span>
</div>

<style>
	.score-card {
		display: inline-flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--space-4) var(--space-6);
		border-radius: var(--radius-panel);
		color: var(--color-on-score-fill);
		font-family: var(--font-sans);
		min-width: 140px;
	}

	.score-card--low {
		background: var(--score-low);
	}

	.score-card--mid {
		background: var(--score-mid);
	}

	.score-card--high {
		background: var(--score-high);
	}

	.score-card__label {
		font-size: var(--text-sm);
		text-transform: uppercase;
		letter-spacing: var(--tracking-wide);
		opacity: 0.85;
	}

	.score-card__value {
		font-size: var(--text-6xl);
		font-weight: 700;
		line-height: var(--leading-tight);
		margin: var(--space-1) 0;
	}

	.score-card__suffix {
		font-size: var(--text-sm);
		opacity: 0.85;
	}
</style>