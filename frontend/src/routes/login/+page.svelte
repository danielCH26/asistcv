<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { page } from '$app/stores';
	import { sessionEvent } from '$stores/session';
	import EmailCodeForm from '$lib/components/EmailCodeForm.svelte';

	$: reason = $page.url.searchParams.get('reason') ?? null;
</script>

<svelte:head>
	<title>eptus · {$_('login.title')}</title>
</svelte:head>

<div class="auth-page">
	<header class="page-header">
		<div>
			<h1 class="page-header__title">{$_('login.heading')}</h1>
			<p class="page-header__intro">{$_('auth.passwordlessHint')}</p>
		</div>
	</header>

	{#if reason === 'expired'}
		<p class="alert auth-page__notice" role="alert">{$_('session.expired')}</p>
	{:else if reason === 'required'}
		<p class="alert auth-page__notice" role="alert">{$_('session.required')}</p>
	{:else if $sessionEvent === 'token_reused'}
		<p class="alert auth-page__notice" role="alert">{$_('session.tokenReused')}</p>
	{/if}

	<div class="card auth-page__card">
		<EmailCodeForm />
	</div>

	<p class="auth-page__switch">
		{$_('login.noAccount')}
		<a href="/signup">{$_('login.signupLink')}</a>
	</p>
</div>

<style>
	.auth-page {
		display: flex;
		flex-direction: column;
		gap: var(--space-5);
		max-width: 28rem;
		margin: 0 auto;
	}

	.auth-page__notice {
		margin: 0;
		padding: var(--space-3) var(--space-4);
		font-size: var(--text-sm);
	}

	.auth-page__card {
		padding: var(--space-5);
	}

	.auth-page__switch {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.auth-page__switch a {
		color: var(--color-action);
	}
</style>
