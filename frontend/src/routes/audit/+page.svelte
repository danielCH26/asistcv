<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { auditStore } from '$stores/audit';
	import { setPendingAuditToken } from '$stores/session';

	let cvText = '';
	let jdText = '';

	let email = '';
	let captureStatus: 'idle' | 'loading' | 'error' | 'done' = 'idle';
	let captureMessage = '';

	$: audit = $auditStore;

	function messageForError(): string {
		if (audit.error === 'JD_TOO_SHORT') return $_('form.validationShort');
		if (audit.retryAfter !== null) {
			return $_('audit.rateLimited', { values: { minutes: Math.ceil(audit.retryAfter / 60) } });
		}
		return audit.error ?? $_('audit.genericError');
	}

	async function handleSubmit() {
		const result = await auditStore.submit(jdText, cvText);
		if (result) setPendingAuditToken(result.audit_token);
	}

	async function handleCapture() {
		if (!audit.result) return;
		captureStatus = 'loading';
		const ok = await auditStore.captureEmail(email);
		captureStatus = ok ? 'done' : 'error';
		captureMessage = ok ? $_('audit.captureDone') : $_('audit.captureError');
	}

	function retry() {
		auditStore.reset();
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('audit.title')}</title>
</svelte:head>

<section class="audit">
	<header class="audit__intro">
		<h1>{$_('audit.heading')}</h1>
		<p>{$_('audit.intro')}</p>
	</header>

	{#if audit.status !== 'done'}
		<form class="audit__form" on:submit|preventDefault={handleSubmit}>
			<label>
				{$_('audit.cvLabel')}
				<textarea rows="8" bind:value={cvText} placeholder={$_('audit.cvPlaceholder')} />
			</label>
			<label>
				{$_('audit.jdLabel')}
				<textarea rows="8" bind:value={jdText} placeholder={$_('form.placeholder')} />
			</label>

			{#if audit.status === 'error' && audit.error}
				<p class="audit__error" role="alert">
					{messageForError()}
					{#if audit.retryAfter !== null}
						<button type="button" on:click={retry}>{$_('error.retry')}</button>
					{/if}
				</p>
			{/if}

			<button type="submit" disabled={audit.status === 'loading'}>
				{audit.status === 'loading' ? $_('audit.submitting') : $_('audit.submit')}
			</button>
		</form>
	{:else if audit.result}
		<section class="audit__result">
			<div class="audit__score">
				<span>{$_('result.scoreLabel')}</span>
				<strong>{audit.result.score}</strong>
			</div>

			<h2>{$_('result.strengths')}</h2>
			<ul>
				{#each audit.result.strengths as item}
					<li>{item}</li>
				{/each}
			</ul>

			<h2>{$_('result.gaps')}</h2>
			<ul>
				{#each audit.result.gaps as item}
					<li>{item}</li>
				{/each}
			</ul>

			<h2>{$_('result.reasoning')}</h2>
			<p class="audit__reasoning">{audit.result.reasoning}</p>

			<section class="audit__capture">
				<h2>{$_('audit.captureHeading')}</h2>
				{#if captureStatus === 'done'}
					<p class="audit__capture-done">{captureMessage}</p>
				{:else}
					<form class="audit__capture-form" on:submit|preventDefault={handleCapture}>
						<input
							type="email"
							bind:value={email}
							required
							placeholder={$_('audit.emailPlaceholder')}
						/>
						<button type="submit" disabled={captureStatus === 'loading'}>
							{$_('audit.captureCta')}
						</button>
					</form>
					{#if captureStatus === 'error'}
						<p class="audit__error" role="alert">{captureMessage}</p>
					{/if}
				{/if}

				<p class="audit__signup-cta">
					{$_('audit.signupCta')}
					<a href="/signup">{$_('audit.signupLink')}</a>
				</p>
			</section>
		</section>
	{/if}
</section>

<style>
	.audit {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.audit__intro h1 {
		margin: 0 0 0.4rem;
		font-size: 1.6rem;
		color: var(--text-strong);
	}

	.audit__intro p {
		margin: 0;
		color: var(--text-muted);
	}

	.audit__form {
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}

	.audit__form label {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		font-size: 0.9rem;
		color: var(--text);
	}

	.audit__form textarea {
		padding: 0.6rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface);
		color: var(--text-strong);
		font-family: inherit;
		resize: vertical;
	}

	.audit__form button,
	.audit__capture-form button {
		align-self: flex-start;
		padding: 0.55rem 1.1rem;
		border: none;
		border-radius: 8px;
		background: var(--accent);
		color: var(--accent-contrast);
		font-weight: 600;
		cursor: pointer;
	}

	.audit__form button:disabled,
	.audit__capture-form button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.audit__error {
		margin: 0;
		color: var(--error);
		font-size: 0.9rem;
	}

	.audit__error button {
		margin-left: 0.75rem;
		padding: 0.25rem 0.6rem;
		border: 1px solid var(--error);
		border-radius: 6px;
		background: transparent;
		color: var(--error);
		cursor: pointer;
	}

	.audit__result {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.audit__result h2 {
		margin: 0.75rem 0 0.25rem;
		font-size: 1.05rem;
		color: var(--text-strong);
	}

	.audit__result ul {
		margin: 0;
		padding-left: 1.25rem;
		color: var(--text);
	}

	.audit__score {
		display: flex;
		align-items: baseline;
		gap: 0.75rem;
		padding: 1rem 1.25rem;
		border: 1px solid var(--border);
		border-radius: 12px;
		background: var(--surface);
	}

	.audit__score strong {
		font-size: 2rem;
		color: var(--text-strong);
	}

	.audit__reasoning {
		white-space: pre-wrap;
		color: var(--text);
		padding: 1rem 1.25rem;
		border: 1px solid var(--border);
		border-radius: 12px;
		background: var(--surface);
	}

	.audit__capture {
		margin-top: 1rem;
		padding: 1.25rem;
		border: 1px solid var(--accent);
		border-radius: 12px;
		background: var(--surface);
	}

	.audit__capture-form {
		display: flex;
		gap: 0.6rem;
		margin-top: 0.5rem;
	}

	.audit__capture-form input {
		flex: 1;
		max-width: 20rem;
		padding: 0.55rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface);
		color: var(--text-strong);
	}

	.audit__capture-done {
		color: var(--text);
		font-weight: 600;
	}

	.audit__signup-cta {
		margin: 0.9rem 0 0;
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.audit__signup-cta a {
		font-weight: 700;
	}

	@media (max-width: 640px) {
		.audit__capture-form {
			flex-direction: column;
		}
	}
</style>
