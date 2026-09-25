<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import ScoreCard from '$components/ScoreCard.svelte';
	import StrengthsGapsList from '$components/StrengthsGapsList.svelte';
	import EnergyBadge from '$components/EnergyBadge.svelte';
	import ReasoningBox from '$components/ReasoningBox.svelte';
	import { loadAnalysisDetail } from '$stores/history';
	import { ApiError, type AnalysisDetail, type EnergyLevel } from '$api/types';

	export let data: { id: string };

	let detail: AnalysisDetail | null = null;
	let status: 'loading' | 'error' | 'done' = 'loading';
	let errorMessage: string | null = null;

	const SNIPPET_MAX_CHARS = 200;

	function isEnergyLevel(value: string | null): value is EnergyLevel {
		return value === 'low' || value === 'medium' || value === 'high';
	}

	$: energyLevel = detail && isEnergyLevel(detail.energy_level) ? detail.energy_level : null;

	$: snippet =
		detail
			? detail.job_description.snippet.length > SNIPPET_MAX_CHARS
				? detail.job_description.snippet.slice(0, SNIPPET_MAX_CHARS).trimEnd() + '…'
				: detail.job_description.snippet
			: '';

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
		// Defense-in-depth: trust the backend to 404 cleanly and only show "Análisis no encontrado."
		// The previous parseInt-bail-out branch proved fragile (SvelteKit timing/caching edge cases
		// could make data.id arrive as something other than a clean positive integer even on /history/4).
		const id = Number.parseInt(data?.id ?? '', 10);
		try {
			if (!Number.isFinite(id) || id <= 0) {
				status = 'error';
				errorMessage = null;
				return;
			}
			const result = await loadAnalysisDetail(id);
			if (!result) {
				status = 'error';
				errorMessage = null;
				return;
			}
			detail = result;
			status = 'done';
		} catch (err) {
			status = 'error';
			if (err instanceof ApiError && err.status === 404) {
				// 404 = "not found" is expected — leave small text blank so the i18n title stands alone
				errorMessage = null;
			} else {
				errorMessage = err instanceof ApiError ? err.message : $_('detail.unexpectedError');
			}
		}
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
		<div class="detail__skeleton" role="status" aria-live="polite" aria-busy="true">
			<div class="detail__skeleton-row detail__skeleton-row--top">
				<div class="detail__skeleton detail__skeleton--score"></div>
				<div class="detail__skeleton detail__skeleton--meta"></div>
			</div>
			<div class="detail__skeleton detail__skeleton--snippet"></div>
			<div class="detail__skeleton detail__skeleton--list"></div>
			<div class="detail__skeleton detail__skeleton--reasoning"></div>
		</div>
		<p class="detail__loading-text">{$_('detail.loading')}</p>
	{/if}

	{#if status === 'error'}
		<div class="detail__error" role="alert">
			<p class="detail__error-title">{$_('detail.notFound')}</p>
			{#if errorMessage}
				<small>{errorMessage}</small>
			{/if}
			<button type="button" class="detail__error-back" on:click={back}>
				{$_('detail.back')}
			</button>
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
				<p class="detail__snippet">{snippet}</p>
				{#if detail.job_description.title}
					<small>
						{detail.job_description.title}{detail.job_description.company
							? ` · ${detail.job_description.company}`
							: ''}
					</small>
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

	.detail__back:hover {
		background: var(--surface-alt);
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
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 1rem 1.25rem;
		background: var(--error-bg);
		color: var(--error);
		border: 1px solid var(--error);
		border-radius: 8px;
	}

	.detail__error-title {
		margin: 0;
		font-weight: 600;
	}

	.detail__error-back {
		align-self: flex-start;
		margin-top: 0.5rem;
		padding: 0.4rem 0.75rem;
		border: 1px solid var(--error);
		border-radius: 6px;
		background: transparent;
		color: var(--error);
		font-weight: 600;
		cursor: pointer;
	}

	.detail__skeleton {
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.detail__skeleton-row {
		display: flex;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.detail__skeleton-row--top {
		justify-content: space-between;
		align-items: center;
	}

	.detail__skeleton--score,
	.detail__skeleton--meta,
	.detail__skeleton--snippet,
	.detail__skeleton--list,
	.detail__skeleton--reasoning {
		background: linear-gradient(
			90deg,
			var(--surface-alt) 0%,
			var(--border) 50%,
			var(--surface-alt) 100%
		);
		background-size: 200% 100%;
		animation: skeleton-shimmer 1.4s ease-in-out infinite;
		border-radius: 8px;
		min-height: 1.25rem;
	}

	.detail__skeleton--score {
		min-width: 140px;
		min-height: 110px;
	}

	.detail__skeleton--meta {
		flex: 1;
		min-width: 180px;
		min-height: 60px;
	}

	.detail__skeleton--snippet {
		min-height: 80px;
	}

	.detail__skeleton--list {
		min-height: 120px;
	}

	.detail__skeleton--reasoning {
		min-height: 100px;
	}

	.detail__loading-text {
		margin: 0;
		text-align: center;
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	@keyframes skeleton-shimmer {
		0% {
			background-position: 200% 0;
		}
		100% {
			background-position: -200% 0;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.detail__skeleton--score,
		.detail__skeleton--meta,
		.detail__skeleton--snippet,
		.detail__skeleton--list,
		.detail__skeleton--reasoning {
			animation: none;
		}
	}
</style>