<script lang="ts">
	/**
	 * Shared passwordless auth flow: email → 6-digit code → session.
	 * Used by /login and /signup (they are the same flow server-side:
	 * verification creates the account on first login).
	 */
	import { _ } from 'svelte-i18n';
	import { onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { requestEmailCode, verifyEmailCode, sessionEvent } from '$stores/session';
	import { ApiError } from '$api/types';
	import { homeForRole } from '$auth/rules';

	let email = '';
	let code = '';
	let step: 'email' | 'code' = 'email';
	let status: 'idle' | 'loading' | 'error' = 'idle';
	let errorMessage = '';
	let resendIn = 0;
	let resendTimer: ReturnType<typeof setInterval> | null = null;

	const RESEND_COOLDOWN_SECONDS = 60;

	function startCooldown() {
		resendIn = RESEND_COOLDOWN_SECONDS;
		resendTimer = setInterval(() => {
			resendIn -= 1;
			if (resendIn <= 0 && resendTimer) {
				clearInterval(resendTimer);
				resendTimer = null;
			}
		}, 1000);
	}

	onDestroy(() => {
		if (resendTimer) clearInterval(resendTimer);
	});

	function messageFor(err: unknown, fallback: string): string {
		if (err instanceof ApiError) {
			const map: Record<string, string> = {
				INVALID_CODE: String($_('auth.errorInvalidCode')),
				CODE_EXPIRED: String($_('auth.errorExpired')),
				CODE_MAX_ATTEMPTS: String($_('auth.errorMaxAttempts')),
				CODE_COOLDOWN: String($_('auth.errorCooldown')),
				RATE_LIMITED: String($_('auth.errorRateLimited'))
			};
			if (err.code && map[err.code]) return map[err.code];
		}
		return fallback;
	}

	async function handleSendCode() {
		status = 'loading';
		errorMessage = '';
		try {
			await requestEmailCode(email.trim());
			status = 'idle';
			step = 'code';
			startCooldown();
		} catch (err) {
			status = 'error';
			errorMessage = messageFor(err, String($_('auth.errorSend')));
		}
	}

	async function handleVerify() {
		status = 'loading';
		errorMessage = '';
		try {
			const user = await verifyEmailCode(email.trim(), code.trim());
			sessionEvent.set(null);
			await goto(homeForRole(user.role));
		} catch (err) {
			status = 'error';
			errorMessage = messageFor(err, String($_('auth.errorGeneric')));
		}
	}

	function handleResend() {
		if (resendIn > 0 || status === 'loading') return;
		code = '';
		void handleSendCode();
	}
</script>

{#if step === 'email'}
	<form class="auth-form" on:submit|preventDefault={handleSendCode}>
		<label>
			{$_('auth.emailLabel')}
			<input
				type="email"
				bind:value={email}
				required
				autocomplete="email"
				placeholder={$_('auth.emailPlaceholder')}
			/>
		</label>

		{#if status === 'error' && errorMessage}
			<p class="auth-form__error" role="alert">{errorMessage}</p>
		{/if}

		<button type="submit" disabled={status === 'loading'}>
			{status === 'loading' ? $_('auth.sending') : $_('auth.sendCode')}
		</button>
	</form>
{:else}
	<form class="auth-form" on:submit|preventDefault={handleVerify}>
		<p class="auth-form__hint">
			{$_('auth.codeSentTo', { values: { email: email.trim() } })}
			<button type="button" class="auth-form__link" on:click={() => (step = 'email')}>
				{$_('auth.changeEmail')}
			</button>
		</p>

		<label>
			{$_('auth.codeLabel')}
			<input
				class="auth-form__code"
				type="text"
				bind:value={code}
				required
				inputmode="numeric"
				autocomplete="one-time-code"
				pattern="[0-9]*"
				maxlength="8"
			/>
		</label>

		{#if status === 'error' && errorMessage}
			<p class="auth-form__error" role="alert">{errorMessage}</p>
		{/if}

		<button type="submit" disabled={status === 'loading'}>
			{status === 'loading' ? $_('auth.verifying') : $_('auth.verify')}
		</button>

		<button
			type="button"
			class="auth-form__link"
			on:click={handleResend}
			disabled={resendIn > 0 || status === 'loading'}
		>
			{resendIn > 0 ? $_('auth.resendIn', { values: { seconds: resendIn } }) : $_('auth.resend')}
		</button>
	</form>
{/if}

<style>
	.auth-form {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.auth-form label {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		font-size: var(--text-sm);
		color: var(--color-ink);
	}

	.auth-form input {
		padding: var(--space-2) var(--space-3);
		border: 1px solid var(--color-line);
		border-radius: var(--radius-control);
		background: var(--clay-fill);
		color: var(--color-ink-strong);
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.auth-form input:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.auth-form .auth-form__code {
		font-size: var(--text-xl);
		letter-spacing: 0.5em;
		text-align: center;
	}

	.auth-form__error {
		margin: 0;
		color: var(--error);
		font-size: var(--text-sm);
	}

	.auth-form__hint {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.auth-form button[type='submit'] {
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

	.auth-form button[type='submit']:hover:not(:disabled) {
		box-shadow: var(--clay-lifted);
	}

	.auth-form button[type='submit']:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.auth-form button[type='submit']:disabled,
	.auth-form button.auth-form__link:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.auth-form button.auth-form__link {
		align-self: center;
		padding: 0;
		border: none;
		background: transparent;
		color: var(--color-action);
		font-size: var(--text-sm);
		text-decoration: underline;
		cursor: pointer;
	}
</style>
