<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { page } from '$app/stores';
	import { clerkError, clerkReady, initClerk, mountSignIn } from '$lib/clerk';

	let container: HTMLDivElement;
	let loading = true;
	let mounted = false;

	$: reason = $page.url.searchParams.get('reason') ?? null;

	onMount(async () => {
		await initClerk();
	});

	// The Clerk failure (if any) is reported through $clerkError — stop the
	// spinner so the user sees the cause instead of an eternal "Cargando".
	$: if ($clerkError) loading = false;

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
		<p class="login__error" role="alert">
			{$_('clerk.initError')}
			<span class="login__error-detail">{$clerkError}</span>
		</p>
	{/if}

	{#if loading}
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

	.login__error {
		padding: var(--space-3) var(--space-4);
		border: 1px solid var(--color-danger, #b91c1c);
		border-radius: var(--radius-card);
		background: var(--color-danger-soft, #fef2f2);
		color: var(--color-danger, #b91c1c);
		margin: 0;
		font-size: var(--text-sm);
	}

	.login__error-detail {
		display: block;
		margin-top: var(--space-2);
		font-family: var(--font-mono, monospace);
		font-size: var(--text-xs);
		opacity: 0.85;
		word-break: break-word;
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

	.login__clerk {
		min-height: 400px;
	}

	.login__clerk.is-hidden {
		display: none;
	}
</style>
