<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { page } from '$app/stores';
	import { sessionEvent } from '$stores/session';
	import EmailCodeForm from '$lib/components/EmailCodeForm.svelte';

	$: reason = $page.url.searchParams.get('reason') ?? null;
</script>

<svelte:head>
	<title>AsistCV · {$_('login.title')}</title>
</svelte:head>

<section class="login">
	<h1>{$_('login.heading')}</h1>

	{#if reason === 'expired'}
		<p class="login__notice" role="alert">{$_('session.expired')}</p>
	{:else if reason === 'required'}
		<p class="login__notice" role="alert">{$_('session.required')}</p>
	{:else if $sessionEvent === 'token_reused'}
		<p class="login__notice" role="alert">{$_('session.tokenReused')}</p>
	{/if}

	<EmailCodeForm />

	<p class="login__signup">
		{$_('login.noAccount')}
		<a href="/signup">{$_('login.signupLink')}</a>
	</p>
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

	.login__signup {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.login__signup a {
		color: var(--color-action);
	}
</style>
