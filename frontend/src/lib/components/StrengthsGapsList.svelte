<script lang="ts">
	import { _ } from 'svelte-i18n';

	export let strengths: string[] = [];
	export let gaps: string[] = [];
</script>

<div class="strengths-gaps">
	<section class="strengths-gaps__panel">
		<h3 class="strengths-gaps__heading strengths-gaps__heading--strength">{$_('result.strengths')}</h3>
		{#if strengths.length === 0}
			<p class="strengths-gaps__empty">—</p>
		{:else}
			<ul class="strengths-gaps__list">
				{#each strengths as item}
					<li>{item}</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section class="strengths-gaps__panel">
		<h3 class="strengths-gaps__heading strengths-gaps__heading--gap">{$_('result.gaps')}</h3>
		{#if gaps.length === 0}
			<p class="strengths-gaps__empty">—</p>
		{:else}
			<ul class="strengths-gaps__list">
				{#each gaps as item}
					<li>{item}</li>
				{/each}
			</ul>
		{/if}
	</section>
</div>

<style>
	.strengths-gaps {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-4);
	}

	.strengths-gaps__panel {
		background: var(--color-surface);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-card-lg);
		padding: var(--space-4);
	}

	.strengths-gaps__heading {
		margin: 0 0 var(--space-2);
		font-size: var(--text-sm);
		text-transform: uppercase;
		letter-spacing: var(--tracking-wide);
	}

	.strengths-gaps__heading--strength {
		color: var(--score-high-ink);
	}

	.strengths-gaps__heading--gap {
		color: var(--color-warning);
	}

	.strengths-gaps__list {
		margin: 0;
		padding-left: var(--space-4);
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.strengths-gaps__empty {
		margin: 0;
		color: var(--color-ink-muted);
	}

	@media (max-width: 640px) {
		.strengths-gaps {
			grid-template-columns: 1fr;
		}
	}
</style>