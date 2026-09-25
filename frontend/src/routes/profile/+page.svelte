<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { apiClient } from '$api/client';
	import { ApiError, type CVSummary, type MatchAnalysis, type CVStructuredData } from '$api/types';
	import { profileStore } from '$stores/profile';
	import {
		completeOnboarding,
		isOnboarding,
		requireSession,
		session
	} from '$stores/session';
	import CvStructuredForm from '$components/CvStructuredForm.svelte';

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
