<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { apiClient } from '$api/client';
	import { ApiError, type AdaptationSummary, type CVSummary } from '$api/types';
	import { adaptationStore } from '$stores/adaptation';
	import { requireSession, session } from '$stores/session';
	import AdaptationResult from '$components/AdaptationResult.svelte';

	let ready = false;
	let cvs: CVSummary[] = [];
	let listError = '';

	let selectedCvId: number | null = null;
	let adaptJdText = '';
	let previousAdaptations: AdaptationSummary[] = [];
	let loadingPrevious = false;
	let previousError = '';

	$: activeCv = cvs.find((cv) => cv.id === selectedCvId) ?? null;

	onMount(async () => {
		if (!(await requireSession())) return;
		await loadCvs();
		ready = true;
	});

	async function loadCvs() {
		listError = '';
		try {
			cvs = await apiClient.listCvs();
			if (selectedCvId === null && cvs.length > 0) selectedCvId = cvs[0].id;
		} catch (err) {
			listError = err instanceof ApiError ? err.message : $_('cv.listError');
		}
	}

	async function runAdapt() {
		if (selectedCvId === null) return;
		if (adaptJdText.trim().length < 50) return;
		await adaptationStore.createAdaptation(selectedCvId, adaptJdText.trim());
		await loadPreviousAdaptations();
	}

	function adaptErrorMessage(code: string | null, fallback: string): string {
		switch (code) {
			case 'LLM_ERROR':
				return $_('adapt.errors.LLM_ERROR');
			case 'INVALID_HONESTY':
				return $_('adapt.errors.INVALID_HONESTY');
			case 'PLAN_LIMIT_REACHED':
				return $_('adapt.errors.PLAN_LIMIT_REACHED');
			case 'NO_CV_FOUND':
				return $_('adapt.errors.NO_CV_FOUND');
			case 'FEATURE_DISABLED':
				return $_('adapt.errors.FEATURE_DISABLED');
			case 'POLL_TIMEOUT':
				return $_('adapt.errors.POLL_TIMEOUT');
			default:
				return fallback;
		}
	}

	async function loadPreviousAdaptations() {
		if (selectedCvId === null) {
			previousAdaptations = [];
			return;
		}
		loadingPrevious = true;
		previousError = '';
		try {
			previousAdaptations = await adaptationStore.listAdaptationsForCv(selectedCvId);
		} catch (err) {
			previousError = err instanceof ApiError ? err.message : $_('adapt.previous.errorLoad');
		} finally {
			loadingPrevious = false;
		}
	}

	let prevLoadCvId: number | null = null;
	$: if (selectedCvId !== null && selectedCvId !== prevLoadCvId) {
		prevLoadCvId = selectedCvId;
		void loadPreviousAdaptations();
	}

	function formatAdaptDate(value: string): string {
		try {
			const d = new Date(value);
			if (Number.isNaN(d.getTime())) return value;
			return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(d);
		} catch {
			return value;
		}
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('adapt.pageTitle')}</title>
</svelte:head>

