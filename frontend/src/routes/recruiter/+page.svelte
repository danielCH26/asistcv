<script lang="ts">
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { apiClient } from '$api/client';
	import {
		ApiError,
		type Candidate,
		type CandidateMatchResult,
		type RankedCandidates
	} from '$api/types';
	import { requireRole } from '$stores/session';

	const TOS_VERSION = '2025-sprint2';
	const MAX_PDF_BYTES = 10 * 1024 * 1024;

	let ready = false;
	let consentOk = false;
	let consentError = '';
	let acceptTos = false;
	let goodFaith = false;
	let consentSubmitting = false;

	let candidates: Candidate[] = [];
	let total = 0;
	let page = 1;
	const pageSize = 20;
	let listError = '';

	let fullName = '';
	let email = '';
	let phone = '';
	let notes = '';
	let cvFile: File | null = null;
	let creating = false;
	let createError = '';

	let jdText = '';
	let matchingId: number | null = null;
	let matchResults = new Map<number, CandidateMatchResult>();
	let matchError = '';
	let planLimitReached = false;

	let ranked: RankedCandidates | null = null;
	let ranking = false;
	let rankError = '';

	async function candidateErrorMessage(err: ApiError): Promise<string> {
		switch (err.code) {
			case 'CANDIDATE_DUPLICATED':
				return $_('recruiter.duplicated');
			case 'CONSENT_REQUIRED':
				consentOk = false;
				return $_('recruiter.consentRequired');
			case 'PLAN_LIMIT_REACHED':
				planLimitReached = true;
				return $_('plan.limitReached');
			default:
				return err.message;
		}
	}

	onMount(async () => {
		if (!(await requireRole('recruiter'))) return;
		ready = true;
		await loadRoster();
	});

	async function loadRoster() {
		listError = '';
		try {
			const res = await apiClient.listCandidates(page, pageSize);
			candidates = res.items;
			total = res.total;
			consentOk = true;
		} catch (err) {
			if (err instanceof ApiError && err.status === 403) {
				consentOk = false;
			} else {
				listError = err instanceof ApiError ? await candidateErrorMessage(err) : $_('recruiter.listError');
			}
		}
	}

	async function submitConsent() {
		if (!acceptTos || !goodFaith) return;
		consentSubmitting = true;
		consentError = '';
		try {
			await apiClient.giveConsent(TOS_VERSION);
			consentOk = true;
			await loadRoster();
		} catch (err) {
			consentError = err instanceof ApiError ? err.message : $_('recruiter.consentError');
		} finally {
			consentSubmitting = false;
		}
	}

	async function handleFile(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		cvFile = input.files?.[0] ?? null;
		if (cvFile && cvFile.size > MAX_PDF_BYTES) {
			createError = $_('cv.fileTooLarge');
			cvFile = null;
		}
	}

	async function addCandidate() {
		creating = true;
		createError = '';
		try {
			await apiClient.createCandidate(
				{ full_name: fullName.trim(), email: email.trim() || undefined, phone: phone.trim() || undefined, notes: notes.trim() || undefined },
				cvFile ?? undefined
			);
			fullName = '';
			email = '';
			phone = '';
			notes = '';
			cvFile = null;
			await loadRoster();
		} catch (err) {
			createError = err instanceof ApiError ? await candidateErrorMessage(err) : $_('recruiter.createError');
		} finally {
			creating = false;
		}
	}

	async function deleteCandidate(id: number) {
		try {
			await apiClient.deleteCandidate(id);
			await loadRoster();
		} catch (err) {
			listError = err instanceof ApiError ? await candidateErrorMessage(err) : $_('recruiter.listError');
		}
	}

	async function runCandidateMatch(candidate: Candidate) {
		if (jdText.trim().length < 50) {
			matchError = $_('form.validationShort');
			return;
		}
		matchingId = candidate.id;
		matchError = '';
		planLimitReached = false;
		try {
			const result = await apiClient.matchCandidate(candidate.id, jdText.trim());
			matchResults = new Map(matchResults).set(candidate.id, result);
		} catch (err) {
			matchError = err instanceof ApiError ? await candidateErrorMessage(err) : $_('recruiter.matchError');
		} finally {
			matchingId = null;
		}
	}

	async function runRanked() {
		if (jdText.trim().length < 50) {
			rankError = $_('form.validationShort');
			return;
		}
		ranking = true;
		rankError = '';
		try {
			ranked = await apiClient.rankedCandidates(jdText.trim());
		} catch (err) {
			ranked = null;
			rankError = err instanceof ApiError ? await candidateErrorMessage(err) : $_('recruiter.matchError');
		} finally {
			ranking = false;
		}
	}
