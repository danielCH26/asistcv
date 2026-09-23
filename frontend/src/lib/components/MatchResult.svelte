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
	<header class="match-result__header">
		<ScoreCard score={analysis.score} />
		<div class="match-result__badges">
			<EnergyBadge level={analysis.energy_level} />
			{#if analysis.mode}
				<span class="match-result__mode">
					{analysis.mode === 'retrieved' ? $_('result.modeRetrieved') : $_('result.modeComplete')}
					{#if analysis.mode === 'retrieved' && analysis.chunks_used != null}
						· {$_('result.chunksUsed', { values: { count: analysis.chunks_used } })}
					{/if}
				</span>
			{/if}
		</div>
	</header>

	<StrengthsGapsList strengths={analysis.strengths} gaps={analysis.gaps} />
	<ReasoningBox text={analysis.reasoning} />
</article>

<style>
	.match-result {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1.5rem;
	}

	.match-result__header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 1rem;
	}

	.match-result__badges {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		align-items: flex-end;
	}

	.match-result__mode {
		font-size: 0.85rem;
		color: var(--text-muted);
	}
</style>