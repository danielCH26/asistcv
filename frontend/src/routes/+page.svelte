<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import JdForm from '$components/JdForm.svelte';
	import MatchResult from '$components/MatchResult.svelte';
	import { analysisStore } from '$stores/analysis';
	import { profileStore } from '$stores/profile';
	import { assertBuildEnv } from '$api/env';

	// Guard de env vars: falla el build si falta PUBLIC_API_URL.
	// La función corre en build time cuando el módulo se evalúa.
	assertBuildEnv();

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
		gap: 1.5rem;
	}

	.home__intro h1 {
		margin: 0 0 0.4rem;
		font-size: 1.6rem;
		color: var(--text-strong);
	}

	.home__intro p {
		margin: 0 0 0.5rem;
		color: var(--text-muted);
	}

	.home__profile {
		font-size: 0.9rem;
	}

	.home__loading,
	.home__error {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		padding: 1.5rem;
		border-radius: 12px;
		text-align: center;
	}

	.home__loading {
		background: var(--surface);
		border: 1px solid var(--border);
	}

	.home__error {
		background: var(--error-bg);
		color: var(--error);
		border: 1px solid var(--error);
	}

	.home__spinner {
		width: 2rem;
		height: 2rem;
		border-radius: 50%;
		border: 3px solid var(--border);
		border-top-color: var(--accent);
		animation: spin 0.9s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.home__error button {
		margin-top: 0.5rem;
		padding: 0.45rem 1rem;
		border: 1px solid var(--error);
		border-radius: 6px;
		background: transparent;
		color: var(--error);
		font-weight: 600;
		cursor: pointer;
	}
</style>