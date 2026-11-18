<script lang="ts">
	import { _ } from 'svelte-i18n';

	export let strengths: string[] = [];
	export let gaps: string[] = [];
</script>

<div class="strengths-gaps">
	<section class="strengths-gaps__panel">
		<h3 class="strengths-gaps__heading">
			<span class="strengths-gaps__dot strengths-gaps__dot--strength" aria-hidden="true"></span>
			{$_('result.strengths')}
		</h3>
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
		<h3 class="strengths-gaps__heading">
			<span class="strengths-gaps__dot strengths-gaps__dot--gap" aria-hidden="true"></span>
			{$_('result.gaps')}
		</h3>
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
	/* Las columnas van planas: viven dentro del panel del resultado y una
	   tarjeta dentro de otra tarjeta sólo agrega ruido. */
	.strengths-gaps {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-6);
	}

	.strengths-gaps__panel {
		min-width: 0;
	}

	.strengths-gaps__heading {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		margin: 0 0 var(--space-3);
		font-family: var(--font-mono);
		font-size: var(--text-2xs);
		letter-spacing: var(--tracking-widest);
		text-transform: uppercase;
		color: var(--color-ink-muted);
	}

	.strengths-gaps__dot {
		width: 6px;
		height: 6px;
		border-radius: var(--radius-circle);
		flex: none;
	}

	.strengths-gaps__dot--strength {
		background: var(--score-high);
	}

	.strengths-gaps__dot--gap {
		background: var(--score-mid);
	}

	.strengths-gaps__list {
		margin: 0;
		padding: 0;
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		font-size: var(--text-sm);
		line-height: var(--leading-relaxed);
		color: var(--color-ink);
	}

	.strengths-gaps__empty {
		margin: 0;
		color: var(--color-ink-muted);
	}

	@media (max-width: 640px) {
		.strengths-gaps {
			grid-template-columns: 1fr;
			gap: var(--space-4);
		}
	}
</style>
