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
		gap: 1.25rem;
		max-width: 26rem;
		margin: 0 auto;
	}

	.signup h1 {
		margin: 0;
		font-size: 1.5rem;
		color: var(--text-strong);
	}

	.signup__banner {
		padding: 0.75rem 1rem;
		border: 1px solid var(--error);
		border-radius: 8px;
		background: var(--error-bg);
		color: var(--error);
		margin: 0;
	}

	.signup__form {
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}

	.signup__form label {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		font-size: 0.9rem;
		color: var(--text);
	}

	.signup__form input[type='text'],
	.signup__form input[type='email'],
	.signup__form input[type='password'] {
		padding: 0.55rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--surface);
		color: var(--text-strong);
	}

	fieldset {
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	legend {
		font-size: 0.85rem;
		color: var(--text-muted);
		padding: 0 0.35rem;
	}

	.signup__role {
		flex-direction: row !important;
		align-items: center;
		gap: 0.5rem !important;
	}

	.signup__consent {
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
		padding: 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface-alt, var(--surface));
	}

	.signup__consent label {
		flex-direction: row;
		align-items: flex-start;
		gap: 0.5rem;
		font-size: 0.85rem;
	}

	.signup__error {
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

	.signup__login {
		margin: 0;
		font-size: 0.9rem;
		color: var(--text-muted);
	}
</style>
