<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { apiClient } from '$api/client';
	import { ApiError, type CVSummary, type MatchAnalysis, type CVStructuredData, type AdaptationSummary } from '$api/types';
	import { profileStore } from '$stores/profile';
	import { adaptationStore } from '$stores/adaptation';
	import {
		completeOnboarding,
		isOnboarding,
		requireSession,
		session
	} from '$stores/session';
	import CvStructuredForm from '$components/CvStructuredForm.svelte';
	import AdaptationResult from '$components/AdaptationResult.svelte';
	import JdForm from '$components/JdForm.svelte';

	// Modos de análisis (issue #61): 'jd' = match contra JD (/v1/match),
	// 'cv_only' = auditoría del CV sin JD (auditAnonymous sin jd_text).
	type AnalysisTab = 'jd' | 'cv_only';
	let activeTab: AnalysisTab = 'jd';

	const ONBOARDING_STEP_KEY = 'asistcv.onboarding_step';
	const MAX_PDF_BYTES = 10 * 1024 * 1024;

	let ready = false;
	let user = get(session)?.user ?? null;
	let cvs: CVSummary[] = [];
	let listError = '';

	let selectedCvId: number | null = null;
	let uploading = false;
	let uploadError = '';
	let editorOpen = false;
	let editorCv: CVDetailLite | null = null;
	let savingEditor = false;
	let editorError = '';

	let jdText = '';
	let matching = false;
	let matchResult: MatchAnalysis | null = null;
	let matchError = '';
	let planLimitReached = false;

	let adaptJdText = '';
	let previousAdaptations: AdaptationSummary[] = [];
	let loadingPrevious = false;
	let previousError = '';

	// Onboarding inline (3 pasos, design §8.4): 1 rol, 2 CV, 3 match.
	let onboardingActive = false;
	let onboardingStep = 1;

	type CVDetailLite = { id: number; structured: Record<string, unknown> };

	$: activeCv = cvs.find((cv) => cv.id === selectedCvId) ?? null;

	onMount(async () => {
		if (!(await requireSession())) return;
		user = get(session)?.user ?? null;
		onboardingActive = isOnboarding();
		if (onboardingActive) {
			const stored = Number.parseInt(localStorage.getItem(ONBOARDING_STEP_KEY) ?? '1', 10);
			onboardingStep = stored >= 1 && stored <= 3 ? stored : 1;
		}
		await loadCvs();
		ready = true;
	});

	function gotoOnboardingStep(step: number) {
		onboardingStep = step;
		localStorage.setItem(ONBOARDING_STEP_KEY, String(step));
	}

	function finishOnboarding() {
		completeOnboarding();
		localStorage.removeItem(ONBOARDING_STEP_KEY);
		onboardingActive = false;
	}

	async function loadCvs() {
		listError = '';
		try {
			cvs = await apiClient.listCvs();
			if (selectedCvId === null && cvs.length > 0) selectedCvId = cvs[0].id;
		} catch (err) {
			listError = err instanceof ApiError ? err.message : $_('cv.listError');
		}
	}

	async function handleUpload(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		if (file.size > MAX_PDF_BYTES) {
			uploadError = $_('cv.fileTooLarge');
			return;
		}
		uploading = true;
		uploadError = '';
		try {
			await apiClient.uploadCv(file);
			await loadCvs();
			if (onboardingActive && onboardingStep === 2) gotoOnboardingStep(3);
		} catch (err) {
			uploadError = err instanceof ApiError ? apiErrorMessage(err) : $_('cv.uploadError');
		} finally {
			uploading = false;
		}
	}

	function apiErrorMessage(err: ApiError): string {
		switch (err.code) {
			case 'FILE_TOO_LARGE':
				return $_('cv.fileTooLarge');
			case 'UNSUPPORTED_MEDIA_TYPE':
				return $_('cv.notPdf');
			case 'PDF_NO_TEXT':
				return $_('cv.noText');
			case 'PDF_PARSE_FAILED':
				return $_('cv.parseFailed');
			case 'PLAN_LIMIT_REACHED':
				return $_('plan.limitReached');
			default:
				return err.message;
		}
	}

	async function handleEditorSubmit(event: CustomEvent<CVStructuredData>) {
		const structured = event.detail;
		savingEditor = true;
		editorError = '';
		try {
			if (editorCv) {
				await apiClient.updateCv(editorCv.id, structured);
			} else {
				await apiClient.createCvStructured(structured);
				if (onboardingActive && onboardingStep === 2) gotoOnboardingStep(3);
			}
			editorOpen = false;
			editorCv = null;
			await loadCvs();
		} catch (err) {
			editorError = err instanceof ApiError ? err.message : $_('cv.uploadError');
		} finally {
			savingEditor = false;
		}
	}

	async function handleDelete(cvId: number) {
		try {
			await apiClient.deleteCv(cvId);
			if (selectedCvId === cvId) selectedCvId = null;
			await loadCvs();
		} catch (err) {
			listError = err instanceof ApiError ? err.message : $_('cv.listError');
		}
	}

	async function openEditor(cvId: number) {
		try {
			const detail = await apiClient.getCv(cvId);
			editorCv = { id: detail.id, structured: detail.structured };
			editorOpen = true;
		} catch (err) {
			listError = err instanceof ApiError ? err.message : $_('cv.listError');
		}
	}

	/** Garantiza un Profile propio para el contexto del match; lo crea desde el CV si falta. */
	async function ensureProfile(): Promise<number> {
		const current = get(profileStore);
		if (current !== null) {
			try {
				await apiClient.getProfile(current);
				return current;
			} catch {
				// 404 = no existe o es de otro usuario. En ambos casos el id
				// cacheado es inservible: olvidarlo antes de crear evita
				// apuntar otra vez al perfil de alguien más (issue #85).
				profileStore.forget();
			}
		}
		const cvDetail = selectedCvId !== null ? await apiClient.getCv(selectedCvId) : null;
		const structured = cvDetail?.structured ?? {};
		const created = await apiClient.createProfile({
			name: typeof structured.full_name === 'string' && structured.full_name ? structured.full_name : user?.full_name || 'CV',
			headline: null,
			experience: { items: structured.experience ?? [] },
			skills: { items: structured.skills ?? [] },
			preferences: { location: structured.location ?? null }
		});
		profileStore.set(created.id);
		return created.id;
	}

	async function runMatch() {
		if (jdText.trim().length < 50) {
			matchError = $_('form.validationShort');
			return;
		}
		matching = true;
		matchError = '';
		matchResult = null;
		planLimitReached = false;
		try {
			const profileId = await ensureProfile();
			matchResult = await apiClient.match({ jd_text: jdText.trim(), profile_id: profileId });
			if (onboardingActive && onboardingStep === 3) finishOnboarding();
		} catch (err) {
			if (err instanceof ApiError && err.status === 402) {
				planLimitReached = true;
				matchError = $_('plan.limitReached');
			} else {
				matchError = err instanceof ApiError ? err.message : $_('error.title');
			}
		} finally {
			matching = false;
		}
	}

	async function runAdapt() {
		if (selectedCvId === null) return;
		if (adaptJdText.trim().length < 50) {
			return;
		}
		await adaptationStore.createAdaptation(selectedCvId, adaptJdText.trim());
		await loadPreviousAdaptations();
	}

	function adaptErrorMessage(code: string | null, fallback: string): string {
		switch (code) {
			case 'LLM_ERROR':
				return $_('adapt.errors.LLM_ERROR');
			case 'INVALID_HONESTY':
				return $_('adapt.errors.INVALID_HONESTY');
			case 'PLAN_LIMIT_REACHED':
				return $_('adapt.errors.PLAN_LIMIT_REACHED');
			case 'NO_CV_FOUND':
				return $_('adapt.errors.NO_CV_FOUND');
			case 'FEATURE_DISABLED':
				return $_('adapt.errors.FEATURE_DISABLED');
			case 'POLL_TIMEOUT':
				return $_('adapt.errors.POLL_TIMEOUT');
			default:
				return fallback;
		}
	}

	async function loadPreviousAdaptations() {
		if (selectedCvId === null) {
			previousAdaptations = [];
			return;
		}
		loadingPrevious = true;
		previousError = '';
		try {
			previousAdaptations = await adaptationStore.listAdaptationsForCv(selectedCvId);
		} catch (err) {
			previousError = err instanceof ApiError ? err.message : $_('adapt.previous.errorLoad');
		} finally {
			loadingPrevious = false;
		}
	}

	let prevLoadCvId: number | null = null;
	$: if (selectedCvId !== null && selectedCvId !== prevLoadCvId) {
		prevLoadCvId = selectedCvId;
		void loadPreviousAdaptations();
	}

	function formatAdaptDate(value: string): string {
		try {
			const d = new Date(value);
			if (Number.isNaN(d.getTime())) return value;
			return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(d);
		} catch {
			return value;
		}
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('profile.title')}</title>
</svelte:head>

