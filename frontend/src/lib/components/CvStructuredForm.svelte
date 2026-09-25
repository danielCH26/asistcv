<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { createEventDispatcher } from 'svelte';
	import type { CVStructuredData } from '$api/types';

	/**
	 * Editor estructurado de CV. Emite `submit` con el payload
	 * listo para `POST /v1/cvs/structured` o `PATCH /v1/cvs/{id}`.
	 */

	export let initial: CVStructuredData | null = null;
	export let disabled = false;

	const dispatch = createEventDispatcher<{ submit: CVStructuredData }>();

	let fullName = initial?.full_name ?? '';
	let email = initial?.email ?? '';
	let phone = initial?.phone ?? '';
	let location = initial?.location ?? '';
	let skillsText = (initial?.skills ?? []).join(', ');
	let experienceText = initial?.experience
		.map((e) => [e.title, e.company, e.years].filter(Boolean).join(' | '))
		.join('\n');
	let educationText = initial?.education
		.map((e) => [e.degree, e.institution, e.year].filter(Boolean).join(' | '))
		.join('\n');

	function parseRows(text: string, keys: [string, string, string]): Record<string, unknown>[] {
		return text
			.split('\n')
			.map((line) => line.trim())
			.filter((line) => line !== '')
			.map((line) => {
				const parts = line.split('|').map((p) => p.trim());
				const entry: Record<string, unknown> = {};
				keys.forEach((key, i) => {
					if (parts[i]) entry[key] = parts[i];
				});
				return entry;
			});
	}

	function handleSubmit() {
		dispatch('submit', {
			full_name: fullName.trim() || 'CV',
			email: email.trim() || null,
			phone: phone.trim() || null,
			location: location.trim() || null,
			experience: parseRows(experienceText ?? '', ['title', 'company', 'years']),
			education: parseRows(educationText ?? '', ['degree', 'institution', 'year']),
			skills: skillsText
				.split(',')
				.map((s) => s.trim())
				.filter((s) => s !== ''),
			languages: initial?.languages ?? []
		});
	}
</script>

<form class="cv-form" on:submit|preventDefault={handleSubmit}>
	<label>
		{$_('cv.form.fullName')}
		<input type="text" bind:value={fullName} required />
	</label>

	<div class="cv-form__row">
		<label>
			{$_('cv.form.email')}
			<input type="email" bind:value={email} />
		</label>
		<label>
			{$_('cv.form.phone')}
			<input type="tel" bind:value={phone} />
		</label>
	</div>

	<label>
		{$_('cv.form.location')}
		<input type="text" bind:value={location} />
	</label>

	<label>
		{$_('cv.form.skills')}
		<small>{$_('cv.form.skillsHint')}</small>
		<textarea rows="2" bind:value={skillsText} />
	</label>

	<label>
		{$_('cv.form.experience')}
		<small>{$_('cv.form.experienceHint')}</small>
		<textarea rows="4" bind:value={experienceText} />
	</label>

	<label>
		{$_('cv.form.education')}
		<small>{$_('cv.form.educationHint')}</small>
		<textarea rows="3" bind:value={educationText} />
	</label>

	<button type="submit" disabled={disabled}>
		{disabled ? $_('cv.form.saving') : $_('cv.form.save')}
	</button>
</form>

<style>
	.cv-form {
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}

	.cv-form label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		font-size: 0.9rem;
		color: var(--text);
	}

	.cv-form small {
		color: var(--text-muted);
	}

	.cv-form input,
	.cv-form textarea {
		padding: 0.5rem 0.7rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--surface);
		color: var(--text-strong);
		font-family: inherit;
		resize: vertical;
	}

	.cv-form__row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.9rem;
	}

	button[type='submit'] {
		align-self: flex-start;
		padding: 0.55rem 1.1rem;
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

	@media (max-width: 640px) {
		.cv-form__row {
			grid-template-columns: 1fr;
		}
	}
</style>
