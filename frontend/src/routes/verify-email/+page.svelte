<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { apiClient } from '$api/client';
	import { ApiError } from '$api/types';

	type Status = 'checking' | 'done' | 'error';

	let status: Status = 'checking';
	let errorCode = '';

	onMount(async () => {
		const token = new URLSearchParams(window.location.search).get('token') ?? '';
		if (!token) {
			errorCode = 'MISSING_TOKEN';
			status = 'error';
			return;
		}
		try {
			await apiClient.confirmEmailVerification(token);
			status = 'done';
		} catch (err) {
			errorCode = err instanceof ApiError ? (err.code ?? 'INVALID_TOKEN') : 'INVALID_TOKEN';
			status = 'error';
		}
	});

	function message(): string {
		switch (errorCode) {
			case 'MISSING_TOKEN':
				return $_('verifyEmail.missingToken');
			case 'TOKEN_EXPIRED':
				return $_('verifyEmail.expired');
			case 'TOKEN_USED':
				return $_('verifyEmail.used');
			default:
				return $_('verifyEmail.invalid');
		}
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('verifyEmail.title')}</title>
</svelte:head>

<section class="verify">
	<h1>{$_('verifyEmail.title')}</h1>

	{#if status === 'checking'}
		<p class="verify__status" aria-live="polite">{$_('verifyEmail.checking')}</p>
	{:else if status === 'done'}
		<p class="verify__status verify__status--ok" role="status">
			{$_('verifyEmail.success')}
		</p>
		<a class="verify__cta" href="/">{$_('verifyEmail.cta')}</a>
	{:else}
		<p class="verify__status verify__status--error" role="alert">{message()}</p>
		<a class="verify__cta" href="/">{$_('verifyEmail.cta')}</a>
	{/if}
</section>

<style>
	.verify {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		max-width: 42rem;
	}

	.verify h1 {
		margin: 0;
		font-size: var(--text-2xl);
		color: var(--color-ink-strong);
	}

	.verify__status {
		margin: 0;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.verify__status--ok {
		color: var(--color-success, var(--color-ink-strong));
	}

	.verify__status--error {
		color: var(--color-danger);
	}

	.verify__cta {
		align-self: flex-start;
		padding: var(--space-2) var(--space-4);
		border: var(--border-width) solid transparent;
		border-radius: var(--radius-control);
		background: var(--color-action);
		color: var(--color-on-action);
		font-weight: 600;
		font-size: var(--text-sm);
		text-decoration: none;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.verify__cta:hover {
		text-decoration: none;
		box-shadow: var(--clay-lifted);
	}

	.verify__cta:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}
</style>
