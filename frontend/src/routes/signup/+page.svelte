<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { sessionEvent } from '$stores/session';
	import { signup, startOnboarding, getPendingAuditToken, clearPendingAuditToken } from '$stores/session';
	import { apiClient } from '$api/client';
	import { ApiError, type Role } from '$api/types';
	import { canSubmitSignup, homeForRole, isPasswordValid, TOS_VERSION } from '$auth/rules';

	let email = '';
	let password = '';
	let fullName = '';
	let role: Role = 'job_seeker';
	let acceptTos = false;
	let goodFaith = false;
	let status: 'idle' | 'loading' | 'error' | 'done' = 'idle';
	let errorMessage = '';
	let notice = get(sessionEvent) === 'token_reused' ? 'banner' : '';

	$: consentRequired = role === 'recruiter';
	$: consentGiven = canSubmitSignup({ role, acceptTos, goodFaith });
	$: submitDisabled = status === 'loading' || !consentGiven;

	async function handleSubmit() {
		if (!isPasswordValid(password)) {
			errorMessage = $_('signup.passwordInvalid');
			status = 'error';
			return;
		}
		status = 'loading';
		errorMessage = '';
		try {
			const result = await signup({
				email,
				password,
				role,
				full_name: fullName.trim() || email,
				locale: 'es',
				accept_tos: consentRequired ? acceptTos : false,
				good_faith_declaration: consentRequired ? goodFaith : false,
				tos_version: TOS_VERSION
			});
			status = 'done';
			if (getPendingAuditToken()) {
				clearPendingAuditToken();
				apiClient.clearAuditToken();
			}
			startOnboarding();
			if (result.analysis_id !== undefined) {
				await goto(`/history/${result.analysis_id}`);
				return;
			}
			await goto(homeForRole(result.user.role));
		} catch (err) {
			status = 'error';
			if (err instanceof ApiError) {
				errorMessage =
					err.code === 'EMAIL_TAKEN'
						? $_('signup.emailTaken')
						: err.status === 422
							? $_('signup.consentRejected')
							: err.message;
			} else {
				errorMessage = $_('signup.genericError');
			}
		}
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('signup.title')}</title>
</svelte:head>

<section class="signup">
	<h1>{$_('signup.heading')}</h1>

	{#if notice === 'banner'}
		<p class="signup__banner" role="alert">{$_('session.tokenReused')}</p>
	{/if}

	<form class="signup__form" on:submit|preventDefault={handleSubmit}>
		<label>
			{$_('signup.fullName')}
			<input type="text" bind:value={fullName} autocomplete="name" />
		</label>

		<label>
			{$_('signup.email')}
			<input type="email" bind:value={email} required autocomplete="email" />
		</label>

		<label>
			{$_('signup.password')}
			<input type="password" bind:value={password} required autocomplete="new-password" />
		</label>

		<fieldset>
			<legend>{$_('signup.roleLabel')}</legend>
			<label class="signup__role">
				<input type="radio" bind:group={role} value="job_seeker" />
				{$_('signup.roleSeeker')}
			</label>
			<label class="signup__role">
				<input type="radio" bind:group={role} value="recruiter" />
				{$_('signup.roleRecruiter')}
			</label>
		</fieldset>

		{#if consentRequired}
			<div class="signup__consent">
				<label>
					<input type="checkbox" bind:checked={acceptTos} />
					{$_('signup.acceptTos')}
				</label>
				<label>
					<input type="checkbox" bind:checked={goodFaith} />
					{$_('signup.goodFaith')}
				</label>
			</div>
		{/if}

		{#if status === 'error' && errorMessage}
			<p class="signup__error" role="alert">{errorMessage}</p>
		{/if}

		<button type="submit" disabled={submitDisabled}>
			{status === 'loading' ? $_('signup.submitting') : $_('signup.submit')}
		</button>
	</form>

	<p class="signup__login">
		{$_('signup.haveAccount')}
		<a href="/login">{$_('signup.loginLink')}</a>
	</p>
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

	.signup__banner {
		padding: var(--space-3) var(--space-4);
		border: 1px solid var(--color-error);
		border-radius: var(--radius-card);
		background: var(--color-error-bg);
		color: var(--color-error);
		margin: 0;
	}

	.signup__form {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.signup__form label {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		font-size: var(--text-sm);
		color: var(--color-ink);
	}

	.signup__form input[type='text'],
	.signup__form input[type='email'],
	.signup__form input[type='password'] {
		padding: var(--space-2) var(--space-3);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-control);
		background: var(--clay-fill);
		color: var(--color-ink-strong);
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.signup__form input[type='text']:focus-visible,
	.signup__form input[type='email']:focus-visible,
	.signup__form input[type='password']:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	fieldset {
		border: 1px solid var(--color-line);
		border-radius: var(--radius-card);
		padding: var(--space-3);
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	legend {
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
		padding: 0 var(--space-1);
	}

	.signup__role {
		flex-direction: row !important;
		align-items: center;
		gap: var(--space-2) !important;
	}

	.signup__consent {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-3);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--color-surface-alt, var(--color-surface));
	}

	.signup__consent label {
		flex-direction: row;
		align-items: flex-start;
		gap: var(--space-2);
		font-size: var(--text-sm);
	}

	.signup__error {
		margin: 0;
		color: var(--error);
		font-size: var(--text-sm);
	}

	button[type='submit'] {
		padding: var(--space-3) var(--space-4);
		border: none;
		border-radius: var(--radius-card);
		background: var(--color-action);
		color: var(--color-on-action);
		font-weight: 600;
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	button[type='submit']:hover:not(:disabled) {
		box-shadow: var(--clay-lifted);
	}

	button[type='submit']:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	button[type='submit']:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.signup__login {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}
</style>
