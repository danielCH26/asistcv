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
		gap: 1rem;
		padding: 1.25rem;
		border: 1px solid var(--border);
		border-radius: 12px;
		background: var(--surface);
	}

	.adaptation-result__header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.adaptation-result__name {
		margin: 0;
		font-size: 1.15rem;
		color: var(--text-strong);
	}

	.adaptation-result__section {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.adaptation-result__heading {
		margin: 0;
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.adaptation-result__empty {
		margin: 0;
		color: var(--text-muted);
	}

	.adaptation-result__tags {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}

	.adaptation-result__tag {
		padding: 0.2rem 0.6rem;
		border-radius: 999px;
		background: var(--surface-alt);
		border: 1px solid var(--border);
		font-size: 0.85rem;
		color: var(--text);
	}

	.adaptation-result__experience {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.adaptation-result__experience-item {
		padding: 0.75rem 1rem;
		border: 1px solid var(--border);
		border-radius: 10px;
		background: var(--surface-alt);
	}

	.adaptation-result__experience-head {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: baseline;
	}

	.adaptation-result__title {
		color: var(--text-strong);
	}

	.adaptation-result__company,
	.adaptation-result__dates {
		color: var(--text-muted);
		font-size: 0.85rem;
	}

	.adaptation-result__description {
		margin: 0.4rem 0 0;
		color: var(--text);
		white-space: pre-wrap;
		line-height: 1.5;
	}
</style>
