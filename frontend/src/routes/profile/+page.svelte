<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { apiClient } from '$api/client';
	import { ApiError, type CVStructuredData, type CVSummary } from '$api/types';
	import {
		completeOnboarding,
		isOnboarding,
		requireSession,
		session
	} from '$stores/session';
	import CvStructuredForm from '$components/CvStructuredForm.svelte';

	const ONBOARDING_STEP_KEY = 'asistcv.onboarding_step';

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
		const MAX_PDF_BYTES = 10 * 1024 * 1024;
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
			uploadError = err instanceof ApiError ? err.message : $_('cv.uploadError');
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

	.profile__cvs {
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
</style>
