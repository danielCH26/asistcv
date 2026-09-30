<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { AdaptedCV } from '$api/types';

	export let adapted: AdaptedCV;
</script>

<article class="adaptation-result">
	<header class="adaptation-result__header">
		<h3 class="adaptation-result__name">{adapted.full_name}</h3>
	</header>

	<section class="adaptation-result__section">
		<h4 class="adaptation-result__heading">{$_('adapt.result.skillsHeading')}</h4>
		{#if adapted.skills.length === 0}
			<p class="adaptation-result__empty">—</p>
		{:else}
			<ul class="adaptation-result__tags">
				{#each adapted.skills as skill}
					<li class="adaptation-result__tag">{skill}</li>
				{/each}
			</ul>
		{/if}
	</section>

	{#if adapted.experience.length > 0}
		<section class="adaptation-result__section">
			<h4 class="adaptation-result__heading">{$_('adapt.result.experienceHeading')}</h4>
			<ol class="adaptation-result__experience">
				{#each adapted.experience as item, idx (idx)}
					<li class="adaptation-result__experience-item">
						<header class="adaptation-result__experience-head">
							<strong class="adaptation-result__title">{item.title}</strong>
							<span class="adaptation-result__company">{item.company}</span>
							<span class="adaptation-result__dates">{item.dates}</span>
						</header>
						<p class="adaptation-result__description">{item.description}</p>
					</li>
				{/each}
			</ol>
		</section>
	{/if}
</article>

<style>
	.adaptation-result {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		padding: var(--space-5);
		border: 1px solid var(--color-line);
		border-radius: 12px;
		background: var(--color-surface);
	}

	.adaptation-result__header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: var(--space-2);
	}

	.adaptation-result__name {
		margin: 0;
		font-size: var(--text-lg);
		color: var(--color-ink-strong);
	}

	.adaptation-result__section {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.adaptation-result__heading {
		margin: 0;
		font-size: var(--text-sm);
		text-transform: uppercase;
		letter-spacing: var(--tracking-wide);
		color: var(--color-ink-muted);
	}

	.adaptation-result__empty {
		margin: 0;
		color: var(--color-ink-muted);
	}

	.adaptation-result__tags {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}

	.adaptation-result__tag {
		padding: var(--space-1) var(--space-2);
		border-radius: 999px;
		background: var(--color-surface-alt);
		border: 1px solid var(--color-line);
		font-size: var(--text-sm);
		color: var(--color-ink);
	}

	.adaptation-result__experience {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.adaptation-result__experience-item {
		padding: var(--space-3) var(--space-4);
		border: 1px solid var(--color-line);
		border-radius: 10px;
		background: var(--color-surface-alt);
	}

	.adaptation-result__experience-head {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		align-items: baseline;
	}

	.adaptation-result__title {
		color: var(--color-ink-strong);
	}

	.adaptation-result__company,
	.adaptation-result__dates {
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.adaptation-result__description {
		margin: var(--space-2) 0 0;
		color: var(--color-ink);
		white-space: pre-wrap;
		line-height: var(--leading-normal);
	}
</style>
