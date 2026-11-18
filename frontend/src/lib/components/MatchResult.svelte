<script lang="ts">
	import { _ } from 'svelte-i18n';
	import ScoreCard from './ScoreCard.svelte';
	import StrengthsGapsList from './StrengthsGapsList.svelte';
	import EnergyBadge from './EnergyBadge.svelte';
	import ReasoningBox from './ReasoningBox.svelte';
	import type { MatchAnalysis } from '$api/types';

	export let analysis: MatchAnalysis;
</script>

<article class="match-result">
	<header class="match-result__head">
		<span class="eyebrow">{$_('result.heading')}</span>
		<div class="match-result__meta">
			{#if analysis.mode}
				<span class="match-result__mode">
					{analysis.mode === 'retrieved' ? $_('result.modeRetrieved') : $_('result.modeComplete')}
					{#if analysis.mode === 'retrieved' && analysis.chunks_used != null}
						· {$_('result.chunksUsed', { values: { count: analysis.chunks_used } })}
					{/if}
				</span>
			{/if}
			<EnergyBadge level={analysis.energy_level} />
		</div>
	</header>

	<div class="match-result__body">
		<ScoreCard score={analysis.score} />
		<StrengthsGapsList strengths={analysis.strengths} gaps={analysis.gaps} />
	</div>

	<ReasoningBox text={analysis.reasoning} />
</article>

<style>
	.match-result {
		display: flex;
		flex-direction: column;
		gap: var(--space-5);
		background: var(--color-surface);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-panel);
		padding: var(--space-5);
	}

	.match-result__head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: var(--space-3);
		padding-bottom: var(--space-4);
		border-bottom: var(--border-width) solid var(--color-line);
	}

	.match-result__meta {
		display: flex;
		align-items: center;
		gap: var(--space-4);
	}

	.match-result__mode {
		font-size: var(--text-xs);
		color: var(--color-ink-muted);
	}

	/* El score va en una columna propia y el resto en la otra: el número se
	   lee de un vistazo y las razones se leen al lado, no debajo. */
	.match-result__body {
		display: grid;
		grid-template-columns: 160px 1fr;
		gap: var(--space-6);
		align-items: start;
	}

	@media (max-width: 640px) {
		.match-result__body {
			grid-template-columns: 1fr;
			gap: var(--space-5);
		}
	}
</style>
