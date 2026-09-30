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
		gap: var(--space-3);
		background: var(--color-surface);
		border: 1px solid var(--color-line);
		border-radius: 12px;
		padding: var(--space-5);
	}

	.jd-form__label {
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--color-ink-strong);
	}

	.jd-form__intro {
		margin: 0;
		color: var(--color-ink-muted);
		font-size: var(--text-sm);
	}

	.jd-form__textarea {
		width: 100%;
		min-height: 220px;
		resize: vertical;
		padding: var(--space-3);
		border: 1px solid var(--color-line);
		border-radius: 8px;
		font-family: inherit;
		font-size: var(--text-sm);
		background: var(--clay-fill);
		color: var(--color-ink);
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.jd-form__textarea:focus {
		outline: 2px solid var(--color-action);
		outline-offset: 1px;
		border-color: var(--color-action);
		box-shadow: var(--clay-lifted);
	}

	.jd-form__textarea:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.jd-form__meta {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-4);
	}

	.jd-form__count {
		font-size: var(--text-sm);
		color: var(--color-ink-muted);
	}

	.jd-form__count.is-warned {
		color: var(--color-warning);
	}

	.jd-form__submit {
		padding: var(--space-2) var(--space-5);
		border: none;
		border-radius: 8px;
		background: var(--color-action);
		color: var(--color-on-action);
		font-weight: 600;
		font-size: var(--text-sm);
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.jd-form__submit:hover:not(:disabled) {
		filter: brightness(1.05);
		box-shadow: var(--clay-lifted);
	}

	.jd-form__submit:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.jd-form__submit:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.jd-form__error {
		margin: 0;
		padding: var(--space-2) var(--space-3);
		border-radius: 6px;
		background: var(--color-danger-muted);
		color: var(--color-danger);
		font-size: var(--text-sm);
	}
</style>