</script>

<svelte:head>
	<title>AsistCV · {$_('recruiter.title')}</title>
</svelte:head>

{#if ready && consentOk}
	<section class="recruiter">
		<h1>{$_('recruiter.heading')}</h1>

		<section class="recruiter__jd">
			<h2>{$_('recruiter.jdHeading')}</h2>
			<textarea rows="5" bind:value={jdText} placeholder={$_('form.placeholder')} />
			<div class="recruiter__jd-actions">
				<button type="button" disabled={ranking} on:click={runRanked}>
					{ranking ? $_('recruiter.ranking') : $_('recruiter.rankCta')}
				</button>
			</div>
			{#if rankError}<p class="recruiter__error">{rankError}</p>{/if}
			{#if planLimitReached}
				<div class="recruiter__upsell">
					<p>{$_('plan.limitReached')}</p>
					<a href="/billing">{$_('plan.upgradeCta')}</a>
				</div>
			{/if}
			{#if matchError}<p class="recruiter__error">{matchError}</p>{/if}
		</section>

		{#if ranked}
			<section class="recruiter__ranked">
				<h2>{$_('recruiter.rankedHeading')}</h2>
				<p class="recruiter__note">
					{ranked.is_truncated
						? $_('recruiter.rankedTruncated', { values: { shown: ranked.total, total: ranked.total_candidates } })
						: $_('recruiter.rankedFull', { values: { total: ranked.total_candidates } })}
				</p>
				<ol>
					{#each ranked.items as candidate (candidate.id)}
						<li>
							<strong>{candidate.full_name}</strong>
							{#if ranked.effective_scores[String(candidate.id)] !== undefined}
								<span class="recruiter__score">
									{$_('result.scoreLabel')}: {Math.round(ranked.effective_scores[String(candidate.id)] * 100)}
								</span>
							{/if}
						</li>
					{/each}
				</ol>
			</section>
		{/if}

		<section class="recruiter__roster">
			<h2>{$_('recruiter.rosterHeading')}</h2>
			<p class="recruiter__note">{$_('recruiter.rosterCount', { values: { total } })}</p>
			{#if listError}<p class="recruiter__error" role="alert">{listError}</p>{/if}

			{#if candidates.length === 0}
				<p class="recruiter__empty">{$_('recruiter.empty')}</p>
			{:else}
				<ul class="candidate-list">
					{#each candidates as candidate (candidate.id)}
						<li class="candidate">
							<div class="candidate__info">
								<strong>{candidate.full_name}</strong>
								{#if candidate.email}<span>{candidate.email}</span>{/if}
								{#if candidate.notes}<small>{candidate.notes}</small>{/if}
							</div>
							<div class="candidate__actions">
								{#if matchResults.has(candidate.id)}
									<span class="candidate__score">
										{$_('result.scoreLabel')}: {matchResults.get(candidate.id)?.score ?? '—'}
									</span>
								{/if}
								<button
									type="button"
									disabled={matchingId === candidate.id}
									on:click={() => runCandidateMatch(candidate)}
								>
									{matchingId === candidate.id ? $_('recruiter.matching') : $_('recruiter.matchCta')}
								</button>
								<button type="button" class="candidate__delete" on:click={() => deleteCandidate(candidate.id)}>
									{$_('cv.delete')}
								</button>
							</div>
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		<section class="recruiter__add">
			<h2>{$_('recruiter.addHeading')}</h2>
			<form on:submit|preventDefault={addCandidate}>
				<label>
					{$_('recruiter.fullName')}
					<input type="text" bind:value={fullName} required />
				</label>
				<div class="recruiter__row">
					<label>
						{$_('recruiter.email')}
						<input type="email" bind:value={email} />
					</label>
					<label>
						{$_('recruiter.phone')}
						<input type="tel" bind:value={phone} />
					</label>
				</div>
				<label>
					{$_('recruiter.notes')}
					<textarea rows="2" bind:value={notes} />
				</label>
				<label>
					{$_('cv.uploadPdf')}
					<input type="file" accept="application/pdf" on:change={handleFile} />
				</label>
				{#if createError}<p class="recruiter__error" role="alert">{createError}</p>{/if}
				<button type="submit" disabled={creating}>
					{creating ? $_('recruiter.saving') : $_('recruiter.addCta')}
				</button>
			</form>
		</section>
	</section>
{:else if ready && !consentOk}
	<section class="recruiter recruiter--consent">
		<h1>{$_('recruiter.consentHeading')}</h1>
		<p>{$_('recruiter.consentIntro')}</p>
		<form class="recruiter__consent-form" on:submit|preventDefault={submitConsent}>
			<label>
				<input type="checkbox" bind:checked={acceptTos} />
				{$_('signup.acceptTos')}
			</label>
			<label>
				<input type="checkbox" bind:checked={goodFaith} />
				{$_('signup.goodFaith')}
			</label>
			{#if consentError}<p class="recruiter__error" role="alert">{consentError}</p>{/if}
			<button type="submit" disabled={!acceptTos || !goodFaith || consentSubmitting}>
				{$_('recruiter.consentCta')}
			</button>
		</form>
	</section>
{/if}

<style>
	.recruiter {
		display: flex;
		flex-direction: column;
		gap: 1.75rem;
	}

	.recruiter h1 {
		margin: 0;
		font-size: 1.5rem;
		color: var(--text-strong);
	}

	.recruiter h2 {
		margin: 0 0 0.5rem;
		font-size: 1.15rem;
		color: var(--text-strong);
	}

	.recruiter--consent {
		max-width: 32rem;
	}

	.recruiter__consent-form {
		display: flex;
		flex-direction: column;
		gap: 0.8rem;
	}

	.recruiter__consent-form label {
		display: flex;
		gap: 0.5rem;
		align-items: flex-start;
		font-size: 0.9rem;
	}

	.recruiter__consent-form button {
		align-self: flex-start;
		padding: 0.55rem 1.1rem;
		border: none;
		border-radius: 8px;
		background: var(--accent);
		color: var(--accent-contrast);
		font-weight: 600;
		cursor: pointer;
	}

	.recruiter__consent-form button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.recruiter__jd,
	.recruiter__roster,
	.recruiter__add,
	.recruiter__ranked {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	textarea,
	.recruiter input[type='text'],
	.recruiter input[type='email'],
	.recruiter input[type='tel'] {
		padding: 0.55rem 0.7rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--surface);
		color: var(--text-strong);
		font-family: inherit;
		resize: vertical;
		width: 100%;
		box-sizing: border-box;
	}

	.recruiter__jd-actions button {
		align-self: flex-start;
		padding: 0.5rem 1rem;
		border: 1px solid var(--accent);
		border-radius: 8px;
		background: var(--accent);
		color: var(--accent-contrast);
		font-weight: 600;
		cursor: pointer;
	}

	.recruiter__jd-actions button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.recruiter__error {
		margin: 0;
		color: var(--error);
		font-size: 0.9rem;
	}

	.recruiter__note {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.85rem;
	}

	.recruiter__empty {
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.candidate-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.candidate {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		padding: 0.65rem 0.9rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface);
	}

	.candidate__info {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	.candidate__info span {
		color: var(--text-muted);
		font-size: 0.85rem;
	}

	.candidate__info small {
		color: var(--text-muted);
	}

	.candidate__actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.candidate__actions button {
		padding: 0.35rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: transparent;
		color: var(--text);
		cursor: pointer;
		font-size: 0.85rem;
	}

	.candidate__actions button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.candidate__delete {
		color: var(--error) !important;
		border-color: var(--error) !important;
	}

	.candidate__score,
	.recruiter__score {
		font-weight: 600;
		color: var(--text-strong);
		font-size: 0.9rem;
	}

	.recruiter__add form {
		display: flex;
		flex-direction: column;
		gap: 0.8rem;
		max-width: 32rem;
	}

	.recruiter__add label {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		font-size: 0.9rem;
		color: var(--text);
	}

	.recruiter__row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.8rem;
	}

	.recruiter__add button[type='submit'] {
		align-self: flex-start;
		padding: 0.55rem 1.1rem;
		border: none;
		border-radius: 8px;
		background: var(--accent);
		color: var(--accent-contrast);
		font-weight: 600;
		cursor: pointer;
	}

	.recruiter__add button[type='submit']:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.recruiter__upsell {
		padding: 1rem;
		border: 1px solid var(--accent);
		border-radius: 8px;
		background: var(--surface);
	}

	.recruiter__ranked ol {
		margin: 0;
		padding-left: 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	@media (max-width: 640px) {
		.recruiter__row {
			grid-template-columns: 1fr;
		}

		.candidate {
			flex-direction: column;
			align-items: flex-start;
		}
	}
</style>
