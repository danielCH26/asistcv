<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import ScoreCard from '$components/ScoreCard.svelte';
	import StrengthsGapsList from '$components/StrengthsGapsList.svelte';
	import EnergyBadge from '$components/EnergyBadge.svelte';
	import ReasoningBox from '$components/ReasoningBox.svelte';
	import { loadAnalysisDetail } from '$stores/history';
	import type { AnalysisDetail, EnergyLevel } from '$api/types';

	export let data: { id: string };

	let detail: AnalysisDetail | null = null;
	let status: 'loading' | 'error' | 'done' = 'loading';
	let errorMessage: string | null = null;

	function isEnergyLevel(value: string | null): value is EnergyLevel {
		return value === 'low' || value === 'medium' || value === 'high';
	}

	$: energyLevel = detail && isEnergyLevel(detail.energy_level) ? detail.energy_level : null;

	function formatDate(value: string): string {
		try {
			return new Intl.DateTimeFormat(undefined, { dateStyle: 'long', timeStyle: 'short' }).format(
				new Date(value)
			);
		} catch {
			return value;
		}
	}

	onMount(async () => {
		const parsed = Number.parseInt(data.id, 10);
		if (!Number.isFinite(parsed) || parsed <= 0) {
			status = 'error';
			errorMessage = 'Invalid analysis id';
			return;
		}
		const result = await loadAnalysisDetail(parsed);
		if (!result) {
			status = 'error';
			errorMessage = 'Could not load detail';
			return;
		}
		detail = result;
		status = 'done';
	});

	function back() {
		void goto('/history');
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('detail.heading')}</title>
</svelte:head>

<section class="detail">
	<header class="detail__header">
		<button type="button" class="detail__back" on:click={back}>← {$_('detail.back')}</button>
		<h1>{$_('detail.heading')}</h1>
	</header>

	{#if status === 'loading'}
		<p>{$_('detail.loading')}</p>
	{/if}

	{#if status === 'error'}
		<div class="detail__error" role="alert">
			<p>{$_('detail.notFound')}</p>
			{#if errorMessage}
				<small>{errorMessage}</small>
			{/if}
		</div>
	{/if}

	{#if status === 'done' && detail}
		<article class="detail__card">
			<div class="detail__top">
				<ScoreCard score={detail.score ?? 0} />
				<div class="detail__meta">
{#if energyLevel}
					<EnergyBadge level={energyLevel} />
				{/if}
					<p class="detail__date">
						{$_('detail.createdAt', { values: { date: formatDate(detail.created_at) } })}
					</p>
				</div>
			</div>

			<section class="detail__jd">
				<h3>{$_('detail.jobSnippet')}</h3>
				<p class="detail__snippet">{detail.job_description.snippet}</p>
				{#if detail.job_description.title}
					<small>{detail.job_description.title}{detail.job_description.company ? ` · ${detail.job_description.company}` : ''}</small>
				{/if}
			</section>

			<StrengthsGapsList strengths={detail.strengths} gaps={detail.gaps} />

			{#if detail.reasoning}
				<ReasoningBox text={detail.reasoning} />
			{/if}
		</article>
	{/if}
</section>

<style>
	.detail {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.detail__header {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.detail__header h1 {
		margin: 0;
		font-size: 1.5rem;
		color: var(--text-strong);
	}

	.detail__back {
		padding: 0.4rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--surface);
		color: var(--text);
		cursor: pointer;
	}

	.detail__card {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1.5rem;
	}

	.detail__top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 1rem;
	}

	.detail__meta {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		align-items: flex-end;
	}

	.detail__date {
		margin: 0;
		font-size: 0.85rem;
		color: var(--text-muted);
	}

	.detail__jd h3 {
		margin: 0 0 0.4rem;
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.detail__snippet {
		margin: 0;
		white-space: pre-wrap;
		font-family: ui-monospace, 'JetBrains Mono', SFMono-Regular, monospace;
		font-size: 0.85rem;
		color: var(--text);
	}

	.detail__error {
		padding: 1rem 1.25rem;
		background: var(--error-bg);
		color: var(--error);
		border: 1px solid var(--error);
		border-radius: 8px;
	}
</style>