{#if ready}
	<section class="adapt">
		<h1>{$_('adapt.heading')}</h1>
		<p class="adapt__subtitle">{$_('adapt.subtitle')}</p>

		{#if listError}<p class="adapt__error" role="alert">{listError}</p>{/if}

		{#if cvs.length === 0}
			<p class="adapt__empty">{$_('adapt.form.cvPlaceholder')}</p>
		{:else}
			<label class="adapt__field">
				<span>{$_('adapt.form.cvLabel')}</span>
				<select bind:value={selectedCvId} disabled={$adaptationStore.status === 'pending'}>
					{#each cvs as cv (cv.id)}
						<option value={cv.id}>{cv.original_filename}</option>
					{/each}
				</select>
			</label>
		{/if}

		<textarea
			class="adapt__jd"
			rows="6"
			bind:value={adaptJdText}
			placeholder={$_('adapt.form.jdPlaceholder')}
			disabled={$adaptationStore.status === 'pending'}
		/>

		<button
			type="button"
			class="adapt__cta"
			disabled={$adaptationStore.status === 'pending' || selectedCvId === null || adaptJdText.trim().length < 50}
			on:click={runAdapt}
		>
			{$adaptationStore.status === 'pending' ? $_('adapt.status.pending') : $_('adapt.cta.submit')}
		</button>

		{#if $adaptationStore.status === 'failed' && $adaptationStore.errorCode === 'PLAN_LIMIT_REACHED'}
			<div class="adapt__upsell" role="alert">
				<p>{$_('adapt.errors.PLAN_LIMIT_REACHED')}</p>
				<p class="adapt__upsell-text">{$_('adapt.upsell.text')}</p>
				<a href="/billing">{$_('adapt.upsell.cta')}</a>
			</div>
		{:else if $adaptationStore.status === 'failed'}
			<p class="adapt__error" role="alert">
				{adaptErrorMessage($adaptationStore.errorCode, $adaptationStore.errorMessage ?? $_('adapt.errors.GENERIC'))}
				<button type="button" on:click={() => adaptationStore.reset()}>{$_('adapt.cta.retry')}</button>
			</p>
		{/if}

		{#if $adaptationStore.status === 'pending'}
			<div class="adapt__loading" role="status">
				<div class="adapt__spinner" aria-hidden="true"></div>
				<p>{$_('adapt.status.pending')}</p>
			</div>
		{/if}

		{#if $adaptationStore.status === 'completed' && $adaptationStore.adaptation?.adapted_cv}
			<div class="adapt__result">
				<h2>{$_('adapt.result.heading')}</h2>
				<AdaptationResult adapted={$adaptationStore.adaptation.adapted_cv} />
			</div>
		{/if}

		<details class="adapt__previous">
			<summary>{$_('adapt.previous.heading')}</summary>
			{#if loadingPrevious}
				<p class="adapt__muted">…</p>
			{:else if previousError}
				<p class="adapt__error" role="alert">{previousError}</p>
			{:else if previousAdaptations.length === 0}
				<p class="adapt__muted">{$_('adapt.previous.empty')}</p>
			{:else}
				<ul class="adapt__list">
					{#each previousAdaptations as item (item.id)}
						<li class="adapt__list-item">
							<span class="adapt__list-id">#{item.id}</span>
							<span class="adapt__list-status adapt__list-status--{item.status}">
								{item.status === 'completed'
									? $_('adapt.previous.statusCompleted')
									: item.status === 'failed'
										? $_('adapt.previous.statusFailed')
										: $_('adapt.previous.statusPending')}
							</span>
							<span class="adapt__list-date">{formatAdaptDate(item.created_at)}</span>
						</li>
					{/each}
				</ul>
			{/if}
		</details>
	</section>
{/if}

<style>
	.adapt {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.adapt h1 {
		margin: 0;
		font-size: var(--text-2xl);
		color: var(--color-ink-strong);
	}

	.adapt h2 {
		margin: 0 0 var(--space-2);
		font-size: var(--text-lg);
		color: var(--color-ink-strong);
	}

	.adapt__subtitle {
		margin: calc(-1 * var(--space-2)) 0 0;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.adapt__error {
		margin: 0;
		color: var(--color-danger);
		font-size: var(--text-sm);
	}

	.adapt__empty {
		margin: 0;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.adapt__field {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		font-size: var(--text-sm);
		color: var(--color-ink);
	}

	.adapt__field select {
		padding: var(--space-2) var(--space-3);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--clay-fill);
		color: var(--color-ink);
		font-family: inherit;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.adapt__field select:focus-visible {
		outline: 2px solid var(--color-action);
		outline-offset: 1px;
		border-color: var(--color-action);
		box-shadow: var(--clay-lifted);
	}

	.adapt__jd {
		width: 100%;
		padding: var(--space-2) var(--space-3);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--clay-fill);
		color: var(--color-ink);
		font-family: inherit;
		resize: vertical;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.adapt__jd:focus {
		outline: 2px solid var(--color-action);
		outline-offset: 1px;
		border-color: var(--color-action);
		box-shadow: var(--clay-lifted);
	}

	.adapt__cta {
		align-self: flex-start;
		padding: var(--space-2) var(--space-4);
		border: none;
		border-radius: var(--radius-card);
		background: var(--color-action);
		color: var(--color-on-action);
		font-weight: 600;
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.adapt__cta:hover:not(:disabled) {
		background: var(--color-accent-hover);
		box-shadow: var(--clay-lifted);
	}

	.adapt__cta:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.adapt__cta:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.adapt__upsell {
		padding: var(--space-4);
		border: var(--border-width) solid var(--color-action);
		border-radius: var(--radius-card);
		background: var(--color-surface);
	}

	.adapt__upsell-text {
		margin: var(--space-2) 0;
		color: var(--color-ink);
	}

	.adapt__upsell a {
		font-weight: 600;
	}

	.adapt__loading {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-3) var(--space-4);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card-lg);
		background: var(--color-surface);
		color: var(--color-ink-muted);
	}

	.adapt__spinner {
		width: var(--space-4);
		height: var(--space-4);
		border-radius: var(--radius-circle);
		border: var(--border-width-thick) solid var(--color-line);
		border-top-color: var(--color-action);
		animation: adapt-spin 0.9s linear infinite;
	}

	@keyframes adapt-spin {
		to {
			transform: rotate(360deg);
		}
	}

	.adapt__result {
		padding: var(--space-4) var(--space-5);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--color-surface);
	}

	.adapt__previous {
		margin-top: var(--space-2);
	}

	.adapt__muted {
		margin: 0;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.adapt__list {
		list-style: none;
		margin: var(--space-2) 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.adapt__list-item {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--color-surface);
		font-size: var(--text-sm);
	}

	.adapt__list-id {
		color: var(--color-ink-muted);
		font-variant-numeric: tabular-nums;
	}

	.adapt__list-status {
		padding: var(--space-1) var(--space-2);
		border-radius: var(--radius-pill);
		font-size: var(--text-xs);
		font-weight: 600;
		border: var(--border-width) solid var(--color-line);
		color: var(--color-ink-muted);
	}

	.adapt__list-status--completed {
		border-color: var(--score-high-ink);
		color: var(--score-high-ink);
	}

	.adapt__list-status--failed {
		border-color: var(--color-danger);
		color: var(--color-danger);
	}

	.adapt__list-status--pending {
		border-color: var(--color-action);
		color: var(--color-action);
	}

	.adapt__list-date {
		margin-left: auto;
		color: var(--color-ink-muted);
	}
</style>
