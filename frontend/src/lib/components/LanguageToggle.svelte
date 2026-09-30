<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { toggleLocale } from '$i18n/index';
</script>

<button type="button" class="lang-toggle" on:click={toggleLocale} aria-label={$_('language.toggle')}>
	<span class="lang-toggle__es">{$_('language.es')}</span>
	<span class="lang-toggle__divider">/</span>
	<span class="lang-toggle__en">{$_('language.en')}</span>
</button>

<style>
	.lang-toggle {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		padding: var(--space-1) var(--space-3);
		border: 1px solid var(--color-line);
		border-radius: 6px;
		background: var(--clay-fill);
		color: var(--color-ink);
		font-size: var(--text-sm);
		cursor: pointer;
		box-shadow: var(--clay-raised);
		transition: box-shadow var(--duration-fast) var(--ease-standard);
	}

	.lang-toggle:hover {
		box-shadow: var(--clay-lifted);
	}

	.lang-toggle:focus-visible {
		box-shadow: var(--clay-focus-ring), var(--clay-raised);
		outline: none;
	}

	.lang-toggle__divider {
		color: var(--color-ink-muted);
	}
</style>