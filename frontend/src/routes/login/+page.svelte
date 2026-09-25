<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { login, sessionEvent } from '$stores/session';
	import { ApiError } from '$api/types';
	import { homeForRole } from '$auth/rules';
	import { page } from '$app/stores';

	let email = '';
	let password = '';
	let status: 'idle' | 'loading' | 'error' = 'idle';
	let errorMessage = '';

	$: reason = $page.url.searchParams.get('reason') ?? null;

	async function handleSubmit() {
		status = 'loading';
		errorMessage = '';
		try {
			const user = await login(email, password);
			sessionEvent.set(null);
			await goto(homeForRole(user.role));
		} catch (err) {
			status = 'error';
			errorMessage =
				err instanceof ApiError && err.code === 'RATE_LIMITED'
					? $_('login.rateLimited')
					: $_('login.invalidCredentials');
		}
	}
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

	<form class="login__form" on:submit|preventDefault={handleSubmit}>
		<label>
			{$_('login.email')}
			<input type="email" bind:value={email} required autocomplete="email" />
		</label>

		<label>
			{$_('login.password')}
			<input type="password" bind:value={password} required autocomplete="current-password" />
		</label>

		{#if status === 'error' && errorMessage}
			<p class="login__error" role="alert">{errorMessage}</p>
		{/if}

		<button type="submit" disabled={status === 'loading'}>
			{status === 'loading' ? $_('login.submitting') : $_('login.submit')}
		</button>
	</form>

	<p class="login__signup">
		{$_('login.noAccount')}
		<a href="/signup">{$_('login.signupLink')}</a>
	</p>
</section>

<style>
	.login {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		max-width: 24rem;
		margin: 0 auto;
	}

	.login h1 {
		margin: 0;
		font-size: 1.5rem;
		color: var(--text-strong);
	}

	.login__notice {
		padding: 0.75rem 1rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface);
		color: var(--text);
		margin: 0;
		font-size: 0.9rem;
	}

	.login__form {
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}

	.login__form label {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		font-size: 0.9rem;
		color: var(--text);
	}

	.login__form input {
		padding: 0.55rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--surface);
		color: var(--text-strong);
	}

	.login__error {
		margin: 0;
		color: var(--error);
		font-size: 0.9rem;
	}

	button[type='submit'] {
		padding: 0.65rem 1rem;
		border: none;
		border-radius: 8px;
		background: var(--accent);
		color: var(--accent-contrast);
		font-weight: 600;
		cursor: pointer;
	}

	button[type='submit']:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.login__signup {
		margin: 0;
		font-size: 0.9rem;
		color: var(--text-muted);
	}
</style>
