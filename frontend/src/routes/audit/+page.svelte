<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { auditStore } from '$stores/audit';
	import { setPendingAuditToken } from '$stores/session';

	const MAX_FILE_SIZE = 10 * 1024 * 1024;

	let cvText = '';
	let jdText = '';
	let jdExpanded = false;
	let mode: 'pdf' | 'text' = 'pdf';
	let cvFile: File | null = null;
	let fileError = '';

	let email = '';
	let captureStatus: 'idle' | 'loading' | 'error' | 'done' = 'idle';
	let captureMessage = '';

	$: audit = $auditStore;

	function formatSize(bytes: number): string {
		if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
		return `${Math.max(1, Math.round(bytes / 1024))} KB`;
	}

	function setMode(next: 'pdf' | 'text') {
		mode = next;
		fileError = '';
	}

	function handleFileChange(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0] ?? null;
		fileError = '';
		if (file && file.size > MAX_FILE_SIZE) {
			cvFile = null;
			input.value = '';
			fileError = $_('audit.fileTooLarge');
			return;
		}
		cvFile = file;
	}

	function clearFile() {
		cvFile = null;
		fileError = '';
		const input = document.getElementById('audit-cv-file') as HTMLInputElement | null;
		if (input) input.value = '';
	}

	function messageForError(): string {
		const code = audit.errorCode;
		if (code === 'PDF_NO_TEXT') return $_('audit.pdfNoText');
		if (code === 'PDF_PARSE_FAILED') return $_('audit.pdfParseFailed');
		if (code === 'FILE_TOO_LARGE') return $_('audit.fileTooLarge');
		if (code === 'UNSUPPORTED_MEDIA_TYPE') return $_('audit.wrongFileType');
		if (code === 'CV_TOO_SHORT') return $_('audit.cvTooShort');
		if (code === 'CV_REQUIRED') return $_('audit.cvRequired');
		if (audit.error === 'JD_TOO_SHORT' || code === 'JD_TOO_SHORT') return $_('form.validationShort');
		if (audit.retryAfter !== null) {
			return $_('audit.rateLimited', { values: { minutes: Math.ceil(audit.retryAfter / 60) } });
		}
		return audit.error ?? $_('audit.genericError');
	}

	async function handleSubmit() {
		fileError = '';
		if (mode === 'pdf' && !cvFile) {
			fileError = $_('audit.cvRequired');
			return;
		}
		if (mode === 'text' && !cvText.trim()) {
			fileError = $_('audit.cvRequired');
			return;
		}
		const result = await auditStore.submit(
			jdText,
			mode === 'text' ? cvText : '',
			mode === 'pdf' ? (cvFile ?? undefined) : undefined
		);
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
		<div class="audit__modes" role="tablist" aria-label={$_('audit.cvLabel')}>
			<button
				type="button"
				role="tab"
				aria-selected={mode === 'pdf'}
				class:active={mode === 'pdf'}
				on:click={() => setMode('pdf')}
			>
				{$_('audit.modePdf')}
			</button>
			<button
				type="button"
				role="tab"
				aria-selected={mode === 'text'}
				class:active={mode === 'text'}
				on:click={() => setMode('text')}
			>
				{$_('audit.modeText')}
			</button>
		</div>

		{#if mode === 'pdf'}
			<div class="audit__file">
				<label class="audit__file-button" for="audit-cv-file">{$_('audit.fileLabel')}</label>
				<input
					id="audit-cv-file"
					class="audit__file-input"
					type="file"
					accept=".pdf,application/pdf"
					on:change={handleFileChange}
				/>
				{#if cvFile}
					<p class="audit__file-meta">
						{cvFile.name} · {formatSize(cvFile.size)}
						<button type="button" class="audit__file-clear" on:click={clearFile}>
							{$_('audit.fileClear')}
						</button>
					</p>
				{/if}
			</div>
		{:else}
			<label>
				{$_('audit.cvLabel')}
				<textarea rows="8" bind:value={cvText} placeholder={$_('audit.cvPlaceholder')} />
			</label>
		{/if}

		<section class="audit__jd">
			<button
				type="button"
				class="audit__jd-toggle"
				aria-expanded={jdExpanded}
				on:click={() => (jdExpanded = !jdExpanded)}
			>
				{$_('audit.jdOptionalToggle')}
			</button>
			{#if jdExpanded}
				<label>
					{$_('audit.jdLabel')}
					<textarea rows="8" bind:value={jdText} placeholder={$_('form.placeholder')} />
				</label>
			{/if}
		</section>

		{#if fileError}
			<p class="audit__error" role="alert">{fileError}</p>
		{/if}
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

			{#if audit.result.mode === 'cv_only'}
				<h2>{$_('result.problematicas')}</h2>
				<ul class="audit__issues">
					{#each audit.result.problematicas ?? [] as issue}
						<li>
							<header>
								<strong>{issue.seccion}</strong>
								<span class="audit__severity audit__severity--{issue.severidad}">
									{issue.severidad}
								</span>
							</header>
							<p>{issue.problema}</p>
						</li>
					{/each}
				</ul>

				<h2>{$_('result.recomendaciones')}</h2>
				<ul>
					{#each audit.result.recomendaciones ?? [] as item}
						<li>{item}</li>
					{/each}
				</ul>

				<h2>{$_('result.fortalezas')}</h2>
				<ul>
					{#each audit.result.strengths as item}
						<li>{item}</li>
					{/each}
				</ul>

				<p class="audit__reasoning">{audit.result.reasoning}</p>
			{:else}
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
			{/if}

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
		gap: var(--space-5);
	}

	.audit__intro h1 {
		margin: 0 0 var(--space-2);
		font-size: var(--text-2xl);
		color: var(--color-ink-strong);
	}

	.audit__intro p {
		margin: 0;
		color: var(--color-ink-muted);
	}

	.audit__form {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.audit__modes {
		display: flex;
		gap: var(--space-2);
	}

	/* Mode switch: a control, so it gets clay. */
	.audit__form .audit__modes button {
		padding: var(--space-2) var(--space-4);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--clay-fill);
		color: var(--color-ink);
		font-weight: 600;
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.audit__form .audit__modes button:hover {
		box-shadow: var(--clay-lifted);
	}

	.audit__form .audit__modes button:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.audit__form .audit__modes button.active {
		border-color: var(--color-action);
		background: var(--color-action);
		color: var(--color-on-action);
	}

	.audit__file {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.audit__file-input {
		display: none;
	}

	.audit__file-button {
		align-self: flex-start;
		padding: var(--space-2) var(--space-4);
		border: var(--border-width) dashed var(--color-line);
		border-radius: var(--radius-card);
		background: var(--clay-fill);
		color: var(--color-ink);
		font-weight: 600;
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.audit__file-button:hover {
		box-shadow: var(--clay-lifted);
	}

	.audit__file-button:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.audit__file-meta {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-ink);
	}

	.audit__form .audit__file-clear {
		margin-left: var(--space-2);
		padding: var(--space-1) 0.5rem;
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-control);
		background: var(--clay-fill);
		color: var(--color-ink-muted);
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.audit__form .audit__file-clear:hover {
		box-shadow: var(--clay-lifted);
	}

	.audit__form .audit__file-clear:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.audit__form label {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		font-size: var(--text-sm);
		color: var(--color-ink);
	}

	.audit__form textarea {
		padding: var(--space-2) 0.75rem;
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--clay-fill);
		color: var(--color-ink);
		font-family: inherit;
		resize: vertical;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.audit__form textarea:focus {
		outline: 2px solid var(--color-action);
		outline-offset: 1px;
		border-color: var(--color-action);
		box-shadow: var(--clay-lifted);
	}

	.audit__form button,
	.audit__capture-form button {
		align-self: flex-start;
		padding: var(--space-2) var(--space-4);
		border: none;
		border-radius: var(--radius-card);
		background: var(--color-action);
		color: var(--color-on-action);
		font-weight: 600;
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.audit__form button:hover:not(:disabled),
	.audit__capture-form button:hover:not(:disabled) {
		filter: brightness(1.05);
		box-shadow: var(--clay-lifted);
	}

	.audit__form button:focus-visible,
	.audit__capture-form button:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.audit__form button:disabled,
	.audit__capture-form button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.audit__error {
		margin: 0;
		color: var(--color-danger);
		font-size: var(--text-sm);
	}

	.audit__error button {
		margin-left: var(--space-3);
		padding: 0.25rem var(--space-2);
		border: var(--border-width) solid var(--color-danger);
		border-radius: var(--radius-control);
		background: var(--clay-fill);
		color: var(--color-danger);
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.audit__error button:hover {
		box-shadow: var(--clay-lifted);
	}

	.audit__error button:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.audit__jd {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	/* Disclosure toggle: a control, so it gets clay. */
	.audit__jd-toggle {
		align-self: flex-start;
		padding: var(--space-2) var(--space-4);
		border: var(--border-width) dashed var(--color-line);
		border-radius: var(--radius-card);
		background: var(--clay-fill);
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
		cursor: pointer;
		text-align: left;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.audit__jd-toggle:hover {
		box-shadow: var(--clay-lifted);
	}

	.audit__jd-toggle:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.audit__jd-toggle[aria-expanded='true'] {
		border-style: solid;
		border-color: var(--color-action);
		color: var(--color-ink-strong);
	}

	.audit__issues {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		list-style: none;
		margin: 0;
		padding: 0;
	}

	/* Findings, not controls. Flat. */
	.audit__issues li {
		padding: var(--space-3) var(--space-4);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--color-surface);
	}

	.audit__issues header {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.audit__issues p {
		margin: var(--space-1) 0 0;
		color: var(--color-ink);
	}

	.audit__severity {
		padding: var(--space-1) 0.5rem;
		border-radius: var(--radius-pill);
		font-size: var(--text-xs);
		font-weight: 700;
		text-transform: uppercase;
		border: var(--border-width) solid var(--color-line);
		color: var(--color-ink-muted);
	}

	.audit__severity--high {
		border-color: var(--color-danger);
		color: var(--color-danger);
	}

	.audit__result {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.audit__result h2 {
		margin: var(--space-3) 0 var(--space-1);
		font-size: var(--text-md);
		color: var(--color-ink-strong);
	}

	.audit__result ul {
		margin: 0;
		padding-left: var(--space-5);
		color: var(--color-ink);
	}

	/* Score display. Stays flat: a bounce shadow behind a saturated fill would
	   read as a glow around the number, which is the exact failure mode the
	   "clay on controls only" rule exists to prevent. */
	.audit__score {
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
		padding: var(--space-4) var(--space-5);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-panel);
		background: var(--color-surface);
	}

	.audit__score strong {
		font-size: var(--text-3xl);
		color: var(--color-ink-strong);
	}

	.audit__reasoning {
		white-space: pre-wrap;
		color: var(--color-ink);
		padding: var(--space-4) var(--space-5);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-panel);
		background: var(--color-surface);
	}

	.audit__capture {
		margin-top: var(--space-4);
		padding: var(--space-5);
		border: var(--border-width) solid var(--color-action);
		border-radius: var(--radius-panel);
		background: var(--color-surface);
	}

	.audit__capture-form {
		display: flex;
		gap: var(--space-2);
		margin-top: var(--space-2);
	}

	.audit__capture-form input {
		flex: 1;
		max-width: 20rem;
		padding: var(--space-2) 0.75rem;
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--clay-fill);
		color: var(--color-ink);
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.audit__capture-form input:focus {
		outline: 2px solid var(--color-action);
		outline-offset: 1px;
		border-color: var(--color-action);
		box-shadow: var(--clay-lifted);
	}

	.audit__capture-done {
		color: var(--color-ink);
		font-weight: 600;
	}

	.audit__signup-cta {
		margin: var(--space-4) 0 0;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.audit__signup-cta a {
		font-weight: 700;
	}

	/* 640px stays a LITERAL on purpose: var() in a media condition silently
	   drops the whole block. See the note on --breakpoint-sm in app.css. */
	@media (max-width: 640px) {
		.audit__capture-form {
			flex-direction: column;
		}
	}
</style>
