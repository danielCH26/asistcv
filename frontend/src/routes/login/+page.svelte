<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { page } from '$app/stores';
	import { clerkError, clerkReady, initClerk, mountSignIn, resetClerkError } from '$lib/clerk';

	let container: HTMLDivElement;
	let loading = true;
	let mounted = false;

	$: reason = $page.url.searchParams.get('reason') ?? null;

	onMount(async () => {
		try {
			await initClerk();
		} catch {
			// initClerk already published the failure through clerkError.
			// The page renders an actionable error instead of a spinner that
			// never resolves.
			loading = false;
		}
	});

	// Retry a failed Clerk initialization: clear the error and let the
	// reactive block mount the component again once Clerk is ready.
	async function retry() {
		resetClerkError();
		loading = true;
		mounted = false;
		try {
			await initClerk();
		} catch {
			loading = false;
		}
	}

	// Reactive mount: $clerkReady may flip after initClerk resolves. Guard
	// against double-mounting on subsequent reactive runs.
	$: if ($clerkReady && container && !mounted) {
		mounted = true;
		loading = false;
		mountSignIn(container, { redirectUrl: '/' });
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('login.title')}</title>
</svelte:head>

<section class="login">
	<h1>{$_('login.heading')}</h1>

	{#if reason === 'required'}
		<p class="login__notice" role="alert">{$_('session.required')}</p>
	{:else if reason === 'expired'}
		<p class="login__notice" role="alert">{$_('session.expired')}</p>
	{/if}

	{#if $clerkError}
		<div class="login__error" role="alert">
			<h2>{$_('clerk.errorTitle')}</h2>
			<p>{$_('clerk.errorBody')}</p>
			<button type="button" on:click={retry}>{$_('clerk.retry')}</button>
		</div>
	{:else if loading}
		<div class="login__loading" aria-live="polite" aria-busy="true">
			<div class="login__spinner" aria-hidden="true"></div>
			<p>{$_('login.loading')}</p>
		</div>
	{/if}

	<div class="login__clerk" bind:this={container} class:is-hidden={loading}></div>
</section>

<style>
	.login {
		display: flex;
		flex-direction: column;
		gap: var(--space-5);
		max-width: 24rem;
		margin: 0 auto;
	}

	.login h1 {
		margin: 0;
		font-size: var(--text-2xl);
		color: var(--color-ink-strong);
	}

	.login__notice {
		padding: var(--space-3) var(--space-4);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--color-surface);
		color: var(--color-ink);
		margin: 0;
		font-size: var(--text-sm);
	}

	.login__loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-6);
	}

	.login__spinner {
		width: var(--space-5);
		height: var(--space-5);
		border-radius: 50%;
		border: 2px solid var(--color-line);
		border-top-color: var(--color-action);
		animation: spin 0.9s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.login__error {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-6);
		border: 1px solid var(--color-danger);
		border-radius: var(--radius-card);
		background: var(--color-danger-muted);
		color: var(--color-danger);
		text-align: center;
	}

	.login__error h2 {
		margin: 0;
		font-size: var(--text-lg);
	}

	.login__error p {
		margin: 0;
		font-size: var(--text-sm);
	}

	.login__error button {
		margin-top: var(--space-2);
		padding: var(--space-2) var(--space-4);
		border: 1px solid var(--color-danger);
		border-radius: var(--radius-control);
		background: transparent;
		color: var(--color-danger);
		font-weight: 600;
		cursor: pointer;
	}

	.login__clerk {
		min-height: 400px;
	}

	.login__clerk.is-hidden {
		display: none;
	}
</style>
