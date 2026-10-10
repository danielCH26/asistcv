<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { apiClient } from '$api/client';
	import { ApiError, type JobOffer, type OfferPreferences } from '$api/types';
	import { requireSession } from '$stores/session';

	let ready = false;

	// Offer list state
	let offers: JobOffer[] = [];
	let loadError = '';
	let loading = true;
	let archivedIds = new Set<number>();
	let archivingId: number | null = null;
	let archiveErrorId: number | null = null;

	// Preferences state
	let prefs: OfferPreferences = {
		frequency_hours: 24,
		top_n: 5,
		email_frequency: 'daily'
	};
	let saveBusy = false;
	let saved = false;
	let saveError = '';
	let prefsExpanded = false;

	function scrollToPrefs() {
		prefsExpanded = true;
		const el = document.getElementById('job-offers__preferences');
		el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	onMount(async () => {
		if (!(await requireSession())) return;
		ready = true;
		try {
			offers = await apiClient.getJobOffers({ status: 'new', limit: 20, offset: 0 });
		} catch (err) {
			if (err instanceof ApiError && err.status === 503) {
				loadError = $_('jobOffers.featureDisabled');
			} else {
				loadError = $_('jobOffers.loadError');
			}
		} finally {
			loading = false;
		}
	});

	async function archiveOffer(id: number) {
		archivingId = id;
		archiveErrorId = null;
		try {
			await apiClient.archiveJobOffer(id);
			archivedIds = new Set([...archivedIds, id]);
			offers = offers.filter((o) => o.id !== id);
		} catch (err) {
			archiveErrorId = id;
		} finally {
			archivingId = null;
		}
	}

	async function savePreferences() {
		saveBusy = true;
		saved = false;
		saveError = '';
		try {
			await apiClient.updateOfferPreferences(prefs);
			saved = true;
			setTimeout(() => (saved = false), 3000);
		} catch {
			saveError = $_('jobOffers.saveError');
		} finally {
			saveBusy = false;
		}
	}

	function scoreLabel(score: number | null): string {
		if (score === null) return '—';
		return `${(score * 100).toFixed(0)}%`;
	}

	function scoreClass(score: number | null): string {
		if (score === null) return '';
		if (score >= 0.75) return 'score--high';
		if (score >= 0.5) return 'score--mid';
		return 'score--low';
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('jobOffers.title')}</title>
</svelte:head>

{#if ready}
	<section class="job-offers">
		<h1>{$_('jobOffers.heading')}</h1>

		<!-- Loading -->
		{#if loading}
			<p class="job-offers__loading">{$_('jobOffers.loading')}</p>
		{/if}

		<!-- Load error -->
		{#if loadError && !loading}
			<p class="job-offers__error" role="alert">{loadError}</p>
		{/if}

		<!-- Empty state -->
		{#if !loading && !loadError && offers.length === 0}
			<p class="job-offers__empty">{$_('jobOffers.empty')}</p>
			<button type="button" class="clay-btn" on:click={scrollToPrefs}>
				{$_('jobOffers.emptyPreferencesCta')}
			</button>
		{/if}

		<!-- Offer list -->
		{#if offers.length > 0}
			<ul class="job-offers__list">
				{#each offers as offer (offer.id)}
					<li class="offer-card">
						<div class="offer-card__header">
							<div class="offer-card__title-group">
								<h2 class="offer-card__title">{offer.title}</h2>
								{#if offer.company}
									<span class="offer-card__company">{offer.company}</span>
								{/if}
							</div>
							{#if offer.score !== null}
								<span
									class="offer-card__score badge {scoreClass(offer.score)}"
									title={$_('jobOffers.scoreLabel')}
								>
									{scoreLabel(offer.score)}
								</span>
							{/if}
						</div>

						{#if offer.snippet}
							<p class="offer-card__snippet">{offer.snippet}</p>
						{/if}

						<div class="offer-card__actions">
							{#if offer.url}
								<a
									class="offer-card__link clay-btn"
									href={offer.url}
									target="_blank"
									rel="noopener noreferrer"
								>
									{$_('jobOffers.externalLink')}
								</a>
							{/if}
							<button
								type="button"
								class="clay-btn clay-btn--secondary"
								disabled={archivingId === offer.id}
								on:click={() => archiveOffer(offer.id)}
							>
								{archivingId === offer.id
									? $_('jobOffers.archiving')
									: archiveErrorId === offer.id
										? $_('jobOffers.archiveError')
										: $_('jobOffers.archiveCta')}
							</button>
						</div>
					</li>
				{/each}
			</ul>
		{/if}

		<!-- Preferences section -->
		<section class="job-offers__prefs" id="job-offers__preferences">
			<h2 class="job-offers__prefs-heading">{$_('jobOffers.preferencesHeading')}</h2>

			<div class="job-offers__prefs-form">
				<label class="job-offers__field">
					<span class="job-offers__field-label">{$_('jobOffers.frequencyLabel')}</span>
					<select class="job-offers__select" bind:value={prefs.frequency_hours}>
						<option value={6}>{$_('jobOffers.frequencyHours', { values: { hours: 6 } })}</option>
						<option value={12}>{$_('jobOffers.frequencyHours', { values: { hours: 12 } })}</option>
						<option value={24}>{$_('jobOffers.frequencyHours', { values: { hours: 24 } })}</option>
						<option value={48}>{$_('jobOffers.frequencyHours', { values: { hours: 48 } })}</option>
					</select>
				</label>

				<label class="job-offers__field">
					<span class="job-offers__field-label">{$_('jobOffers.topNLabel')}</span>
					<select class="job-offers__select" bind:value={prefs.top_n}>
						{#each [1, 3, 5, 10, 15, 20] as n}
							<option value={n}>{n}</option>
						{/each}
					</select>
				</label>

				<label class="job-offers__field">
					<span class="job-offers__field-label">{$_('jobOffers.emailFrequencyLabel')}</span>
					<select class="job-offers__select" bind:value={prefs.email_frequency}>
						<option value="none">{$_('jobOffers.emailNone')}</option>
						<option value="daily">{$_('jobOffers.emailDaily')}</option>
						<option value="weekly">{$_('jobOffers.emailWeekly')}</option>
					</select>
				</label>
			</div>

			<div class="job-offers__prefs-footer">
				<button
					type="button"
					class="clay-btn clay-btn--primary"
					disabled={saveBusy}
					on:click={savePreferences}
				>
					{saveBusy ? $_('jobOffers.saving') : $_('jobOffers.savePreferences')}
				</button>
				{#if saved}
					<span class="job-offers__saved" role="status">{$_('jobOffers.saved')}</span>
				{/if}
				{#if saveError}
					<span class="job-offers__save-error" role="alert">{saveError}</span>
				{/if}
			</div>
		</section>
	</section>
{/if}

<style>
	.job-offers {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.job-offers h1 {
		margin: 0;
		font-size: var(--text-2xl);
		color: var(--color-ink-strong);
	}

	.job-offers__loading {
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.job-offers__error {
		margin: 0;
		color: var(--color-error);
		font-size: var(--text-sm);
	}

	.job-offers__empty {
		margin: 0;
		color: var(--color-ink-muted);
	}

	/* Clay button base */
	:global(.clay-btn) {
		padding: var(--space-2) var(--space-4);
		border: none;
		border-radius: var(--radius-card);
		background: var(--clay-fill);
		color: var(--color-ink);
		font-weight: 600;
		font-size: var(--text-sm);
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
		text-decoration: none;
		display: inline-block;
	}

	:global(.clay-btn:hover) {
		box-shadow: var(--clay-lifted);
	}

	:global(.clay-btn:focus-visible) {
		outline: none;
		box-shadow: var(--clay-raised), var(--clay-focus-ring);
	}

	:global(.clay-btn:disabled) {
		opacity: 0.5;
		cursor: not-allowed;
		box-shadow: none;
	}

	:global(.clay-btn--primary) {
		background: var(--color-action);
		color: var(--color-on-action);
	}

	:global(.clay-btn--secondary) {
		background: var(--clay-fill);
		color: var(--color-ink-muted);
	}

	/* Offer list */
	.job-offers__list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.offer-card {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-4);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-panel);
		background: var(--color-surface);
		box-shadow: var(--clay-raised);
	}

	.offer-card__header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: var(--space-3);
	}

	.offer-card__title-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.offer-card__title {
		margin: 0;
		font-size: var(--text-md);
		color: var(--color-ink-strong);
		font-weight: 600;
	}

	.offer-card__company {
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.offer-card__score {
		flex-shrink: 0;
		padding: var(--space-1) var(--space-2);
		border-radius: var(--radius-control);
		font-size: var(--text-xs);
		font-weight: 700;
		background: var(--clay-fill);
		color: var(--color-ink);
		box-shadow: var(--clay-raised);
	}

	:global(.score--high) {
		background: var(--color-success-bg, #dcfce7);
		color: var(--color-success, #16a34a);
	}

	:global(.score--mid) {
		background: var(--color-warning-bg, #fef9c3);
		color: var(--color-warning, #ca8a04);
	}

	:global(.score--low) {
		background: var(--color-error-bg, #fee2e2);
		color: var(--color-error, #dc2626);
	}

	.offer-card__snippet {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
		line-height: var(--leading-relaxed);
	}

	.offer-card__actions {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	/* Preferences section */
	.job-offers__prefs {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		padding: var(--space-4);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-panel);
		background: var(--color-surface);
		box-shadow: var(--clay-raised);
	}

	.job-offers__prefs-heading {
		margin: 0;
		font-size: var(--text-lg);
		color: var(--color-ink-strong);
	}

	.job-offers__prefs-form {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.job-offers__field {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.job-offers__field-label {
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
		font-weight: 500;
	}

	.job-offers__select {
		padding: var(--space-2) var(--space-3);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-control);
		background: var(--clay-fill);
		color: var(--color-ink);
		font-size: var(--text-sm);
		cursor: pointer;
		box-shadow: var(--clay-raised);
		appearance: none;
		-webkit-appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%236b7280' d='M6 8L2 4h8z'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 10px center;
		padding-right: 28px;
	}

	.job-offers__select:focus {
		outline: none;
		box-shadow: var(--clay-raised), var(--clay-focus-ring);
	}

	.job-offers__prefs-footer {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	.job-offers__saved {
		font-size: var(--text-sm);
		color: var(--color-success, #16a34a);
	}

	.job-offers__save-error {
		font-size: var(--text-sm);
		color: var(--color-error);
	}
</style>
