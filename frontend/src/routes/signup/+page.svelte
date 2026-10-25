<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { page } from '$app/stores';
	import { clerkError, clerkReady, initClerk, mountSignUp } from '$lib/clerk';
	import { startOnboarding } from '$stores/session';

	let container: HTMLDivElement;
	let loading = true;
	let mounted = false;

	$: reason = $page.url.searchParams.get('reason') ?? null;

	onMount(async () => {
		await initClerk();
		// Start onboarding wizard immediately so it is ready when the
		// post-signup page (the Clerk redirect target) mounts.
		startOnboarding();
	});

	// The Clerk failure (if any) is reported through $clerkError — stop the
	// spinner so the user sees the cause instead of an eternal "Cargando".
	$: if ($clerkError) loading = false;

	// Reactive mount: $clerkReady may flip after initClerk resolves. Guard
	// against double-mounting on subsequent reactive runs. After Clerk
	// finishes the signup flow it redirects to `/profile` where the
	// onboarding wizard is rendered; the backend auto-provisions the user
	// on the first authenticated API call.
	$: if ($clerkReady && container && !mounted) {
		mounted = true;
		loading = false;
		mountSignUp(container, { redirectUrl: '/profile' });
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('signup.title')}</title>
</svelte:head>

<section class="signup">
	<h1>{$_('signup.heading')}</h1>

	{#if reason === 'required'}
		<p class="signup__notice" role="alert">{$_('session.required')}</p>
	{/if}

	{#if $clerkError}
		<p class="signup__error" role="alert">
			{$_('clerk.initError')}
			<span class="signup__error-detail">{$clerkError}</span>
		</p>
	{/if}

	{#if loading}
		<div class="signup__loading" aria-live="polite" aria-busy="true">
			<div class="signup__spinner" aria-hidden="true"></div>
			<p>{$_('signup.loading')}</p>
		</div>
	{/if}

	<div class="signup__clerk" bind:this={container} class:is-hidden={loading}></div>
</section>

<style>
	.signup {
		display: flex;
		flex-direction: column;
		gap: var(--space-5);
		max-width: 26rem;
		margin: 0 auto;
	}

	.signup h1 {
		margin: 0;
		font-size: var(--text-2xl);
		color: var(--color-ink-strong);
	}

	.signup__notice {
		padding: var(--space-3) var(--space-4);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--color-surface);
		color: var(--color-ink);
		margin: 0;
		font-size: var(--text-sm);
	}

	.signup__error {
		padding: var(--space-3) var(--space-4);
		border: 1px solid var(--color-danger, #b91c1c);
		border-radius: var(--radius-card);
		background: var(--color-danger-soft, #fef2f2);
		color: var(--color-danger, #b91c1c);
		margin: 0;
		font-size: var(--text-sm);
	}

	.signup__error-detail {
		display: block;
		margin-top: var(--space-2);
		font-family: var(--font-mono, monospace);
		font-size: var(--text-xs);
		opacity: 0.85;
		word-break: break-word;
	}

	.signup__loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-6);
	}

	.signup__spinner {
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

	.signup__clerk {
		min-height: 480px;
	}

	.signup__clerk.is-hidden {
		display: none;
	}
</style>
