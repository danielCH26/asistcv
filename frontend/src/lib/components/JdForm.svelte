<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { _ } from 'svelte-i18n';

	export let value = '';
	export let loading = false;
	export let minChars = 50;

	const dispatch = createEventDispatcher<{ submit: { jdText: string } }>();

	let validationError: string | null = null;

	$: characterCount = value.length;

	function handleSubmit(event: Event) {
		event.preventDefault();
		validationError = null;

		const trimmed = value.trim();
		if (trimmed.length === 0) {
			validationError = 'form.validationEmpty';
			return;
		}
		if (trimmed.length < minChars) {
			validationError = 'form.validationShort';
			return;
		}

		dispatch('submit', { jdText: trimmed });
	}
</script>

<form class="jd-form" on:submit={handleSubmit} novalidate>
	<label class="jd-form__label" for="jd-text">{$_('home.heading')}</label>
	<p class="jd-form__intro">{$_('home.intro')}</p>

	<textarea
		id="jd-text"
		class="jd-form__textarea"
		rows="10"
		placeholder={$_('form.placeholder')}
		bind:value
		disabled={loading}
		aria-invalid={validationError ? 'true' : 'false'}
	></textarea>

	<div class="jd-form__meta">
		<span class="jd-form__count" class:is-warned={characterCount > 0 && characterCount < minChars}>
			{$_('form.charsHint', { values: { count: characterCount } })}
		</span>
		<button type="submit" class="jd-form__submit" disabled={loading || characterCount < minChars}>
			{loading ? $_('form.submitting') : $_('form.submit')}
		</button>
	</div>

	{#if validationError}
		<p class="jd-form__error" role="alert">{$_(validationError)}</p>
	{/if}
</form>

<style>
	.jd-form {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1.25rem;
	}

	.jd-form__label {
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--text-strong);
	}

	.jd-form__intro {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.jd-form__textarea {
		width: 100%;
		min-height: 220px;
		resize: vertical;
		padding: 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		font-family: inherit;
		font-size: 0.95rem;
		background: var(--bg);
		color: var(--text);
	}

	.jd-form__textarea:focus {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.jd-form__textarea:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.jd-form__meta {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
	}

	.jd-form__count {
		font-size: 0.85rem;
		color: var(--text-muted);
	}

	.jd-form__count.is-warned {
		color: var(--warn);
	}

	.jd-form__submit {
		padding: 0.55rem 1.25rem;
		border: none;
		border-radius: 8px;
		background: var(--accent);
		color: var(--accent-contrast);
		font-weight: 600;
		font-size: 0.95rem;
		cursor: pointer;
	}

	.jd-form__submit:hover:not(:disabled) {
		filter: brightness(1.05);
	}

	.jd-form__submit:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.jd-form__error {
		margin: 0;
		padding: 0.5rem 0.75rem;
		border-radius: 6px;
		background: var(--error-bg);
		color: var(--error);
		font-size: 0.85rem;
	}
</style>