{#if ready}
	<section class="profile">
		<h1>{$_('profile.heading')}</h1>

		{#if user}
			<p class="profile__user">
				{$_('profile.userInfo', { values: { name: user.full_name, email: user.email } })}
				· {$_(user.role === 'recruiter' ? 'signup.roleRecruiter' : 'signup.roleSeeker')}
			</p>
		{/if}

		{#if onboardingActive}
			<section class="onboarding">
				<h2>{$_('onboarding.heading')}</h2>
				<p class="onboarding__steps">{$_('onboarding.stepOf', { values: { step: onboardingStep } })}</p>

				{#if onboardingStep === 1}
					<p>{$_('onboarding.roleConfirm', { values: { role: $_(user?.role === 'recruiter' ? 'signup.roleRecruiter' : 'signup.roleSeeker') } })}</p>
					<button type="button" on:click={() => gotoOnboardingStep(2)}>{$_('onboarding.next')}</button>
				{:else if onboardingStep === 2}
					<div class="onboarding__cv">
						<label class="onboarding__upload">
							{$_('cv.uploadPdf')}
							<input type="file" accept="application/pdf" disabled={uploading} on:change={handleUpload} />
						</label>
						{#if uploadError}<p class="profile__error">{uploadError}</p>{/if}
						<details>
							<summary>{$_('cv.useEditor')}</summary>
							<CvStructuredForm on:submit={handleEditorSubmit} disabled={savingEditor} />
							{#if editorError}<p class="profile__error">{editorError}</p>{/if}
						</details>
					</div>
				{:else}
					<p>{$_('onboarding.matchCta')}</p>
					<button type="button" on:click={finishOnboarding}>{$_('onboarding.skip')}</button>
				{/if}
			</section>
		{/if}

		<section class="profile__cvs">
			<h2>{$_('cv.heading')}</h2>
			{#if listError}<p class="profile__error" role="alert">{listError}</p>{/if}

			<label class="profile__upload">
				{$_('cv.uploadPdf')}
				<input type="file" accept="application/pdf" disabled={uploading} on:change={handleUpload} />
			</label>
			{#if uploadError}<p class="profile__error">{uploadError}</p>{/if}

			<details class="profile__editor-toggle">
				<summary>{$_('cv.createStructured')}</summary>
				<CvStructuredForm on:submit={handleEditorSubmit} disabled={savingEditor} />
				{#if editorError}<p class="profile__error">{editorError}</p>{/if}
			</details>

			{#if cvs.length === 0}
				<p class="profile__empty">{$_('cv.empty')}</p>
			{:else}
				<ul class="cv-list">
					{#each cvs as cv (cv.id)}
						<li class="cv-list__item" class:is-selected={cv.id === selectedCvId}>
							<label class="cv-list__pick">
								<input
									type="radio"
									name="selected-cv"
									value={cv.id}
									checked={cv.id === selectedCvId}
									on:change={() => (selectedCvId = cv.id)}
								/>
								<span>{cv.original_filename}</span>
							</label>
							<span class="cv-list__date">{new Date(cv.last_edited_at).toLocaleDateString()}</span>
							<button type="button" on:click={() => openEditor(cv.id)}>{$_('cv.edit')}</button>
							<button type="button" class="cv-list__delete" on:click={() => handleDelete(cv.id)}>
								{$_('cv.delete')}
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		<section class="profile__match">
			<div class="profile__tabs" role="tablist" aria-label={$_('profile.matchHeading')}>
				<button
					type="button"
					role="tab"
					aria-selected={activeTab === 'jd'}
					class:active={activeTab === 'jd'}
					on:click={() => (activeTab = 'jd')}
				>
					{$_('profile.tabCvVsJd')}
				</button>
				<button
					type="button"
					role="tab"
					aria-selected={activeTab === 'cv_only'}
					class:active={activeTab === 'cv_only'}
					on:click={() => (activeTab = 'cv_only')}
				>
					{$_('profile.tabCvOnly')}
				</button>
			</div>

			{#if activeTab === 'jd'}
				<div class="profile__panel" role="tabpanel">
					<p class="profile__match-hint">
						{activeCv
							? $_('profile.matchWithCv', { values: { name: activeCv.original_filename } })
							: $_('profile.matchNoCv')}
					</p>
					<JdForm
						bind:value={jdText}
						loading={matching}
						headingKey="profile.jdLabel"
						introKey="profile.jdIntro"
						on:submit={() => runMatch()}
					/>

					{#if planLimitReached}
						<div class="profile__upsell" role="alert">
							<p>{$_('plan.limitReached')}</p>
							<a href="/billing">{$_('plan.upgradeCta')}</a>
						</div>
					{:else if matchError}
						<p class="profile__error" role="alert">{matchError}</p>
					{/if}

					{#if matchResult}
						<div class="profile__result">
							<p class="profile__score">
								{$_('result.scoreLabel')}: <strong>{matchResult.score}</strong>
							</p>
							<h3>{$_('result.reasoning')}</h3>
							<p class="profile__reasoning">{matchResult.reasoning}</p>
						</div>
					{/if}
				</div>
			{:else}
				<div class="profile__panel" role="tabpanel">
					<p class="profile__match-hint">{$_('profile.cvOnlyHint')}</p>
				</div>
			{/if}
		</section>

		<section class="profile__adapt">
			<h2>{$_('adapt.heading')}</h2>
			<p class="profile__adapt-subtitle">{$_('adapt.subtitle')}</p>

			{#if cvs.length === 0}
				<p class="profile__adapt-empty">{$_('adapt.form.cvPlaceholder')}</p>
			{:else}
				<label class="profile__adapt-field">
					<span>{$_('adapt.form.cvLabel')}</span>
					<select bind:value={selectedCvId} disabled={$adaptationStore.status === 'pending'}>
						{#each cvs as cv (cv.id)}
							<option value={cv.id}>{cv.original_filename}</option>
						{/each}
					</select>
				</label>
			{/if}

			<textarea
				class="profile__jd"
				rows="6"
				bind:value={adaptJdText}
				placeholder={$_('adapt.form.jdPlaceholder')}
				disabled={$adaptationStore.status === 'pending'}
			/>

			<button
				type="button"
				class="profile__adapt-cta"
				disabled={$adaptationStore.status === 'pending' || selectedCvId === null || adaptJdText.trim().length < 50}
				on:click={runAdapt}
			>
				{$adaptationStore.status === 'pending' ? $_('adapt.status.pending') : $_('adapt.cta.submit')}
			</button>

			{#if $adaptationStore.status === 'failed' && $adaptationStore.errorCode === 'PLAN_LIMIT_REACHED'}
				<div class="profile__upsell" role="alert">
					<p>{$_('adapt.errors.PLAN_LIMIT_REACHED')}</p>
					<p class="profile__upsell-text">{$_('adapt.upsell.text')}</p>
					<a href="/billing">{$_('adapt.upsell.cta')}</a>
				</div>
			{:else if $adaptationStore.status === 'failed'}
				<p class="profile__error" role="alert">
					{adaptErrorMessage($adaptationStore.errorCode, $adaptationStore.errorMessage ?? $_('adapt.errors.GENERIC'))}
					<button type="button" on:click={() => adaptationStore.reset()}>{$_('adapt.cta.retry')}</button>
				</p>
			{/if}

			{#if $adaptationStore.status === 'pending'}
				<div class="profile__adapt-loading" role="status">
					<div class="profile__adapt-spinner" aria-hidden="true"></div>
					<p>{$_('adapt.status.pending')}</p>
				</div>
			{/if}

			{#if $adaptationStore.status === 'completed' && $adaptationStore.adaptation?.adapted_cv}
				<div class="profile__adapt-result">
					<h3>{$_('adapt.result.heading')}</h3>
					<AdaptationResult adapted={$adaptationStore.adaptation.adapted_cv} />
				</div>
			{/if}

			<details class="profile__adapt-previous">
				<summary>{$_('adapt.previous.heading')}</summary>
				{#if loadingPrevious}
					<p class="profile__muted">…</p>
				{:else if previousError}
					<p class="profile__error" role="alert">{previousError}</p>
				{:else if previousAdaptations.length === 0}
					<p class="profile__muted">{$_('adapt.previous.empty')}</p>
				{:else}
					<ul class="profile__adapt-list">
						{#each previousAdaptations as item (item.id)}
							<li class="profile__adapt-list-item">
								<span class="profile__adapt-list-id">#{item.id}</span>
								<span class="profile__adapt-list-status profile__adapt-list-status--{item.status}">
									{item.status === 'completed'
										? $_('adapt.previous.statusCompleted')
										: item.status === 'failed'
											? $_('adapt.previous.statusFailed')
											: $_('adapt.previous.statusPending')}
								</span>
								<span class="profile__adapt-list-date">{formatAdaptDate(item.created_at)}</span>
							</li>
						{/each}
					</ul>
				{/if}
			</details>
		</section>
	</section>
{/if}

<style>
	.profile {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.profile h1 {
		margin: 0;
		font-size: var(--text-2xl);
		color: var(--color-ink-strong);
	}

	.profile h2 {
		margin: 0 0 var(--space-2);
		font-size: var(--text-lg);
		color: var(--color-ink-strong);
	}

	.profile__user {
		margin: calc(-1 * var(--space-2)) 0 0;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.onboarding {
		padding: var(--space-5);
		border: var(--border-width) solid var(--color-action);
		border-radius: var(--radius-panel);
		background: var(--color-surface);
	}

	.onboarding__steps {
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
		margin: var(--space-1) 0 var(--space-3);
	}

	.onboarding__cv {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.profile__upload,
	.onboarding__upload {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		font-size: var(--text-sm);
		color: var(--color-ink);
	}

	.profile__cvs,
	.profile__match {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	/* Analysis-mode tabs (issue #61). Same tablist pattern as the audit page:
	   flat buttons on the surface, the active one carrying the action colour.
	   Pill radius reads as a mode switch, not a navigation bar. */
	.profile__tabs {
		display: flex;
		gap: var(--space-1);
		border-bottom: 1px solid var(--color-line);
		padding-bottom: var(--space-2);
	}

	.profile__tabs button {
		padding: var(--space-2) var(--space-4);
		border: 1px solid transparent;
		border-radius: var(--radius-pill);
		background: transparent;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
		font-weight: 600;
		cursor: pointer;
		transition:
			color var(--duration-fast) var(--ease-standard),
			background var(--duration-fast) var(--ease-standard);
	}

	.profile__tabs button:hover {
		color: var(--color-ink-strong);
	}

	.profile__tabs button.active {
		background: var(--color-action-muted);
		border-color: var(--color-action);
		color: var(--color-action);
	}

	.profile__tabs button:focus-visible {
		outline: 2px solid var(--color-action);
		outline-offset: 1px;
	}

	.profile__panel {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.profile__error {
		margin: 0;
		color: var(--color-danger);
		font-size: var(--text-sm);
	}

	.profile__empty {
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.cv-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	/* A row, not a control. The tappable parts of this row are the radio and the
	   two buttons below, so the row itself stays flat and the clay goes on those. */
	.cv-list__item {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-2) var(--space-3);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--color-surface);
	}

	.cv-list__item.is-selected {
		border-color: var(--color-action);
	}

	.cv-list__pick {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		flex: 1;
		cursor: pointer;
	}

	.cv-list__date {
		color: var(--color-ink-muted);
		font-size: var(--text-xs);
	}

	.cv-list__item button {
		padding: var(--space-1) var(--space-3);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-control);
		background: var(--clay-fill);
		color: var(--color-ink);
		cursor: pointer;
		font-size: var(--text-sm);
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.cv-list__item button:hover {
		box-shadow: var(--clay-lifted);
	}

	.cv-list__item button:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.cv-list__delete {
		color: var(--color-danger) !important;
		border-color: var(--color-danger) !important;
	}

	.profile__jd {
		width: 100%;
		padding: var(--space-2) var(--space-3);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--clay-fill);
		color: var(--color-ink);
		font-family: inherit;
		resize: vertical;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.profile__jd:focus {
		outline: 2px solid var(--color-action);
		outline-offset: 1px;
		border-color: var(--color-action);
		box-shadow: var(--clay-lifted);
	}

	.profile__match button[type='button'] {
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

	.profile__match button[type='button']:hover:not(:disabled) {
		filter: brightness(1.05);
		box-shadow: var(--clay-lifted);
	}

	.profile__match button[type='button']:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.profile__match button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.profile__adapt {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.profile__adapt-subtitle {
		margin: 0;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.profile__adapt-empty {
		margin: 0;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.profile__adapt-field {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		font-size: var(--text-sm);
		color: var(--color-ink);
	}

	.profile__adapt-field select {
		padding: var(--space-2) var(--space-3);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--clay-fill);
		color: var(--color-ink);
		font-family: inherit;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.profile__adapt-field select:focus-visible {
		outline: 2px solid var(--color-action);
		outline-offset: 1px;
		border-color: var(--color-action);
		box-shadow: var(--clay-lifted);
	}

	.profile__adapt-cta {
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

	.profile__adapt-cta:hover:not(:disabled) {
		filter: brightness(1.05);
		box-shadow: var(--clay-lifted);
	}

	.profile__adapt-cta:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.profile__adapt-cta:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.profile__adapt-loading {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-3) var(--space-4);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card-lg);
		background: var(--color-surface);
		color: var(--color-ink-muted);
	}

	.profile__adapt-spinner {
		width: var(--space-4);
		height: var(--space-4);
		border-radius: var(--radius-circle);
		border: var(--border-width-thick) solid var(--color-line);
		border-top-color: var(--color-action);
		animation: profile-adapt-spin 0.9s linear infinite;
	}

	@keyframes profile-adapt-spin {
		to {
			transform: rotate(360deg);
		}
	}

	.profile__adapt-result h3 {
		margin: 0 0 var(--space-2);
		font-size: var(--text-md);
		color: var(--color-ink-strong);
	}

	.profile__upsell-text {
		margin: var(--space-2) 0;
		color: var(--color-ink);
	}

	.profile__adapt-previous {
		margin-top: var(--space-2);
	}

	.profile__muted {
		margin: 0;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.profile__adapt-list {
		list-style: none;
		margin: var(--space-2) 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.profile__adapt-list-item {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--color-surface);
		font-size: var(--text-sm);
	}

	.profile__adapt-list-id {
		color: var(--color-ink-muted);
		font-variant-numeric: tabular-nums;
	}

	.profile__adapt-list-status {
		padding: var(--space-1) var(--space-2);
		border-radius: var(--radius-pill);
		font-size: var(--text-xs);
		font-weight: 600;
		border: var(--border-width) solid var(--color-line);
		color: var(--color-ink-muted);
	}

	.profile__adapt-list-status--completed {
		border-color: var(--score-high-ink);
		color: var(--score-high-ink);
	}

	.profile__adapt-list-status--failed {
		border-color: var(--color-danger);
		color: var(--color-danger);
	}

	.profile__adapt-list-status--pending {
		border-color: var(--color-action);
		color: var(--color-action);
	}

	.profile__adapt-list-date {
		margin-left: auto;
		color: var(--color-ink-muted);
	}

	.profile__upsell {
		padding: var(--space-4);
		border: var(--border-width) solid var(--color-action);
		border-radius: var(--radius-card);
		background: var(--color-surface);
	}

	.profile__upsell a {
		font-weight: 600;
	}

	/* A RESULT card. Not interactive, so it stays flat: a light bounce shadow
	   over a saturated surface reads as glow, not as material. */
	.profile__result {
		padding: var(--space-4) var(--space-5);
		border: var(--border-width) solid var(--color-line);
		border-radius: var(--radius-card);
		background: var(--color-surface);
	}

	.profile__score strong {
		font-size: var(--text-2xl);
		color: var(--color-ink-strong);
	}

	.profile__reasoning {
		white-space: pre-wrap;
		color: var(--color-ink);
	}
</style>
