<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import JdForm from '$components/JdForm.svelte';
	import MatchResult from '$components/MatchResult.svelte';
	import { analysisStore } from '$stores/analysis';
	import { profileStore } from '$stores/profile';
	import { apiClient } from '$api/client';
	import { isAuthenticated, refreshIfNeeded } from '$stores/session';
	import type { SubscriptionInfo } from '$api/types';

	let subscription: SubscriptionInfo | null = null;

	onMount(async () => {
		if (!get(isAuthenticated)) return;
		await refreshIfNeeded();
		try {
			subscription = await apiClient.subscription();
		} catch {
			subscription = null;
		}
	});

	function usageLabel(): string {
		if (!subscription) return '';
		const matches = subscription.usage['matches_this_month'];
		const limit = subscription.limits['matches_per_month'];
		if (typeof matches !== 'number') return '';
		if (typeof limit !== 'number' || limit <= 0) {
			return $_('billing.usageUnlimited', { values: { used: matches } });
		}
		return $_('billing.usage', { values: { used: matches, limit } });
	}

	async function handleSubmit(event: CustomEvent<{ jdText: string }>) {
		const profileId = get(profileStore);
		await analysisStore.submit(event.detail.jdText, profileId);
	}

	function retry() {
		analysisStore.reset();
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('app.tagline')}</title>
</svelte:head>

<section class="home">
	<header class="home__intro">
		<h1>{$_('home.heading')}</h1>
		<p>{$_('home.intro')}</p>
		<p class="home__profile">
			{$_('home.profileLabel')}: <strong>#{$profileStore}</strong>
		</p>
		{#if $isAuthenticated && usageLabel()}
			<p class="home__usage">{usageLabel()}</p>
		{/if}
	</header>

	<JdForm on:submit={handleSubmit} loading={$analysisStore.status === 'loading'} />

	{#if $analysisStore.status === 'loading'}
		<section class="home__loading" aria-live="polite">
			<div class="home__spinner" aria-hidden="true"></div>
			<h2>{$_('loading.title')}</h2>
			<p>{$_('loading.subtitle')}</p>
			<small>{$_('loading.detail')}</small>
		</section>
	{/if}

	{#if $analysisStore.status === 'error'}
		<section class="home__error" role="alert">
			<h2>{$_('error.title')}</h2>
			<p>{$analysisStore.error}</p>
			<button type="button" on:click={retry}>{$_('error.retry')}</button>
		</section>
	{/if}

	{#if $analysisStore.status === 'done' && $analysisStore.result}
		<MatchResult analysis={$analysisStore.result} />
	{/if}
</section>

<style>
	.home {
		display: flex;
		flex-direction: column;
		gap: var(--space-5);
	}

	.home__intro h1 {
		margin: 0 0 0.4rem;
		font-size: 1.6rem;
		color: var(--color-ink-strong);
	}

	.home__intro p {
		margin: 0 0 var(--space-2);
		color: var(--color-ink-muted);
	}

	.home__profile {
		font-size: 0.9rem;
	}

	.home__usage {
		margin: 0;
		font-size: 0.85rem;
		color: var(--color-ink-muted);
	}

	/* Status panels, not controls. Flat. */
	.home__loading,
	.home__error {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-5);
		border-radius: var(--radius-panel);
		text-align: center;
	}

	.home__loading {
		background: var(--color-surface);
		border: var(--border-width) solid var(--color-line);
	}

	.home__error {
		background: var(--color-danger-muted);
		color: var(--color-danger);
		border: var(--border-width) solid var(--color-danger);
	}

	.home__spinner {
		width: var(--space-6);
		height: var(--space-6);
		border-radius: var(--radius-circle);
		border: var(--border-width-heavy) solid var(--color-line);
		border-top-color: var(--color-action);
		animation: spin 0.9s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* A control: clay. */
	.home__error button {
		margin-top: var(--space-2);
		padding: 0.45rem var(--space-4);
		border: var(--border-width) solid var(--color-danger);
		border-radius: var(--radius-control);
		background: var(--clay-fill);
		color: var(--color-danger);
		font-weight: 600;
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.home__error button:hover {
		box-shadow: var(--clay-lifted);
	}

	.home__error button:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}
</style>
