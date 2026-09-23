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
		gap: 1rem;
	}

	.strengths-gaps__panel {
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 1rem;
	}

	.strengths-gaps__heading {
		margin: 0 0 0.5rem;
		font-size: 0.95rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.strengths-gaps__heading--strength {
		color: var(--score-high);
	}

	.strengths-gaps__heading--gap {
		color: var(--warn);
	}

	.strengths-gaps__list {
		margin: 0;
		padding-left: 1.1rem;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.strengths-gaps__empty {
		margin: 0;
		color: var(--text-muted);
	}

	@media (max-width: 640px) {
		.strengths-gaps {
			grid-template-columns: 1fr;
		}
	}
</style>