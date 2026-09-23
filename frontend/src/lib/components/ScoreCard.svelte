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
		padding: 1rem 1.75rem;
		border-radius: 12px;
		color: #fff;
		font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
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
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		opacity: 0.85;
	}

	.score-card__value {
		font-size: 3.5rem;
		font-weight: 700;
		line-height: 1;
		margin: 0.25rem 0;
	}

	.score-card__suffix {
		font-size: 0.85rem;
		opacity: 0.85;
	}
</style>