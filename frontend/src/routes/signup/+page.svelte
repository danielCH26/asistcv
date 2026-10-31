<script lang="ts">
	import { _ } from 'svelte-i18n';
	import EmailCodeForm from '$lib/components/EmailCodeForm.svelte';
</script>

<svelte:head>
	<title>AsistCV · {$_('signup.title')}</title>
</svelte:head>

<section class="signup">
	<h1>{$_('signup.heading')}</h1>

	<p class="signup__hint">{$_('auth.passwordlessHint')}</p>

	<EmailCodeForm />

	<p class="signup__login">
		{$_('auth.haveAccount')}
		<a href="/login">{$_('auth.loginLink')}</a>
	</p>
</section>

<style>
	.signup {
		display: flex;
		flex-direction: column;
		gap: var(--space-5);
		max-width: 24rem;
		margin: 0 auto;
	}

	.signup h1 {
		margin: 0;
		font-size: var(--text-2xl);
		color: var(--color-ink-strong);
	}

	.signup__hint {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.signup__login {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.signup__login a {
		color: var(--color-action);
	}
</style>
