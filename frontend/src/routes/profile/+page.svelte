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

	/** Garantiza un Profile para el contexto del match; lo crea desde el CV si falta. */
	async function ensureProfile(): Promise<number> {
		const current = get(profileStore);
		try {
			await apiClient.getProfile(current);
			return current;
		} catch {
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
			<h2>{$_('profile.matchHeading')}</h2>
			<p class="profile__match-hint">
				{activeCv
					? $_('profile.matchWithCv', { values: { name: activeCv.original_filename } })
					: $_('profile.matchNoCv')}
			</p>
			<textarea
				class="profile__jd"
				rows="6"
				bind:value={jdText}
				placeholder={$_('form.placeholder')}
			/>
			<button type="button" disabled={matching} on:click={runMatch}>
				{matching ? $_('form.submitting') : $_('form.submit')}
			</button>

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
					<p class="profile__score">{$_('result.scoreLabel')}: <strong>{matchResult.score}</strong></p>
					<h3>{$_('result.reasoning')}</h3>
					<p class="profile__reasoning">{matchResult.reasoning}</p>
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
		gap: 1.75rem;
	}

	.profile h1 {
		margin: 0;
		font-size: 1.5rem;
		color: var(--text-strong);
	}

	.profile h2 {
		margin: 0 0 0.5rem;
		font-size: 1.15rem;
		color: var(--text-strong);
	}

	.profile__user {
		margin: -0.5rem 0 0;
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.onboarding {
		padding: 1.25rem;
		border: 1px solid var(--accent);
		border-radius: 12px;
		background: var(--surface);
	}

	.onboarding__steps {
		color: var(--text-muted);
		font-size: 0.85rem;
		margin: 0.25rem 0 0.75rem;
	}

	.onboarding__cv {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.profile__upload,
	.onboarding__upload {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		font-size: 0.9rem;
		color: var(--text);
	}

	.profile__cvs,
	.profile__match {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.profile__error {
		margin: 0;
		color: var(--error);
		font-size: 0.9rem;
	}

	.profile__empty {
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.cv-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.cv-list__item {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.6rem 0.8rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface);
	}

	.cv-list__item.is-selected {
		border-color: var(--accent);
	}

	.cv-list__pick {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex: 1;
		cursor: pointer;
	}

	.cv-list__date {
		color: var(--text-muted);
		font-size: 0.8rem;
	}

	.cv-list__item button {
		padding: 0.3rem 0.7rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: transparent;
		color: var(--text);
		cursor: pointer;
		font-size: 0.85rem;
	}

	.cv-list__delete {
		color: var(--error) !important;
		border-color: var(--error) !important;
	}

	.profile__jd {
		width: 100%;
		padding: 0.6rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface);
		color: var(--text-strong);
		font-family: inherit;
		resize: vertical;
	}

	.profile__match button[type='button'] {
		align-self: flex-start;
		padding: 0.55rem 1.1rem;
		border: none;
		border-radius: 8px;
		background: var(--accent);
		color: var(--accent-contrast);
		font-weight: 600;
		cursor: pointer;
	}

	.profile__match button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.profile__adapt {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.profile__adapt-subtitle {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.profile__adapt-empty {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.profile__adapt-field {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		font-size: 0.9rem;
		color: var(--text);
	}

	.profile__adapt-field select {
		padding: 0.55rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface);
		color: var(--text-strong);
		font-family: inherit;
	}

	.profile__adapt-cta {
		align-self: flex-start;
		padding: 0.55rem 1.1rem;
		border: none;
		border-radius: 8px;
		background: var(--accent);
		color: var(--accent-contrast);
		font-weight: 600;
		cursor: pointer;
	}

	.profile__adapt-cta:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.profile__adapt-loading {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.85rem 1rem;
		border: 1px solid var(--border);
		border-radius: 10px;
		background: var(--surface);
		color: var(--text-muted);
	}

	.profile__adapt-spinner {
		width: 1rem;
		height: 1rem;
		border-radius: 50%;
		border: 2px solid var(--border);
		border-top-color: var(--accent);
		animation: profile-adapt-spin 0.9s linear infinite;
	}

	@keyframes profile-adapt-spin {
		to {
			transform: rotate(360deg);
		}
	}

	.profile__adapt-result h3 {
		margin: 0 0 0.5rem;
		font-size: 1rem;
		color: var(--text-strong);
	}

	.profile__upsell-text {
		margin: 0.4rem 0;
		color: var(--text);
	}

	.profile__adapt-previous {
		margin-top: 0.5rem;
	}

	.profile__muted {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.profile__adapt-list {
		list-style: none;
		margin: 0.5rem 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.profile__adapt-list-item {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface);
		font-size: 0.85rem;
	}

	.profile__adapt-list-id {
		color: var(--text-muted);
		font-variant-numeric: tabular-nums;
	}

	.profile__adapt-list-status {
		padding: 0.1rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		border: 1px solid var(--border);
		color: var(--text-muted);
	}

	.profile__adapt-list-status--completed {
		border-color: var(--score-high-ink);
		color: var(--score-high-ink);
	}

	.profile__adapt-list-status--failed {
		border-color: var(--error);
		color: var(--error);
	}

	.profile__adapt-list-status--pending {
		border-color: var(--accent);
		color: var(--accent);
	}

	.profile__adapt-list-date {
		margin-left: auto;
		color: var(--text-muted);
	}

	.profile__upsell {
		padding: 1rem;
		border: 1px solid var(--accent);
		border-radius: 8px;
		background: var(--surface);
	}

	.profile__upsell a {
		font-weight: 600;
	}

	.profile__result {
		padding: 1rem 1.25rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface);
	}

	.profile__score strong {
		font-size: 1.4rem;
		color: var(--text-strong);
	}

	.profile__reasoning {
		white-space: pre-wrap;
		color: var(--text);
	}
</style>
