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

	.audit__modes {
		display: flex;
		gap: 0.4rem;
	}

	.audit__form .audit__modes button {
		padding: 0.45rem 0.9rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface);
		color: var(--text);
		font-weight: 600;
		cursor: pointer;
	}

	.audit__form .audit__modes button.active {
		border-color: var(--accent);
		background: var(--accent);
		color: var(--accent-contrast);
	}

	.audit__file {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.audit__file-input {
		display: none;
	}

	.audit__file-button {
		align-self: flex-start;
		padding: 0.55rem 1.1rem;
		border: 1px dashed var(--border);
		border-radius: 8px;
		background: var(--surface);
		color: var(--text-strong);
		font-weight: 600;
		cursor: pointer;
	}

	.audit__file-meta {
		margin: 0;
		font-size: 0.9rem;
		color: var(--text);
	}

	.audit__form .audit__file-clear {
		margin-left: 0.6rem;
		padding: 0.15rem 0.5rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: transparent;
		color: var(--text-muted);
		cursor: pointer;
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

	.audit__jd {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.audit__jd-toggle {
		align-self: flex-start;
		padding: 0.45rem 0.9rem;
		border: 1px dashed var(--border);
		border-radius: 8px;
		background: var(--surface);
		color: var(--text-muted);
		font-size: 0.9rem;
		cursor: pointer;
		text-align: left;
	}

	.audit__jd-toggle[aria-expanded='true'] {
		border-style: solid;
		border-color: var(--accent);
		color: var(--text-strong);
	}

	.audit__issues {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.audit__issues li {
		padding: 0.75rem 1rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface);
	}

	.audit__issues header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.audit__issues p {
		margin: 0.35rem 0 0;
		color: var(--text);
	}

	.audit__severity {
		padding: 0.1rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 700;
		text-transform: uppercase;
		border: 1px solid var(--border);
		color: var(--text-muted);
	}

	.audit__severity--high {
		border-color: var(--error);
		color: var(--error);
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
