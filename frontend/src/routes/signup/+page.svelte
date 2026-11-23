<script lang="ts">
	import { _ } from 'svelte-i18n';
	import EmailCodeForm from '$lib/components/EmailCodeForm.svelte';
</script>

<svelte:head>
	<title>eptus · {$_('signup.title')}</title>
</svelte:head>

<div class="auth-page">
	<header class="page-header">
		<div>
			<h1 class="page-header__title">{$_('signup.heading')}</h1>
			<p class="page-header__intro">{$_('auth.passwordlessHint')}</p>
		</div>
	</header>

	<div class="card auth-page__card">
		<EmailCodeForm />
	</div>

	<p class="auth-page__switch">
		{$_('auth.haveAccount')}
		<a href="/login">{$_('auth.loginLink')}</a>
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
